from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterDateTime,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSink,
)
from qgis.PyQt.QtCore import QCoreApplication, QDate, QMetaType

import constants
from processing_provider.utils import make_fields, write_features
from repository.japan_dpf import api

# keys of the API response
FEED_FIELDS = [
    ("organization_id", QMetaType.Type.QString),
    ("organization_name", QMetaType.Type.QString),
    ("organization_web_url", QMetaType.Type.QString),
    ("organization_email", QMetaType.Type.QString),
    ("feed_id", QMetaType.Type.QString),
    ("feed_name", QMetaType.Type.QString),
    ("feed_pref_id", QMetaType.Type.Int),
    ("feed_pref", QMetaType.Type.QString),
    ("feed_license_id", QMetaType.Type.QString),
    ("feed_license_url", QMetaType.Type.QString),
    ("feed_url", QMetaType.Type.QString),
    ("feed_page_url", QMetaType.Type.QString),
    ("file_uid", QMetaType.Type.QString),
    ("file_rid", QMetaType.Type.QString),
    ("file_from_date", QMetaType.Type.QString),
    ("file_to_date", QMetaType.Type.QString),
    ("file_url", QMetaType.Type.QString),
    ("file_stop_url", QMetaType.Type.QString),
    ("file_route_url", QMetaType.Type.QString),
    ("file_tracking_url", QMetaType.Type.QString),
    ("file_last_updated_at", QMetaType.Type.QString),
]

# index 0 is "any", index n is the prefecture code n
PREF_NAMES = [
    constants.JAPAN_PREFS_CODE_TO_NAME[code]
    for code in sorted(constants.JAPAN_PREFS_CODE_TO_NAME)
]


class SearchJapanDpfAlgorithm(QgsProcessingAlgorithm):
    TARGET_DATE = "TARGET_DATE"
    EXTENT = "EXTENT"
    PREF = "PREF"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return QCoreApplication.translate("GTFSGo", string)

    def createInstance(self):
        return SearchJapanDpfAlgorithm()

    def name(self):
        return "searchjapandpf"

    def displayName(self):
        return self.tr("Search [Japan]GTFS data repository")

    def shortHelpString(self):
        return self.tr(
            "Search GTFS feeds valid on the target date in the GTFS data repository "
            "(https://gtfs-data.jp).\n"
            "Feeds can be filtered by extent and prefecture. "
            "The result is a table of feeds, file_url is the URL of the GTFS zip file."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterDateTime(
                self.TARGET_DATE,
                self.tr("target date"),
                type=Qgis.ProcessingDateTimeParameterDataType.Date,
                defaultValue=QDate.currentDate(),
            )
        )
        self.addParameter(
            QgsProcessingParameterExtent(
                self.EXTENT,
                self.tr("extent"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.PREF,
                self.tr("prefecture"),
                options=[self.tr("any")] + PREF_NAMES,
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr("GTFS feeds"),
                Qgis.ProcessingSourceType.Vector,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        target_date = self.parameterAsDateTime(
            parameters, self.TARGET_DATE, context
        ).date()
        if not target_date.isValid():
            raise QgsProcessingException(self.tr("target date is required."))

        crs = QgsCoordinateReferenceSystem("EPSG:4326")
        extent = None
        if parameters.get(self.EXTENT) is not None:
            rect = self.parameterAsExtent(parameters, self.EXTENT, context, crs)
            if not rect.isEmpty():
                extent = ",".join(
                    str(v)
                    for v in (
                        rect.xMinimum(),
                        rect.yMinimum(),
                        rect.xMaximum(),
                        rect.yMaximum(),
                    )
                )

        pref_code = self.parameterAsEnum(parameters, self.PREF, context) or None

        feedback.pushInfo(self.tr("Searching..."))
        try:
            feeds = api.get_feeds(
                target_date.toString("yyyy-MM-dd"), extent=extent, pref=pref_code
            )
        except Exception as e:
            raise QgsProcessingException(
                self.tr(
                    "Error occured, please check:\n- Internet connection.\n- Repository-server"
                )
                + "\n\n"
                + str(e)
            ) from e
        for feed in feeds:
            feed["feed_pref"] = constants.JAPAN_PREFS_CODE_TO_NAME.get(
                feed.get("feed_pref_id")
            )
        feedback.pushInfo(self.tr("Found feeds: ") + str(len(feeds)))

        fields = make_fields(FEED_FIELDS)
        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields, Qgis.WkbType.NoGeometry, crs
        )
        write_features(sink, fields, feeds, feedback)
        return {self.OUTPUT: dest_id}
