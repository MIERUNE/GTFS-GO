import re

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDateTime,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
)
from qgis.PyQt.QtCore import QCoreApplication, QMetaType

from processing_provider.utils import (
    GTFS_FILE_FILTER,
    gtfs_parser,
    make_fields,
    write_features,
)

AGGREGATED_ROUTES_FIELDS = [
    ("frequency", QMetaType.Type.Int),
    ("prev_stop_id", QMetaType.Type.QString),
    ("prev_stop_name", QMetaType.Type.QString),
    ("next_stop_id", QMetaType.Type.QString),
    ("next_stop_name", QMetaType.Type.QString),
    ("agency_id", QMetaType.Type.QString),
    ("agency_name", QMetaType.Type.QString),
]
AGGREGATED_STOPS_FIELDS = [
    ("similar_stop_name", QMetaType.Type.QString),
    ("similar_stop_id", QMetaType.Type.QString),
    ("count", QMetaType.Type.Int),
]
STOP_RELATIONS_FIELDS = [
    ("stop_id", QMetaType.Type.QString),
    ("stop_name", QMetaType.Type.QString),
    ("similar_stop_id", QMetaType.Type.QString),
    ("similar_stop_name", QMetaType.Type.QString),
]

# hh:mm:ss, hour can be more than 24 in GTFS
TIME_PATTERN = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")


class AggregateFrequencyAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    UNIFY_STOPS = "UNIFY_STOPS"
    DELIMITER = "DELIMITER"
    DATE = "DATE"
    BEGIN_TIME = "BEGIN_TIME"
    END_TIME = "END_TIME"
    OUTPUT_ROUTES = "OUTPUT_ROUTES"
    OUTPUT_STOPS = "OUTPUT_STOPS"
    OUTPUT_STOP_RELATIONS = "OUTPUT_STOP_RELATIONS"

    def tr(self, string):
        return QCoreApplication.translate("GTFSGo", string)

    def createInstance(self):
        return AggregateFrequencyAlgorithm()

    def name(self):
        return "aggregatefrequency"

    def displayName(self):
        return self.tr("Aggregate traffic frequency")

    def shortHelpString(self):
        return self.tr(
            "Aggregate how many times each path (line between two stops) is used.\n"
            "Similar stops - having same parent_station, same stop_id prefix or "
            "same stop_name and near to each - can be unified into one stop.\n"
            "Trips can be filtered by service date and departure time "
            "(begin <= departure_time < end, hh:mm:ss)."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT,
                self.tr("GTFS zip file"),
                behavior=Qgis.ProcessingFileParameterBehavior.File,
                fileFilter=GTFS_FILE_FILTER,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.UNIFY_STOPS,
                self.tr("unify similar stops"),
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.DELIMITER,
                self.tr("stop_id delimiter (used when unifying stops)"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterDateTime(
                self.DATE,
                self.tr("service date"),
                type=Qgis.ProcessingDateTimeParameterDataType.Date,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.BEGIN_TIME,
                self.tr("begin time (hh:mm:ss)"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.END_TIME,
                self.tr("end time (hh:mm:ss)"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_ROUTES,
                self.tr("Aggregated routes"),
                Qgis.ProcessingSourceType.VectorLine,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_STOPS,
                self.tr("Aggregated stops"),
                Qgis.ProcessingSourceType.VectorPoint,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_STOP_RELATIONS,
                self.tr("Stop relations"),
                Qgis.ProcessingSourceType.Vector,
            )
        )

    def checkParameterValues(self, parameters, context):
        begin_time = self.parameterAsString(parameters, self.BEGIN_TIME, context)
        end_time = self.parameterAsString(parameters, self.END_TIME, context)
        if bool(begin_time) != bool(end_time):
            return False, self.tr("Both begin time and end time must be set.")
        for value in (begin_time, end_time):
            if value and not TIME_PATTERN.match(value):
                return False, self.tr("Time must be in hh:mm:ss format: ") + value
        return super().checkParameterValues(parameters, context)

    def processAlgorithm(self, parameters, context, feedback):
        gtfs_path = self.parameterAsFile(parameters, self.INPUT, context)
        unify_stops = self.parameterAsBool(parameters, self.UNIFY_STOPS, context)
        delimiter = (
            self.parameterAsString(parameters, self.DELIMITER, context)
            if unify_stops
            else ""
        )
        date = self.parameterAsDateTime(parameters, self.DATE, context).date()
        yyyymmdd = date.toString("yyyyMMdd") if date.isValid() else ""
        begin_time = self.parameterAsString(
            parameters, self.BEGIN_TIME, context
        ).replace(":", "")
        end_time = self.parameterAsString(parameters, self.END_TIME, context).replace(
            ":", ""
        )
        if bool(begin_time) != bool(end_time):
            raise QgsProcessingException(
                self.tr("Both begin time and end time must be set.")
            )
        crs = QgsCoordinateReferenceSystem("EPSG:4326")

        feedback.pushInfo(self.tr("Loading GTFS..."))
        gtfs = gtfs_parser.GTFSFactory(gtfs_path)

        feedback.pushInfo(self.tr("Aggregating..."))
        aggregator = gtfs_parser.aggregate.Aggregator(
            gtfs,
            no_unify_stops=not unify_stops,
            delimiter=delimiter,
            yyyymmdd=yyyymmdd,
            begin_time=begin_time,
            end_time=end_time,
        )

        results = {}
        for output, fields_def, wkb_type, read in (
            (
                self.OUTPUT_ROUTES,
                AGGREGATED_ROUTES_FIELDS,
                Qgis.WkbType.LineString,
                aggregator.read_route_frequency,
            ),
            (
                self.OUTPUT_STOPS,
                AGGREGATED_STOPS_FIELDS,
                Qgis.WkbType.Point,
                aggregator.read_interpolated_stops,
            ),
            (
                self.OUTPUT_STOP_RELATIONS,
                STOP_RELATIONS_FIELDS,
                Qgis.WkbType.NoGeometry,
                aggregator.read_stop_relations,
            ),
        ):
            if feedback.isCanceled():
                break
            fields = make_fields(fields_def)
            sink, dest_id = self.parameterAsSink(
                parameters, output, context, fields, wkb_type, crs
            )
            write_features(sink, fields, read(), feedback)
            results[output] = dest_id

        return results
