import os
import shutil

import pytest
from qgis.core import QgsProject
from qgis.PyQt.QtCore import QDate

from gtfs_go_dialog import GTFSGoDialog

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "gtfs_parser", "tests", "fixture"
)
LAYER_NAMES = {"routes", "stops", "aggregated_routes", "aggregated_stops", "result"}


@pytest.fixture
def gtfs_zip(tmp_path):
    return shutil.make_archive(str(tmp_path / "gtfs"), "zip", FIXTURE_DIR)


@pytest.fixture
def execute(qgis_iface, gtfs_zip):
    """Run the dialog with a local zip, return added layers by name"""

    def _execute(output_dir=""):
        dialog = GTFSGoDialog(qgis_iface)
        dialog.zipFileWidget.setFilePath(gtfs_zip)
        dialog.outputDirFileWidget.setFilePath(output_dir)
        dialog.aggregateCheckbox.setChecked(True)
        # date filter is on by default (today), use a service day of the fixture
        dialog.filterByDateDateEdit.setDate(QDate(2021, 8, 2))
        dialog.refresh()
        assert dialog.pushButton.isEnabled()
        dialog.execution()
        return {
            layer.name(): layer for layer in QgsProject.instance().mapLayers().values()
        }

    yield _execute
    QgsProject.instance().clear()


def test_dialog(qgis_iface):
    """Test the dialog."""
    dialog = GTFSGoDialog(qgis_iface)

    assert dialog.isVisible() is False
    dialog.show()
    assert dialog.isVisible() is True
    dialog.close()
    assert dialog.isVisible() is False


def test_japan_dpf_search(qgis_iface, monkeypatch):
    feed = {
        "organization_id": "org1",
        "organization_name": "Org",
        "feed_id": "feed1",
        "feed_name": "Feed",
        "feed_pref_id": 1,
        "file_uid": "uid1",
        "file_url": "https://example.com/gtfs.zip",
    }
    monkeypatch.setattr(
        "processing_provider.search_japan_dpf.api.get_feeds",
        lambda *args, **kwargs: [dict(feed)],
    )
    dialog = GTFSGoDialog(qgis_iface)
    dialog.japan_dpf_search()

    assert dialog.japanDpfResultTableView.model().rowCount() == 1
    row = dialog.get_selected_row_data_in_japan_dpf_table(0)
    assert row["organization"] == "Org"
    assert row["feed"] == "Feed"
    assert row["pref"] == "北海道"
    assert row["file_url"] == "https://example.com/gtfs.zip"


def test_dialog_translated(qgis_iface):
    import i18n

    i18n.load("ja")
    try:
        dialog = GTFSGoDialog(qgis_iface)
        assert dialog.pushButton.text() == "QGISに読み込む"
        assert dialog.repositoryCombobox.itemText(0) == "プリセット"
    finally:
        i18n.load("en")


def test_execution_without_output_dir(execute):
    layers = execute()

    assert set(layers) == LAYER_NAMES
    for layer in layers.values():
        assert layer.isValid()
        assert layer.providerType() == "memory"
        assert layer.featureCount() > 0
    group = QgsProject.instance().layerTreeRoot().findGroup("gtfs")
    assert [child.name() for child in group.children()] == [
        "result",
        "aggregated_stops",
        "aggregated_routes",
        "stops",
        "routes",
    ]


def test_execution_with_output_dir(execute, tmp_path):
    output_dir = tmp_path / "output"
    layers = execute(str(output_dir))

    assert set(layers) == LAYER_NAMES
    for layer in layers.values():
        assert layer.isValid()
        assert layer.providerType() == "ogr"
        assert layer.featureCount() > 0
    assert sorted(os.listdir(output_dir / "gtfs")) == [
        "aggregated_routes.geojson",
        "aggregated_stops.geojson",
        "result.csv",
        "routes.geojson",
        "stops.geojson",
    ]
