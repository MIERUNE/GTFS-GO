"""Tests for the GTFS-GO processing algorithms."""

import os
import shutil

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProject,
    QgsRectangle,
    QgsReferencedRectangle,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QDate

from processing_provider.aggregate_frequency import AggregateFrequencyAlgorithm
from processing_provider.extract_routes_stops import ExtractRoutesAndStopsAlgorithm
from processing_provider.provider import GTFSGoProvider
from processing_provider.search_japan_dpf import SearchJapanDpfAlgorithm
from processing_provider.utils import gtfs_parser

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "gtfs_parser", "tests", "fixture"
)


@pytest.fixture(scope="module")
def gtfs_zip(tmp_path_factory):
    base = tmp_path_factory.mktemp("gtfs") / "gtfs"
    return shutil.make_archive(str(base), "zip", FIXTURE_DIR)


def run(algorithm, parameters):
    alg = algorithm.create()
    context = QgsProcessingContext()
    context.setProject(QgsProject.instance())
    feedback = QgsProcessingFeedback()
    ok, message = alg.checkParameterValues(parameters, context)
    assert ok, message
    results, ok = alg.run(parameters, context, feedback)
    assert ok, feedback.textLog()
    return results


def load(path):
    layer = QgsVectorLayer(path, "test", "ogr")
    assert layer.isValid()
    return layer


def test_provider_algorithms(qgis_app):
    provider = GTFSGoProvider()
    provider.loadAlgorithms()
    assert {alg.name() for alg in provider.algorithms()} == {
        "extractroutesandstops",
        "aggregatefrequency",
        "searchjapandpf",
    }


def test_extract_routes_and_stops(qgis_app, gtfs_zip, tmp_path):
    routes_path = str(tmp_path / "routes.geojson")
    stops_path = str(tmp_path / "stops.geojson")
    run(
        ExtractRoutesAndStopsAlgorithm(),
        {
            "INPUT": gtfs_zip,
            "IGNORE_SHAPES": False,
            "IGNORE_NO_ROUTE": False,
            "OUTPUT_ROUTES": routes_path,
            "OUTPUT_STOPS": stops_path,
        },
    )

    stops = load(stops_path)
    assert stops.featureCount() == 899
    stop = next(
        f
        for f in stops.getFeatures()
        if f["stop_id"] == "1000_04"  # 帯広駅バスターミナル
    )
    assert stop["stop_name"] == "帯広駅バスターミナル"
    assert set(stop["route_ids"]) == {
        "24_C",
        "53_F",
        "32_B",
        "33_C",
        "51_C",
        "34_A",
        "42_B",
        "41_A",
        "31_A",
        "52_D",
    }
    point = stop.geometry().asPoint()
    assert point.x() == pytest.approx(143.203227)
    assert point.y() == pytest.approx(42.918326)

    routes = load(routes_path)
    assert routes.featureCount() > 0
    assert {f.name() for f in routes.fields()} >= {"route_id", "route_name"}


def test_extract_ignore_no_route(qgis_app, gtfs_zip, tmp_path):
    stops_path = str(tmp_path / "stops.geojson")
    run(
        ExtractRoutesAndStopsAlgorithm(),
        {
            "INPUT": gtfs_zip,
            "IGNORE_SHAPES": True,
            "IGNORE_NO_ROUTE": True,
            "OUTPUT_ROUTES": str(tmp_path / "routes.geojson"),
            "OUTPUT_STOPS": stops_path,
        },
    )
    stops = load(stops_path)
    assert 0 < stops.featureCount() < 899
    assert all(len(f["route_ids"]) > 0 for f in stops.getFeatures())


def test_aggregate_frequency(qgis_app, gtfs_zip, tmp_path):
    routes_path = str(tmp_path / "aggregated_routes.geojson")
    stops_path = str(tmp_path / "aggregated_stops.geojson")
    csv_path = str(tmp_path / "result.csv")
    run(
        AggregateFrequencyAlgorithm(),
        {
            "INPUT": gtfs_zip,
            "UNIFY_STOPS": True,
            "DELIMITER": "",
            "OUTPUT_ROUTES": routes_path,
            "OUTPUT_STOPS": stops_path,
            "OUTPUT_STOP_RELATIONS": csv_path,
        },
    )

    routes = load(routes_path)
    assert routes.featureCount() > 0
    assert all(f["frequency"] > 0 for f in routes.getFeatures())

    stops = load(stops_path)
    assert stops.featureCount() > 0
    assert all(f["count"] > 0 for f in stops.getFeatures())

    with open(csv_path, encoding="utf-8") as f:
        header = f.readline().strip()
    assert header == "stop_id,stop_name,similar_stop_id,similar_stop_name"
    relations = load(csv_path)
    expected = gtfs_parser.aggregate.Aggregator(
        gtfs_parser.GTFSFactory(gtfs_zip)
    ).read_stop_relations()
    assert relations.featureCount() == len(expected)
    assert relations.fields().names() == list(expected[0].keys())


def test_aggregate_frequency_filters(qgis_app, gtfs_zip, tmp_path):
    def total_frequency(parameters, name):
        routes_path = str(tmp_path / f"{name}.geojson")
        run(
            AggregateFrequencyAlgorithm(),
            {
                "INPUT": gtfs_zip,
                "UNIFY_STOPS": False,
                "OUTPUT_ROUTES": routes_path,
                "OUTPUT_STOPS": "memory:",
                "OUTPUT_STOP_RELATIONS": "memory:",
                **parameters,
            },
        )
        return sum(f["frequency"] for f in load(routes_path).getFeatures())

    unfiltered = total_frequency({}, "unfiltered")
    by_time = total_frequency(
        {"BEGIN_TIME": "07:00:00", "END_TIME": "09:00:00"}, "by_time"
    )
    by_date = total_frequency({"DATE": QDate(2021, 8, 2)}, "by_date")  # Monday
    assert 0 < by_time < unfiltered
    assert 0 < by_date < unfiltered


@pytest.mark.parametrize(
    "begin,end",
    [("07:00:00", ""), ("", "09:00:00"), ("7:00", "09:00:00")],
)
def test_aggregate_invalid_time(qgis_app, gtfs_zip, begin, end):
    alg = AggregateFrequencyAlgorithm().create()
    context = QgsProcessingContext()
    ok, _ = alg.checkParameterValues(
        {
            "INPUT": gtfs_zip,
            "BEGIN_TIME": begin,
            "END_TIME": end,
            "OUTPUT_ROUTES": "memory:",
            "OUTPUT_STOPS": "memory:",
            "OUTPUT_STOP_RELATIONS": "memory:",
        },
        context,
    )
    assert not ok


DPF_FEED = {
    "organization_id": "org1",
    "organization_name": "Org",
    "feed_id": "feed1",
    "feed_name": "Feed",
    "feed_pref_id": 1,
    "feed_license_id": "CC BY 4.0",
    "file_uid": "uid1",
    "file_from_date": "2024-04-01",
    "file_to_date": "2025-03-31",
    "file_url": "https://example.com/gtfs.zip",
}


@pytest.fixture
def get_feeds(monkeypatch):
    calls = []

    def fake(target_date, extent=None, pref=None):
        calls.append({"target_date": target_date, "extent": extent, "pref": pref})
        return [dict(DPF_FEED)]

    monkeypatch.setattr("processing_provider.search_japan_dpf.api.get_feeds", fake)
    return calls


def test_search_japan_dpf(qgis_app, get_feeds, tmp_path):
    output_path = str(tmp_path / "feeds.csv")
    run(
        SearchJapanDpfAlgorithm(),
        {
            "TARGET_DATE": QDate(2024, 4, 1),
            "EXTENT": QgsReferencedRectangle(
                QgsRectangle(141.0, 42.0, 144.0, 44.0),
                QgsCoordinateReferenceSystem("EPSG:4326"),
            ),
            "PREF": 1,  # 北海道
            "OUTPUT": output_path,
        },
    )
    assert get_feeds == [
        {"target_date": "2024-04-01", "extent": "141.0,42.0,144.0,44.0", "pref": 1}
    ]

    feeds = load(output_path)
    assert feeds.featureCount() == 1
    feed = next(feeds.getFeatures())
    assert feed["feed_name"] == "Feed"
    assert feed["feed_pref"] == "北海道"
    assert feed["file_url"] == "https://example.com/gtfs.zip"


def test_search_japan_dpf_extent_reprojected(qgis_app, get_feeds):
    # extent in another CRS is sent to the API in EPSG:4326 (xmin,ymin,xmax,ymax)
    run(
        SearchJapanDpfAlgorithm(),
        {
            "TARGET_DATE": QDate(2024, 4, 1),
            "EXTENT": QgsReferencedRectangle(
                QgsRectangle(15696048.2, 5160979.4, 16030006.7, 5465442.2),
                QgsCoordinateReferenceSystem("EPSG:3857"),
            ),
            "OUTPUT": "memory:",
        },
    )
    xmin, ymin, xmax, ymax = map(float, get_feeds[0]["extent"].split(","))
    assert xmin == pytest.approx(141.0, abs=1e-3)
    assert ymin == pytest.approx(42.0, abs=1e-3)
    assert xmax == pytest.approx(144.0, abs=1e-3)
    assert ymax == pytest.approx(44.0, abs=1e-3)


def test_search_japan_dpf_no_filter(qgis_app, get_feeds):
    run(
        SearchJapanDpfAlgorithm(),
        {"TARGET_DATE": QDate(2024, 4, 1), "OUTPUT": "memory:"},
    )
    assert get_feeds == [{"target_date": "2024-04-01", "extent": None, "pref": None}]


def test_search_japan_dpf_error(qgis_app, monkeypatch):
    def fail(*args, **kwargs):
        raise Exception("network error")

    monkeypatch.setattr("processing_provider.search_japan_dpf.api.get_feeds", fail)
    alg = SearchJapanDpfAlgorithm().create()
    context = QgsProcessingContext()
    feedback = QgsProcessingFeedback()
    _, ok = alg.run(
        {"TARGET_DATE": QDate(2024, 4, 1), "OUTPUT": "memory:"}, context, feedback
    )
    assert not ok
    assert "network error" in feedback.textLog()


def test_plugin_registers_provider(qgis_iface):
    from qgis.core import QgsApplication
    from qgis.PyQt.QtCore import QSettings

    from gtfs_go import GTFSGo

    QSettings().setValue("locale/userLocale", "en_US")
    plugin = GTFSGo(qgis_iface)
    plugin.initGui()
    registry = QgsApplication.processingRegistry()
    assert registry.algorithmById("gtfsgo:extractroutesandstops") is not None
    assert registry.algorithmById("gtfsgo:aggregatefrequency") is not None
    assert registry.algorithmById("gtfsgo:searchjapandpf") is not None
    plugin.unload()
    assert registry.providerById("gtfsgo") is None
