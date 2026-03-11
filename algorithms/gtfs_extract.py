from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QCoreApplication, QVariant

from ..gtfs_duckdb import init_gtfs_connection

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
                results[self.OUTPUT_STOPS] = self._extract_stops(
                    parameters, context, feedback, gtfs.conn
                )

            if feedback.isCanceled():
                return results

            if want_routes:
                results[self.OUTPUT_ROUTES] = self._extract_routes(
                    parameters, context, feedback, gtfs.conn, gtfs.has_shapes
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
