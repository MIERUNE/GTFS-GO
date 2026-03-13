from __future__ import annotations

import os
import re

import sip
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
    QgsProcessingLayerPostProcessorInterface,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QCoreApplication, QVariant

from ..gtfs_duckdb import init_gtfs_connection

_STYLE_DIR = os.path.join(os.path.dirname(__file__), "..", "style")


class _QmlStylePostProcessor(QgsProcessingLayerPostProcessorInterface):
    _instances: list = []

    def __init__(self, qml_path: str):
        super().__init__()
        self.qml_path = qml_path

    @staticmethod
    def create(qml_path: str) -> "_QmlStylePostProcessor":
        inst = _QmlStylePostProcessor(qml_path)
        sip.transferto(inst, None)
        _QmlStylePostProcessor._instances.append(inst)
        return inst

    def postProcessLayer(self, layer, context, feedback):
        layer.loadNamedStyle(self.qml_path)
        layer.triggerRepaint()

_CRS_4326 = QgsCoordinateReferenceSystem.fromEpsgId(4326)


def _stop_grouping_cte(delimiter: str, max_distance: float) -> str:
    escaped = re.escape(delimiter)
    return f"""
    parent_station_groups AS (
      SELECT
        parent_station AS similar_stop_id,
        stop_id
      FROM stops_geo
      WHERE parent_station IS NOT NULL
        AND parent_station != ''
        AND EXISTS (SELECT 1 FROM stops_geo s2 WHERE s2.stop_id = stops_geo.parent_station)
        AND (location_type = 0 OR location_type IS NULL)
    ),

    solo_stops AS (
      SELECT *
      FROM stops_geo
      WHERE NOT EXISTS (
        SELECT 1 FROM parent_station_groups p WHERE p.stop_id = stops_geo.stop_id
      )
      AND (location_type = 0 OR location_type IS NULL)
    ),

    id_prefix_groups AS (
      SELECT
        REGEXP_EXTRACT(stop_id, '^([^{escaped}]+)') AS similar_stop_id,
        stop_id
      FROM solo_stops
      WHERE REGEXP_EXTRACT(stop_id, '^([^{escaped}]+)') != stop_id
    ),

    remaining_stops AS (
      SELECT *
      FROM solo_stops
      WHERE NOT EXISTS (
        SELECT 1 FROM id_prefix_groups ip WHERE ip.stop_id = solo_stops.stop_id
      )
    ),

    proximity_groups AS (
      SELECT
        a.stop_id AS stop_id,
        MIN(b.stop_id) AS similar_stop_id
      FROM remaining_stops a
      JOIN remaining_stops b ON a.stop_name = b.stop_name
      WHERE (POWER(a.stop_lon - b.stop_lon, 2) + POWER(a.stop_lat - b.stop_lat, 2)) <= POWER({max_distance}, 2)
      GROUP BY a.stop_id
    ),

    all_stop_relations AS (
      SELECT stop_id, similar_stop_id FROM parent_station_groups
      UNION ALL
      SELECT stop_id, similar_stop_id FROM id_prefix_groups
      UNION ALL
      SELECT stop_id, similar_stop_id FROM proximity_groups
    ),

    similar_stop_attributes AS (
      SELECT
        r.similar_stop_id,
        MIN(s.stop_name) AS similar_stop_name,
        AVG(s.stop_lon) AS stop_lon,
        AVG(s.stop_lat) AS stop_lat,
        COUNT(*) AS stop_count,
        ST_Point(AVG(s.stop_lon), AVG(s.stop_lat)) AS geom
      FROM all_stop_relations r
      JOIN stops_geo s ON r.stop_id = s.stop_id
      GROUP BY r.similar_stop_id
    )"""


def _aggregated_stops_query(delimiter: str, max_distance: float) -> str:
    return f"""
    WITH {_stop_grouping_cte(delimiter, max_distance)},

    stop_trip_counts AS (
      SELECT stop_id, COUNT(*) AS trip_count
      FROM stop_times
      GROUP BY stop_id
    ),

    similar_stop_trip_counts AS (
      SELECT
        r.similar_stop_id,
        SUM(stc.trip_count) AS total_trip_count
      FROM all_stop_relations r
      JOIN stop_trip_counts stc ON r.stop_id = stc.stop_id
      GROUP BY r.similar_stop_id
    ),

    aggregated AS (
      SELECT
        a.similar_stop_id,
        a.similar_stop_name,
        a.stop_count,
        COALESCE(stc.total_trip_count, 0) AS trip_count,
        a.geom
      FROM similar_stop_attributes a
      LEFT JOIN similar_stop_trip_counts stc ON a.similar_stop_id = stc.similar_stop_id
    )

    SELECT
      similar_stop_id,
      similar_stop_name,
      stop_count,
      trip_count,
      ST_AsText(geom) AS wkt
    FROM aggregated
    """


def _aggregated_segments_query(delimiter: str, max_distance: float) -> str:
    return f"""
    WITH {_stop_grouping_cte(delimiter, max_distance)},

    stop_times_with_similar AS (
      SELECT
        st.trip_id,
        st.stop_sequence,
        r.similar_stop_id
      FROM stop_times st
      JOIN all_stop_relations r ON st.stop_id = r.stop_id
    ),

    next_stops AS (
      SELECT
        trip_id,
        similar_stop_id AS from_similar_stop,
        LEAD(similar_stop_id) OVER (
          PARTITION BY trip_id ORDER BY stop_sequence
        ) AS to_similar_stop
      FROM stop_times_with_similar
    ),

    similar_edges AS (
      SELECT
        from_similar_stop,
        to_similar_stop,
        COUNT(*) AS trip_count
      FROM next_stops
      WHERE to_similar_stop IS NOT NULL
        AND from_similar_stop != to_similar_stop
      GROUP BY from_similar_stop, to_similar_stop
    ),

    trip_route_info AS (
      SELECT t.trip_id, r.route_id, r.route_short_name, r.route_long_name
      FROM trips t
      JOIN routes r ON t.route_id = r.route_id
    ),

    segment_routes AS (
      SELECT
        ns.from_similar_stop,
        ns.to_similar_stop,
        tri.route_id,
        MIN(tri.route_short_name) AS route_short_name,
        MIN(tri.route_long_name) AS route_long_name,
        COUNT(*) AS route_trip_count
      FROM next_stops ns
      JOIN trip_route_info tri ON ns.trip_id = tri.trip_id
      WHERE ns.to_similar_stop IS NOT NULL
        AND ns.from_similar_stop != ns.to_similar_stop
      GROUP BY ns.from_similar_stop, ns.to_similar_stop, tri.route_id
    ),

    segment_route_list AS (
      SELECT
        from_similar_stop,
        to_similar_stop,
        STRING_AGG(route_short_name, ',') AS route_short_names,
        STRING_AGG(route_long_name, ',') AS route_long_names
      FROM segment_routes
      GROUP BY from_similar_stop, to_similar_stop
    ),

    similar_geometries AS (
      SELECT
        e.from_similar_stop,
        e.to_similar_stop,
        e.trip_count,
        srl.route_short_names,
        srl.route_long_names,
        sf.similar_stop_name AS from_stop_name,
        st_attr.similar_stop_name AS to_stop_name,
        ST_MakeLine(ARRAY[sf.geom, st_attr.geom]) AS geom
      FROM similar_edges e
      JOIN similar_stop_attributes sf ON sf.similar_stop_id = e.from_similar_stop
      JOIN similar_stop_attributes st_attr ON st_attr.similar_stop_id = e.to_similar_stop
      LEFT JOIN segment_route_list srl
        ON e.from_similar_stop = srl.from_similar_stop
        AND e.to_similar_stop = srl.to_similar_stop
    )

    SELECT
      from_similar_stop,
      to_similar_stop,
      from_stop_name,
      to_stop_name,
      trip_count,
      route_short_names,
      route_long_names,
      ST_AsText(geom) AS wkt
    FROM similar_geometries
    """


class GtfsAggregateAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    DELIMITER = "DELIMITER"
    MAX_DISTANCE = "MAX_DISTANCE"
    APPLY_STYLE = "APPLY_STYLE"
    OUTPUT_STOPS = "OUTPUT_STOPS"
    OUTPUT_SEGMENTS = "OUTPUT_SEGMENTS"

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return GtfsAggregateAlgorithm()

    def name(self):
        return "aggregate"

    def displayName(self):
        return self.tr("Aggregate GTFS Stops / Segments")

    def group(self):
        return None

    def groupId(self):
        return None

    def shortHelpString(self) -> str:
        return self.tr(
            "Aggregates GTFS stops by grouping similar stops "
            "(parent station, ID prefix, proximity) and computes "
            "segment-level trip counts between aggregated stops. "
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
            QgsProcessingParameterString(
                self.DELIMITER,
                self.tr("Stop ID Delimiter"),
                defaultValue="_",
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_DISTANCE,
                self.tr("Proximity Max Distance (degrees)"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.003,
                optional=True,
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
                self.tr("Aggregated Stops"),
                QgsProcessing.TypeVectorPoint,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_SEGMENTS,
                self.tr("Aggregated Segments"),
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

        delimiter = self.parameterAsString(parameters, self.DELIMITER, context) or "_"
        max_distance = (
            self.parameterAsDouble(parameters, self.MAX_DISTANCE, context) or 0.003
        )
        apply_style = self.parameterAsBool(parameters, self.APPLY_STYLE, context)

        want_stops = self.OUTPUT_STOPS in parameters and parameters[self.OUTPUT_STOPS]
        want_segments = (
            self.OUTPUT_SEGMENTS in parameters and parameters[self.OUTPUT_SEGMENTS]
        )

        if not want_stops and not want_segments:
            raise QgsProcessingException(
                self.tr(
                    "At least one output (Aggregated Stops or Aggregated Segments) "
                    "must be specified."
                )
            )

        gtfs = init_gtfs_connection(folder, feedback)
        results: dict = {}
        try:
            if want_stops:
                dest_id = self._aggregate_stops(
                    parameters, context, feedback, gtfs.conn, delimiter, max_distance
                )
                results[self.OUTPUT_STOPS] = dest_id
                if apply_style and context.willLoadLayerOnCompletion(dest_id):
                    qml = os.path.join(_STYLE_DIR, "aggregated_stops.qml")
                    context.layerToLoadOnCompletionDetails(
                        dest_id
                    ).setPostProcessor(_QmlStylePostProcessor.create(qml))

            if feedback.isCanceled():
                return results

            if want_segments:
                dest_id = self._aggregate_segments(
                    parameters, context, feedback, gtfs.conn, delimiter, max_distance
                )
                results[self.OUTPUT_SEGMENTS] = dest_id
                if apply_style and context.willLoadLayerOnCompletion(dest_id):
                    qml = os.path.join(_STYLE_DIR, "aggregated_routes.qml")
                    context.layerToLoadOnCompletionDetails(
                        dest_id
                    ).setPostProcessor(_QmlStylePostProcessor.create(qml))
        finally:
            gtfs.conn.close()

        return results

    def _aggregate_stops(
        self, parameters, context, feedback, conn, delimiter, max_distance
    ) -> str:
        fields = QgsFields()
        fields.append(QgsField("similar_stop_id", QVariant.String))
        fields.append(QgsField("similar_stop_name", QVariant.String))
        fields.append(QgsField("stop_count", QVariant.Int))
        fields.append(QgsField("trip_count", QVariant.Int))

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

        query = _aggregated_stops_query(delimiter, max_distance)
        result = conn.execute(query).fetchall()

        total = len(result)
        for i, (stop_id, stop_name, stop_count, trip_count, wkt) in enumerate(result):
            if feedback.isCanceled():
                break

            feat = QgsFeature()
            feat.setFields(fields, initAttributes=True)
            feat.setAttribute("similar_stop_id", stop_id)
            feat.setAttribute("similar_stop_name", stop_name)
            feat.setAttribute("stop_count", stop_count)
            feat.setAttribute("trip_count", trip_count)
            feat.setGeometry(QgsGeometry.fromWkt(wkt))
            sink.addFeature(feat, QgsFeatureSink.FastInsert)

            if (i + 1) % 500 == 0:
                feedback.setProgress(int((i + 1) / total * 50))

        feedback.pushInfo(f"Aggregated into {total} stop groups.")
        return dest_id

    def _aggregate_segments(
        self, parameters, context, feedback, conn, delimiter, max_distance
    ) -> str:
        fields = QgsFields()
        fields.append(QgsField("from_stop_id", QVariant.String))
        fields.append(QgsField("to_stop_id", QVariant.String))
        fields.append(QgsField("from_stop_name", QVariant.String))
        fields.append(QgsField("to_stop_name", QVariant.String))
        fields.append(QgsField("trip_count", QVariant.Int))
        fields.append(QgsField("route_short_names", QVariant.String))
        fields.append(QgsField("route_long_names", QVariant.String))

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_SEGMENTS,
            context,
            fields,
            QgsWkbTypes.LineString,
            _CRS_4326,
        )
        if sink is None:
            raise QgsProcessingException(
                self.invalidSinkError(parameters, self.OUTPUT_SEGMENTS)
            )

        query = _aggregated_segments_query(delimiter, max_distance)
        result = conn.execute(query).fetchall()

        total = len(result)
        for i, row in enumerate(result):
            if feedback.isCanceled():
                break

            (
                from_stop_id,
                to_stop_id,
                from_stop_name,
                to_stop_name,
                trip_count,
                route_short_names,
                route_long_names,
                wkt,
            ) = row

            feat = QgsFeature()
            feat.setFields(fields, initAttributes=True)
            feat.setAttribute("from_stop_id", from_stop_id)
            feat.setAttribute("to_stop_id", to_stop_id)
            feat.setAttribute("from_stop_name", from_stop_name)
            feat.setAttribute("to_stop_name", to_stop_name)
            feat.setAttribute("trip_count", trip_count)
            feat.setAttribute("route_short_names", route_short_names or "")
            feat.setAttribute("route_long_names", route_long_names or "")
            feat.setGeometry(QgsGeometry.fromWkt(wkt))
            sink.addFeature(feat, QgsFeatureSink.FastInsert)

            if (i + 1) % 100 == 0:
                feedback.setProgress(50 + int((i + 1) / total * 50))

        feedback.pushInfo(f"Aggregated into {total} segments.")
        return dest_id
