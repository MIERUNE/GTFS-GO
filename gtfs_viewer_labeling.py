from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import *


def get_labeling_for_stops(target_field_name="stop_name"):
    text_format = QgsTextFormat()
    text_format.setFont(QFont("Arial", 9))
    text_format.setSize(9)
    buffer_settings = QgsTextBufferSettings()
    buffer_settings.setEnabled(True)
    buffer_settings.setSize(1)
    buffer_settings.setColor(QColor("white"))
    text_format.setBuffer(buffer_settings)
    pal_layer = QgsPalLayerSettings()
    pal_layer.setFormat(text_format)
    pal_layer.fieldName = target_field_name
    pal_layer.placement = QgsPalLayerSettings.Placement.OrderedPositionsAroundPoint
    pal_layer.dist = 2.2
    pal_layer.scaleVisibility = True
    pal_layer.minimumScale = 50000
    pal_layer.enabled = True
    labeling = QgsVectorLayerSimpleLabeling(pal_layer)
    return labeling
