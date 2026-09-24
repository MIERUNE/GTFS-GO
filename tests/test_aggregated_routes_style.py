from qgis.core import (
    Qgis,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QMetaType

from gtfs_go_labeling import get_labeling_for_aggregated_routes
from gtfs_go_renderer import make_frequency_renderer
from gtfs_go_settings import AGGREGATED_ROUTES_WIDTH_CLASSES


def _make_routes_layer(frequencies):
    layer = QgsVectorLayer("LineString?crs=EPSG:4326", "routes", "memory")
    provider = layer.dataProvider()
    provider.addAttributes([QgsField("frequency", QMetaType.Type.Int)])
    layer.updateFields()
    features = []
    for i, frequency in enumerate(frequencies):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(
            QgsGeometry.fromPolylineXY([QgsPointXY(i, 0), QgsPointXY(i, 1)])
        )
        feature.setAttribute("frequency", frequency)
        features.append(feature)
    provider.addFeatures(features)
    return layer


def test_make_frequency_renderer():
    layer = _make_routes_layer([1, 2, 5, 10, 20, 50, 100, 200, 400])
    renderer = make_frequency_renderer(layer, "frequency")

    assert renderer.classAttribute() == "frequency"

    ranges = renderer.ranges()
    assert len(ranges) == len(AGGREGATED_ROUTES_WIDTH_CLASSES)
    widths = [r.symbol().width() for r in ranges]
    assert widths == [width for _, width in AGGREGATED_ROUTES_WIDTH_CLASSES]
    assert ranges[0].lowerValue() == 0
    for previous, current in zip(ranges, ranges[1:]):
        assert previous.upperValue() == current.lowerValue()

    assert renderer.symbolForValue(10).width() == widths[0]
    assert renderer.symbolForValue(11).width() == widths[1]
    assert renderer.symbolForValue(1000).width() == widths[-1]
    assert [r.label() for r in ranges] == [
        "0 - 10",
        "11 - 30",
        "31 - 60",
        "61 - 120",
        "121 - 240",
        "241 -",
    ]

    # line width must not rely on data-defined expressions
    for r in ranges:
        for symbol_layer in r.symbol().symbolLayers():
            assert not symbol_layer.dataDefinedProperties().hasActiveProperties()


def test_labeling_for_aggregated_routes():
    labeling = get_labeling_for_aggregated_routes("frequency")
    settings = labeling.settings()
    assert settings.fieldName == "frequency"
    assert settings.placement == Qgis.LabelPlacement.Line
    assert not settings.dataDefinedProperties().hasActiveProperties()
