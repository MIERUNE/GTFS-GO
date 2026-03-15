from __future__ import annotations

import os

import sip
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPalLayerSettings,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingLayerPostProcessorInterface,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
    QgsRendererCategory,
    QgsSimpleMarkerSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsSvgMarkerSymbolLayer,
    QgsSymbol,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QCoreApplication, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont

from ..gtfs_duckdb import init_gtfs_connection

_STYLE_DIR = os.path.join(os.path.dirname(__file__), "..", "style")
_STOPS_SVG_PATH = os.path.join(_STYLE_DIR, "busstop.svg")


class _StopsStylePostProcessor(QgsProcessingLayerPostProcessorInterface):
    _instances: list = []

    @staticmethod
    def create() -> "_StopsStylePostProcessor":
        inst = _StopsStylePostProcessor()
        sip.transferto(inst, None)
        _StopsStylePostProcessor._instances.append(inst)
        return inst

    def postProcessLayer(self, layer, context, feedback):
        # SVG marker with white halo
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        svg_layer = QgsSvgMarkerSymbolLayer(_STOPS_SVG_PATH)
        svg_layer.setSize(7.0)
        symbol.changeSymbolLayer(0, svg_layer)
        halo_layer = QgsSimpleMarkerSymbolLayer()
        halo_layer.setColor(QColor("white"))
        halo_layer.setSize(9.0)
        halo_layer.setStrokeStyle(Qt.PenStyle.NoPen)
        symbol.insertSymbolLayer(0, halo_layer)
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))

        # Labeling
        text_format = QgsTextFormat()
        text_format.setFont(QFont("Arial", 10))
        text_format.setSize(10)
        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(1.0)
        buf.setColor(QColor("white"))
        text_format.setBuffer(buf)
        pal = QgsPalLayerSettings()
        pal.setFormat(text_format)
        pal.fieldName = "stop_name"
        pal.placement = QgsPalLayerSettings.Placement.OrderedPositionsAroundPoint
        pal.dist = 2.0
        pal.scaleVisibility = True
        pal.minimumScale = 100000
        pal.enabled = True
        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()
        _StopsStylePostProcessor._instances.remove(self)


_ROUTES_COLOR_LIST = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
    "#ff9896",
    "#c5b0d5",
]


class _RoutesStylePostProcessor(QgsProcessingLayerPostProcessorInterface):
    _instances: list = []

    def __init__(self, field_name: str):
        super().__init__()
        self.field_name = field_name

    @staticmethod
    def create(field_name: str) -> "_RoutesStylePostProcessor":
        inst = _RoutesStylePostProcessor(field_name)
        sip.transferto(inst, None)
        _RoutesStylePostProcessor._instances.append(inst)
        return inst

    def _make_symbol(self, color: QColor):
        symbol = QgsSymbol.defaultSymbol(self._geom_type)
        line_layer = symbol.symbolLayer(0)
        line_layer.setColor(color)
        line_layer.setWidth(0.8)
        line_layer.setPenJoinStyle(Qt.PenJoinStyle.RoundJoin)
        outline = line_layer.clone()
        outline.setColor(QColor(30, 30, 30))
        outline.setWidth(1.2)
        symbol.insertSymbolLayer(0, outline)
        return symbol

    def postProcessLayer(self, layer, context, feedback):
        self._geom_type = layer.geometryType()
        field_idx = layer.fields().indexOf(self.field_name)
        values = sorted(layer.uniqueValues(field_idx))
        categories = []
        for i, value in enumerate(values):
            color = QColor(_ROUTES_COLOR_LIST[i % len(_ROUTES_COLOR_LIST)])
            symbol = self._make_symbol(color)
            categories.append(QgsRendererCategory(value, symbol, str(value)))
        renderer = QgsCategorizedSymbolRenderer(self.field_name, categories)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        _RoutesStylePostProcessor._instances.remove(self)


_QUERY_WITH_SHAPES = """
    WITH shape_geom AS (
        SELECT
            shape_id,
            ST_MakeLine(
                LIST(
                    ST_Point(shape_pt_lon, shape_pt_lat)
                    ORDER BY shape_pt_sequence
                )
            ) AS geom
        FROM shapes
        GROUP BY shape_id
    )
    SELECT shape_id, ST_AsText(geom) AS wkt
    FROM shape_geom
"""

_QUERY_WITHOUT_SHAPES = """
    WITH trip_lines AS (
        SELECT
            st.trip_id,
            ST_MakeLine(
                LIST(sg.geom ORDER BY st.stop_sequence)
            ) AS geom
        FROM stop_times st
        JOIN stops_geo sg ON st.stop_id = sg.stop_id
        GROUP BY st.trip_id
    )
    SELECT trip_id, ST_AsText(geom) AS wkt
    FROM trip_lines
"""

_CRS_4326 = QgsCoordinateReferenceSystem.fromEpsgId(4326)


class GtfsExtractAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    APPLY_STYLE = "APPLY_STYLE"
    OUTPUT_STOPS = "OUTPUT_STOPS"
    OUTPUT_ROUTES = "OUTPUT_ROUTES"

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return GtfsExtractAlgorithm()

    def name(self):
        return "extract"

    def displayName(self):
        return self.tr("Extract GTFS Stops / Routes")

    def group(self):
        return None

    def groupId(self):
        return None

    def shortHelpString(self) -> str:
        return self.tr(
            "Extracts stops and/or routes from GTFS CSV files. "
            "Both outputs are optional — at least one must be specified."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT,
                self.tr("GTFS Folder"),
                behavior=QgsProcessingParameterFile.Folder,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.APPLY_STYLE,
                self.tr("Apply Style"),
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_STOPS,
                self.tr("Stops"),
                QgsProcessing.TypeVectorPoint,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_ROUTES,
                self.tr("Routes"),
                QgsProcessing.TypeVectorLine,
                optional=True,
            )
        )

    def processAlgorithm(
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        folder = self.parameterAsString(parameters, self.INPUT, context)
        if not folder:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.INPUT)
            )

        apply_style = self.parameterAsBool(parameters, self.APPLY_STYLE, context)

        want_stops = self.OUTPUT_STOPS in parameters and parameters[self.OUTPUT_STOPS]
        want_routes = (
            self.OUTPUT_ROUTES in parameters and parameters[self.OUTPUT_ROUTES]
        )

        if not want_stops and not want_routes:
            raise QgsProcessingException(
                self.tr("At least one output (Stops or Routes) must be specified.")
            )

        gtfs = init_gtfs_connection(folder, feedback)
        results: dict = {}
        try:
            if want_stops:
                dest_id = self._extract_stops(parameters, context, feedback, gtfs.conn)
                results[self.OUTPUT_STOPS] = dest_id
                if apply_style and context.willLoadLayerOnCompletion(dest_id):
                    context.layerToLoadOnCompletionDetails(dest_id).setPostProcessor(
                        _StopsStylePostProcessor.create()
                    )

            if feedback.isCanceled():
                return results

            if want_routes:
                id_field_name = "shape_id" if gtfs.has_shapes else "trip_id"
                dest_id = self._extract_routes(
                    parameters, context, feedback, gtfs.conn, gtfs.has_shapes
                )
                results[self.OUTPUT_ROUTES] = dest_id
                if apply_style and context.willLoadLayerOnCompletion(dest_id):
                    context.layerToLoadOnCompletionDetails(dest_id).setPostProcessor(
                        _RoutesStylePostProcessor.create(id_field_name)
                    )
        finally:
            gtfs.conn.close()

        return results

    def _extract_stops(self, parameters, context, feedback, conn) -> str:
        fields = QgsFields()
        fields.append(QgsField("stop_id", QVariant.String))
        fields.append(QgsField("stop_name", QVariant.String))

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_STOPS,
            context,
            fields,
            QgsWkbTypes.Point,
            _CRS_4326,
        )
        if sink is None:
            raise QgsProcessingException(
                self.invalidSinkError(parameters, self.OUTPUT_STOPS)
            )

        result = conn.execute("""
            SELECT stop_id, stop_name, ST_AsText(geom) AS wkt
            FROM stops_geo
        """).fetchall()

        total = len(result)
        for i, (stop_id, stop_name, wkt) in enumerate(result):
            if feedback.isCanceled():
                break

            feat = QgsFeature()
            feat.setFields(fields, initAttributes=True)
            feat.setAttribute("stop_id", stop_id)
            feat.setAttribute("stop_name", stop_name)
            feat.setGeometry(QgsGeometry.fromWkt(wkt))
            sink.addFeature(feat, QgsFeatureSink.FastInsert)

            if (i + 1) % 500 == 0:
                feedback.setProgress(int((i + 1) / total * 50))

        feedback.pushInfo(f"Extracted {total} stops.")
        return dest_id

    def _extract_routes(self, parameters, context, feedback, conn, has_shapes) -> str:
        if has_shapes:
            feedback.pushInfo("shapes.txt found: building routes from shape points.")
            id_field_name = "shape_id"
            query = _QUERY_WITH_SHAPES
        else:
            feedback.pushInfo(
                "shapes.txt not found: building routes from stop sequences."
            )
            id_field_name = "trip_id"
            query = _QUERY_WITHOUT_SHAPES

        fields = QgsFields()
        fields.append(QgsField(id_field_name, QVariant.String))

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_ROUTES,
            context,
            fields,
            QgsWkbTypes.LineString,
            _CRS_4326,
        )
        if sink is None:
            raise QgsProcessingException(
                self.invalidSinkError(parameters, self.OUTPUT_ROUTES)
            )

        result = conn.execute(query).fetchall()

        total = len(result)
        for i, (id_value, wkt) in enumerate(result):
            if feedback.isCanceled():
                break

            feat = QgsFeature()
            feat.setFields(fields, initAttributes=True)
            feat.setAttribute(id_field_name, id_value)
            feat.setGeometry(QgsGeometry.fromWkt(wkt))
            sink.addFeature(feat, QgsFeatureSink.FastInsert)

            if (i + 1) % 100 == 0:
                feedback.setProgress(50 + int((i + 1) / total * 50))

        feedback.pushInfo(f"Extracted {total} route lines (by {id_field_name}).")
        return dest_id
