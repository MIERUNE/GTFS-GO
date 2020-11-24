from qgis.PyQt.QtCore import Qt
from qgis.core import *
from qgis.PyQt.QtGui import QColor

from .gtfs_viewer_settings import (
    STOPS_PNG_PATH,
    ROUTES_COLOR_LIST,
    ROUTES_LINE_WIDTH_MM,
    ROUTES_OUTLINE_WIDTH_MM,
    ROUTES_OUTLINE_COLOR
)


def get_random_color():
    import random
    random_index = random.randrange(0, len(ROUTES_COLOR_LIST) - 1, 1)
    return QColor(ROUTES_COLOR_LIST[random_index])


class Renderer:
    def __init__(self, target_layer, target_field_name):
        self.target_layer = target_layer
        self.target_field_name = target_field_name

    def is_point_layer(self):
        return self.target_layer.geometryType() == QgsWkbTypes.GeometryType.PointGeometry

    def make_symbol(self):
        symbol = QgsSymbol.defaultSymbol(self.target_layer.geometryType())
        if self.is_point_layer():
            symbol_layer = QgsRasterMarkerSymbolLayer(STOPS_PNG_PATH)
            symbol.changeSymbolLayer(0, symbol_layer)
        else:
            line_layer = symbol.symbolLayer(0)
            line_layer.setPenJoinStyle(Qt.RoundJoin)
            line_layer.setWidth(ROUTES_LINE_WIDTH_MM)
            line_layer.setColor(get_random_color())
            outline_layer = symbol.symbolLayer(0).clone()
            outline_layer.setColor(QColor(ROUTES_OUTLINE_COLOR))
            outline_layer.setWidth(ROUTES_OUTLINE_WIDTH_MM)
            symbol.insertSymbolLayer(0, outline_layer)
        return symbol

    def make_categories_by(self):
        categories = []
        # get all target field value with removing dupulicates
        target_field_values = set([feature.attribute(self.target_field_name)
                                   for feature in self.target_layer.getFeatures()])
        for value in target_field_values:
            symbol = self.make_symbol()
            category = QgsRendererCategory(value, symbol, value)
            categories.append(category)
        return categories

    def make_renderer(self):
        if self.is_point_layer():
            renderer = QgsSingleSymbolRenderer(self.make_symbol())
        else:
            categories = self.make_categories_by()
            renderer = QgsCategorizedSymbolRenderer(
                self.target_field_name, categories)
        return renderer
