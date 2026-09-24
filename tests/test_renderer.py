from typing import Optional

from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

from gtfs_go_renderer import Renderer


def _make_route_layer(
    route_rows: list[tuple[Optional[str], ...]], with_color_field: bool = True
) -> QgsVectorLayer:
    layer = QgsVectorLayer("LineString?crs=EPSG:4326", "routes", "memory")
    fields = [
        QgsField("route_id", QVariant.String),
        QgsField("route_name", QVariant.String),
    ]
    if with_color_field:
        fields.append(QgsField("route_color", QVariant.String))
    provider = layer.dataProvider()
    provider.addAttributes(fields)
    layer.updateFields()

    features = []
    for route_row in route_rows:
        feature = QgsFeature(layer.fields())
        feature.setAttributes(list(route_row))
        feature.setGeometry(
            QgsGeometry.fromPolylineXY([QgsPointXY(0.0, 0.0), QgsPointXY(1.0, 1.0)])
        )
        features.append(feature)
    provider.addFeatures(features)
    layer.updateExtents()
    return layer


def _route_symbol_color_name(renderer: QgsCategorizedSymbolRenderer, value: str) -> str:
    category = next(c for c in renderer.categories() if c.value() == value)
    # symbolLayer(0) is the outline, symbolLayer(1) is the route line
    return category.symbol().symbolLayer(1).color().name().upper()


def test_use_gtfs_route_color_when_present() -> None:
    layer = _make_route_layer([("A", "Route A", "FF0000")])
    renderer = Renderer(layer, "route_name").make_renderer()

    assert _route_symbol_color_name(renderer, "Route A") == "#FF0000"


def test_fallback_to_random_when_color_missing_or_invalid() -> None:
    layer = _make_route_layer(
        [
            ("A", "Missing", None),
            ("B", "Empty", ""),
            ("C", "Invalid", "ZZZZZZ"),
        ]
    )
    renderer = Renderer(layer, "route_name").make_renderer()

    assert len(renderer.categories()) == 3
    for value in ("Missing", "Empty", "Invalid"):
        assert _route_symbol_color_name(renderer, value) != "#000000"


def test_fallback_to_random_when_color_field_absent() -> None:
    layer = _make_route_layer([("A", "Route A")], with_color_field=False)
    renderer = Renderer(layer, "route_name").make_renderer()

    assert len(renderer.categories()) == 1


def test_prefers_valid_gtfs_color_with_duplicate_category_values() -> None:
    layer = _make_route_layer([("A", "Same Name", ""), ("B", "Same Name", "F09EC0")])
    renderer = Renderer(layer, "route_name").make_renderer()

    assert len(renderer.categories()) == 1
    assert _route_symbol_color_name(renderer, "Same Name") == "#F09EC0"


def test_keeps_first_valid_gtfs_color_with_duplicate_category_values() -> None:
    layer = _make_route_layer(
        [("A", "Same Name", "F09EC0"), ("B", "Same Name", "008000")]
    )
    renderer = Renderer(layer, "route_name").make_renderer()

    assert _route_symbol_color_name(renderer, "Same Name") == "#F09EC0"
