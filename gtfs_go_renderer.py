from typing import Any, Optional

from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsFeatureRenderer,
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


def _get_random_color() -> QColor:
    import random

    # not for security purposes: only varies layer symbol colors
    return QColor(random.choice(ROUTES_COLOR_LIST))  # nosec B311


def _get_gtfs_route_color(route_color: Any) -> Optional[QColor]:
    """Return QColor from GTFS route_color (hex without '#'), or None if invalid"""
    if not route_color or not isinstance(route_color, str):
        return None
    qcolor = QColor(f"#{route_color}")
    if not qcolor.isValid():
        return None
    return qcolor


class Renderer:
    def __init__(self, target_layer: QgsVectorLayer, target_field_name: str):
        self.target_layer = target_layer
        self.target_field_name = target_field_name

    def _is_point_layer(self) -> bool:
        return (
            self.target_layer.geometryType() == QgsWkbTypes.GeometryType.PointGeometry
        )

    def _make_symbol(self, route_color: Any = None) -> QgsSymbol:
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
            line_color = _get_gtfs_route_color(route_color)
            if line_color is None:
                line_color = _get_random_color()
            line_layer.setColor(line_color)
            outline_layer = symbol.symbolLayer(0).clone()
            outline_layer.setColor(QColor(ROUTES_OUTLINE_COLOR))
            outline_layer.setWidth(ROUTES_OUTLINE_WIDTH_MM)
            symbol.insertSymbolLayer(0, outline_layer)
        return symbol

    def _make_categories_by(self) -> list[QgsRendererCategory]:
        categories: list[QgsRendererCategory] = []
        # route_color is absent when the GTFS feed does not provide it
        color_field_index = self.target_layer.fields().indexOf("route_color")
        # get all target field values with removing duplicates,
        # keeping the first valid route_color for each value
        route_color_by_value: dict[Any, Any] = {}
        for feature in self.target_layer.getFeatures():
            value = feature.attribute(self.target_field_name)
            route_color = (
                feature.attribute(color_field_index) if color_field_index >= 0 else None
            )
            if _get_gtfs_route_color(route_color_by_value.get(value)) is None:
                route_color_by_value[value] = route_color
        for value, route_color in route_color_by_value.items():
            symbol = self._make_symbol(route_color)
            category = QgsRendererCategory(value, symbol, value)
            categories.append(category)
        return categories

    def make_renderer(self) -> QgsFeatureRenderer:
        if self._is_point_layer():
            renderer = QgsSingleSymbolRenderer(self._make_symbol())
        else:
            categories = self._make_categories_by()
            renderer = QgsCategorizedSymbolRenderer(self.target_field_name, categories)
        return renderer
