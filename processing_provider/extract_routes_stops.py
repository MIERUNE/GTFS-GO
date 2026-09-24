from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
)
from qgis.PyQt.QtCore import QMetaType

import i18n
from gtfs_go_styles import (
    style_routes_layer,
    style_stops_layer,
)
from processing_provider.utils import (
    GTFS_FILE_FILTER,
    gtfs_parser,
    make_fields,
    set_style_on_completion,
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
    APPLY_STYLE = "APPLY_STYLE"
    OUTPUT_ROUTES = "OUTPUT_ROUTES"
    OUTPUT_STOPS = "OUTPUT_STOPS"

    def createInstance(self):
        return ExtractRoutesAndStopsAlgorithm()

    def name(self):
        return "extractroutesandstops"

    def displayName(self):
        return i18n.tr("Extract routes and stops")

    def shortHelpString(self):
        return i18n.tr(
            "Parse a GTFS feed into simple routes (MultiLineString) and stops (Point).\n"
            "Routes are generated from shapes.txt if it exists, otherwise from stop_times.txt."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT,
                i18n.tr("GTFS zip file"),
                behavior=Qgis.ProcessingFileParameterBehavior.File,
                fileFilter=GTFS_FILE_FILTER,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.IGNORE_SHAPES,
                i18n.tr("ignore shapes.txt"),
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.IGNORE_NO_ROUTE,
                i18n.tr("ignore isolated stops"),
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.APPLY_STYLE,
                i18n.tr("apply style to output layers"),
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_ROUTES,
                i18n.tr("Routes"),
                Qgis.ProcessingSourceType.VectorLine,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_STOPS,
                i18n.tr("Stops"),
                Qgis.ProcessingSourceType.VectorPoint,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        gtfs_path = self.parameterAsFile(parameters, self.INPUT, context)
        ignore_shapes = self.parameterAsBool(parameters, self.IGNORE_SHAPES, context)
        ignore_no_route = self.parameterAsBool(
            parameters, self.IGNORE_NO_ROUTE, context
        )
        apply_style = self.parameterAsBool(parameters, self.APPLY_STYLE, context)
        crs = QgsCoordinateReferenceSystem("EPSG:4326")

        feedback.pushInfo(i18n.tr("Loading GTFS..."))
        gtfs = gtfs_parser.GTFSFactory(gtfs_path)

        results = {}
        for output, fields_def, wkb_type, read, style_func in (
            (
                self.OUTPUT_ROUTES,
                ROUTES_FIELDS,
                Qgis.WkbType.MultiLineString,
                lambda: gtfs_parser.parse.read_routes(
                    gtfs, ignore_shapes=ignore_shapes
                ),
                style_routes_layer,
            ),
            (
                self.OUTPUT_STOPS,
                STOPS_FIELDS,
                Qgis.WkbType.Point,
                lambda: gtfs_parser.parse.read_stops(
                    gtfs, ignore_no_route=ignore_no_route
                ),
                style_stops_layer,
            ),
        ):
            if feedback.isCanceled():
                break
            fields = make_fields(fields_def)
            sink, dest_id = self.parameterAsSink(
                parameters, output, context, fields, wkb_type, crs
            )
            write_features(sink, fields, read(), feedback)
            if apply_style:
                set_style_on_completion(context, dest_id, style_func)
            results[output] = dest_id

        return results
