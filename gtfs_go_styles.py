import os

from qgis.core import QgsSymbolLayer, QgsVectorLayer

from gtfs_go_labeling import (
    get_labeling_for_aggregated_routes,
    get_labeling_for_stops,
)
from gtfs_go_renderer import Renderer, make_frequency_renderer
from gtfs_go_settings import STOPS_MINIMUM_VISIBLE_SCALE

_QML_DIR = os.path.dirname(__file__)


def style_routes_layer(layer: QgsVectorLayer) -> None:
    layer.setRenderer(Renderer(layer, "route_name").make_renderer())


def style_stops_layer(layer: QgsVectorLayer) -> None:
    layer.setLabelsEnabled(True)
    layer.setLabeling(get_labeling_for_stops("stop_name"))
    layer.setMinimumScale(STOPS_MINIMUM_VISIBLE_SCALE)
    layer.setScaleBasedVisibility(True)
    layer.setRenderer(Renderer(layer, "stop_name").make_renderer())


def style_aggregated_routes_layer(layer: QgsVectorLayer) -> None:
    layer.setLabelsEnabled(True)
    layer.setLabeling(get_labeling_for_aggregated_routes("frequency"))
    layer.setRenderer(make_frequency_renderer(layer, "frequency"))


def style_aggregated_stops_layer(
    layer: QgsVectorLayer, scale_stop_size: bool = False
) -> None:
    layer.loadNamedStyle(os.path.join(_QML_DIR, "aggregated_stops.qml"))
    dd_props = layer.renderer().symbol().symbolLayers()[0].dataDefinedProperties()
    if dd_props.hasProperty(QgsSymbolLayer.PropertySize):
        dd_props.property(QgsSymbolLayer.PropertySize).setActive(scale_stop_size)
