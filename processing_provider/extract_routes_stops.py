from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
)
from qgis.PyQt.QtCore import QCoreApplication, QMetaType

from processing_provider.utils import (
    GTFS_FILE_FILTER,
    gtfs_parser,
    make_fields,
    write_features,
)

ROUTES_FIELDS = [
    ("route_id", QMetaType.Type.QString),
    ("route_name", QMetaType.Type.QString),
]
STOPS_FIELDS = [
    ("stop_id", QMetaType.Type.QString),
    ("stop_name", QMetaType.Type.QString),
    ("route_ids", QMetaType.Type.QStringList),
]


class ExtractRoutesAndStopsAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    IGNORE_SHAPES = "IGNORE_SHAPES"
    IGNORE_NO_ROUTE = "IGNORE_NO_ROUTE"
    OUTPUT_ROUTES = "OUTPUT_ROUTES"
    OUTPUT_STOPS = "OUTPUT_STOPS"

    def tr(self, string):
        return QCoreApplication.translate("GTFSGo", string)

    def createInstance(self):
        return ExtractRoutesAndStopsAlgorithm()

    def name(self):
        return "extractroutesandstops"

    def displayName(self):
        return self.tr("Extract routes and stops")

    def shortHelpString(self):
        return self.tr(
            "Parse a GTFS feed into simple routes (MultiLineString) and stops (Point).\n"
            "Routes are generated from shapes.txt if it exists, otherwise from stop_times.txt."
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
                self.IGNORE_SHAPES,
                self.tr("ignore shapes.txt"),
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.IGNORE_NO_ROUTE,
                self.tr("ignore isolated stops"),
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_ROUTES,
                self.tr("Routes"),
                Qgis.ProcessingSourceType.VectorLine,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_STOPS,
                self.tr("Stops"),
                Qgis.ProcessingSourceType.VectorPoint,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        gtfs_path = self.parameterAsFile(parameters, self.INPUT, context)
        ignore_shapes = self.parameterAsBool(parameters, self.IGNORE_SHAPES, context)
        ignore_no_route = self.parameterAsBool(
            parameters, self.IGNORE_NO_ROUTE, context
        )
        crs = QgsCoordinateReferenceSystem("EPSG:4326")

        feedback.pushInfo(self.tr("Loading GTFS..."))
        gtfs = gtfs_parser.GTFSFactory(gtfs_path)

        results = {}
        for output, fields_def, wkb_type, read in (
            (
                self.OUTPUT_ROUTES,
                ROUTES_FIELDS,
                Qgis.WkbType.MultiLineString,
                lambda: gtfs_parser.parse.read_routes(
                    gtfs, ignore_shapes=ignore_shapes
                ),
            ),
            (
                self.OUTPUT_STOPS,
                STOPS_FIELDS,
                Qgis.WkbType.Point,
                lambda: gtfs_parser.parse.read_stops(
                    gtfs, ignore_no_route=ignore_no_route
                ),
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
