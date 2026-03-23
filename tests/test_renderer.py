import unittest

from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsVectorLayer
from qgis.PyQt.QtCore import QVariant

from gtfs_go_renderer import Renderer

from .utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()


def _make_route_layer(route_rows):
    layer = QgsVectorLayer("LineString?crs=EPSG:4326", "routes", "memory")
    provider = layer.dataProvider()
    provider.addAttributes(
        [
            QgsField("route_id", QVariant.String),
            QgsField("route_name", QVariant.String),
            QgsField("route_color", QVariant.String),
        ]
    )
    layer.updateFields()

    features = []
    for route_row in route_rows:
        if len(route_row) == 2:
            route_name, route_color = route_row
            route_id = route_name
        else:
            route_id, route_name, route_color = route_row
        feature = QgsFeature(layer.fields())
        feature.setAttributes([route_id, route_name, route_color])
        feature.setGeometry(
            QgsGeometry.fromPolylineXY([QgsPointXY(0.0, 0.0), QgsPointXY(1.0, 1.0)])
        )
        features.append(feature)

    provider.addFeatures(features)
    layer.updateExtents()
    return layer


def _route_symbol_color_name(renderer, route_name):
    categories = renderer.categories()
    category = next(
        category for category in categories if category.value() == route_name
    )
    return category.symbol().symbolLayer(1).color().name().upper()


class TestRenderer(unittest.TestCase):
    def test_use_gtfs_route_color_when_random_is_disabled(self):
        layer = _make_route_layer([("Route A", "FF0000")])
        renderer = Renderer(
            layer, "route_name", use_random_colors=False
        ).make_renderer()

        assert _route_symbol_color_name(renderer, "Route A") == "#FF0000"

    def test_always_use_random_when_random_is_enabled(self):
        layer = _make_route_layer([("Route A", "FF0000")])
        renderer = Renderer(layer, "route_name", use_random_colors=True).make_renderer()

        assert _route_symbol_color_name(renderer, "Route A") != "#FF0000"

    def test_fallback_to_random_when_color_missing_or_empty(self):
        layer = _make_route_layer([("Missing", None), ("Empty", "")])
        renderer = Renderer(
            layer, "route_name", use_random_colors=False
        ).make_renderer()

        assert _route_symbol_color_name(renderer, "Missing") != "#FF0000"
        assert _route_symbol_color_name(renderer, "Empty") != "#FF0000"

    def test_prefers_valid_gtfs_color_with_duplicate_category_values(self):
        layer = _make_route_layer([("Same Name", ""), ("Same Name", "F09EC0")])
        renderer = Renderer(
            layer, "route_name", use_random_colors=False
        ).make_renderer()

        assert _route_symbol_color_name(renderer, "Same Name") == "#F09EC0"

    def test_category_by_route_id_allows_distinct_colors_for_same_route_name(self):
        layer = _make_route_layer(
            [("A", "Shared Name", "F09EC0"), ("B", "Shared Name", "008000")]
        )
        renderer = Renderer(
            layer,
            "route_id",
            use_random_colors=False,
            target_label_field_name="route_name",
        ).make_renderer()

        assert _route_symbol_color_name(renderer, "A") == "#F09EC0"
        assert _route_symbol_color_name(renderer, "B") == "#008000"


if __name__ == "__main__":
    unittest.main()
