import pytest
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
from gtfs_go_settings import (
    AGGREGATED_ROUTES_MAX_WIDTH_MM,
    AGGREGATED_ROUTES_MIN_WIDTH_MM,
)


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
    assert renderer.graduatedMethod() == Qgis.GraduatedMethod.Size

    ranges = renderer.ranges()
    assert len(ranges) > 1
    widths = [r.symbol().width() for r in ranges]
    assert widths == sorted(widths)
    assert widths[0] == pytest.approx(AGGREGATED_ROUTES_MIN_WIDTH_MM)
    assert widths[-1] == pytest.approx(AGGREGATED_ROUTES_MAX_WIDTH_MM)

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
