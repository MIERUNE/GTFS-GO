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
from gtfs_go_renderer import frequency_to_width, make_frequency_renderer


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
    assert len(ranges) > 1
    widths = [r.symbol().width() for r in ranges]
    assert widths == sorted(widths)
    # each class width lies within the expression's widths at its bounds
    for r, width in zip(ranges, widths):
        assert (
            frequency_to_width(r.lowerValue())
            <= width
            <= frequency_to_width(r.upperValue())
        )

    # line width must not rely on data-defined expressions
    for r in ranges:
        for symbol_layer in r.symbol().symbolLayers():
            assert not symbol_layer.dataDefinedProperties().hasActiveProperties()


def test_frequency_to_width():
    assert frequency_to_width(0) == pytest.approx(0.05)
    assert frequency_to_width(1) == pytest.approx(0.25)
    assert frequency_to_width(100) == pytest.approx(0.05 + 100**0.6 * 0.2)


def test_labeling_for_aggregated_routes():
    labeling = get_labeling_for_aggregated_routes("frequency")
    settings = labeling.settings()
    assert settings.fieldName == "frequency"
    assert settings.placement == Qgis.LabelPlacement.Line
    assert not settings.dataDefinedProperties().hasActiveProperties()
