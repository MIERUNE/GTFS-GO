from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsSimpleMarkerSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsSvgMarkerSymbolLayer,
    QgsSymbol,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from gtfs_go_settings import (
    ROUTES_COLOR_LIST,
    ROUTES_LINE_WIDTH_MM,
    ROUTES_OUTLINE_COLOR,
    ROUTES_OUTLINE_WIDTH_MM,
    STOPS_ICON_HALO_WIDTH_MM,
    STOPS_ICON_SIZE_MM,
    STOPS_SVG_PATH,
)


def _get_random_color():
    import random

    random_index = random.randrange(0, len(ROUTES_COLOR_LIST) - 1, 1)
    return QColor(ROUTES_COLOR_LIST[random_index])


def _get_gtfs_route_color(route_color):
    if route_color is None:
        return None

    qcolor = QColor(f"#{route_color}")
    if not qcolor.isValid():
        return None
    return qcolor


class Renderer:
    def __init__(
        self,
        target_layer: QgsVectorLayer,
        target_field_name: str,
        use_random_colors: bool = False,
        target_label_field_name: str | None = None,
    ):
        self.target_layer = target_layer
        self.target_field_name = target_field_name
        self.use_random_colors = use_random_colors
        self.target_label_field_name = target_label_field_name

    def _is_point_layer(self):
        return (
            self.target_layer.geometryType() == QgsWkbTypes.GeometryType.PointGeometry
        )

    def _make_symbol(self, route_color=None):
        symbol = QgsSymbol.defaultSymbol(self.target_layer.geometryType())
        if self._is_point_layer():
            symbol_layer = QgsSvgMarkerSymbolLayer(STOPS_SVG_PATH)
            symbol_layer.setSize(STOPS_ICON_SIZE_MM)
            symbol.changeSymbolLayer(0, symbol_layer)
            icon_halo_layer = QgsSimpleMarkerSymbolLayer()
            icon_halo_layer.setColor(QColor("white"))
            icon_halo_layer.setSize(STOPS_ICON_SIZE_MM + STOPS_ICON_HALO_WIDTH_MM)
            icon_halo_layer.setStrokeStyle(Qt.PenStyle.NoPen)
            symbol.insertSymbolLayer(0, icon_halo_layer)
        else:
            line_layer = symbol.symbolLayer(0)
            line_layer.setPenJoinStyle(Qt.PenJoinStyle.RoundJoin)
            line_layer.setWidth(ROUTES_LINE_WIDTH_MM)
            symbol_color = _get_random_color()
            if not self.use_random_colors:
                gtfs_route_color = _get_gtfs_route_color(route_color)
                if gtfs_route_color is not None:
                    symbol_color = gtfs_route_color
            line_layer.setColor(symbol_color)
            outline_layer = symbol.symbolLayer(0).clone()
            outline_layer.setColor(QColor(ROUTES_OUTLINE_COLOR))
            outline_layer.setWidth(ROUTES_OUTLINE_WIDTH_MM)
            symbol.insertSymbolLayer(0, outline_layer)
        return symbol

    def _make_categories_by(self):
        categories = []
        route_color_by_value = {}
        label_by_value = {}
        target_field_values = set()
        for feature in self.target_layer.getFeatures():
            value = feature.attribute(self.target_field_name)
            target_field_values.add(value)
            candidate_color = feature.attribute("route_color")
            label_value = (
                feature.attribute(self.target_label_field_name)
                if self.target_label_field_name
                else value
            )
            if value not in route_color_by_value:
                route_color_by_value[value] = candidate_color
            elif (
                _get_gtfs_route_color(route_color_by_value[value]) is None
                and _get_gtfs_route_color(candidate_color) is not None
            ):
                route_color_by_value[value] = candidate_color
            if value not in label_by_value:
                label_by_value[value] = label_value
        for value in target_field_values:
            symbol = self._make_symbol(route_color_by_value.get(value))
            label = label_by_value.get(value, value)
            category = QgsRendererCategory(value, symbol, label)
            categories.append(category)
        return categories

    def make_renderer(self):
        if self._is_point_layer():
            renderer = QgsSingleSymbolRenderer(self._make_symbol())
        else:
            categories = self._make_categories_by()
            renderer = QgsCategorizedSymbolRenderer(self.target_field_name, categories)
        return renderer
