from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsClassificationJenks,
    QgsGraduatedSymbolRenderer,
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
    AGGREGATED_ROUTES_CLASS_COUNT,
    AGGREGATED_ROUTES_COLOR,
    AGGREGATED_ROUTES_MAX_WIDTH_MM,
    AGGREGATED_ROUTES_MIN_WIDTH_MM,
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

    # not for security purposes: only varies layer symbol colors
    return QColor(random.choice(ROUTES_COLOR_LIST))  # nosec B311


class Renderer:
    def __init__(self, target_layer: QgsVectorLayer, target_field_name: str):
        self.target_layer = target_layer
        self.target_field_name = target_field_name

    def _is_point_layer(self):
        return (
            self.target_layer.geometryType() == QgsWkbTypes.GeometryType.PointGeometry
        )

    def _make_symbol(self):
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
            line_layer.setColor(_get_random_color())
            outline_layer = symbol.symbolLayer(0).clone()
            outline_layer.setColor(QColor(ROUTES_OUTLINE_COLOR))
            outline_layer.setWidth(ROUTES_OUTLINE_WIDTH_MM)
            symbol.insertSymbolLayer(0, outline_layer)
        return symbol

    def _make_categories_by(self):
        categories = []
        # get all target field value with removing dupulicates
        target_field_values = set(
            [
                feature.attribute(self.target_field_name)
                for feature in self.target_layer.getFeatures()
            ]
        )
        for value in target_field_values:
            symbol = self._make_symbol()
            category = QgsRendererCategory(value, symbol, value)
            categories.append(category)
        return categories

    def make_renderer(self):
        if self._is_point_layer():
            renderer = QgsSingleSymbolRenderer(self._make_symbol())
        else:
            categories = self._make_categories_by()
            renderer = QgsCategorizedSymbolRenderer(self.target_field_name, categories)
        return renderer


def make_frequency_renderer(
    target_layer: QgsVectorLayer, target_field_name: str
) -> QgsGraduatedSymbolRenderer:
    """Graduated renderer varying line width by frequency, without expressions"""
    symbol = QgsSymbol.defaultSymbol(target_layer.geometryType())
    symbol.setColor(QColor(AGGREGATED_ROUTES_COLOR))
    symbol.symbolLayer(0).setPenCapStyle(Qt.PenCapStyle.RoundCap)

    renderer = QgsGraduatedSymbolRenderer(target_field_name)
    renderer.setSourceSymbol(symbol)
    renderer.setClassificationMethod(QgsClassificationJenks())
    renderer.updateClasses(target_layer, AGGREGATED_ROUTES_CLASS_COUNT)
    renderer.setGraduatedMethod(Qgis.GraduatedMethod.Size)
    renderer.setSymbolSizes(
        AGGREGATED_ROUTES_MIN_WIDTH_MM, AGGREGATED_ROUTES_MAX_WIDTH_MM
    )
    return renderer
