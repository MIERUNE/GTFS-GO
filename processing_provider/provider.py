import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from processing_provider.aggregate_frequency import AggregateFrequencyAlgorithm
from processing_provider.extract_routes_stops import ExtractRoutesAndStopsAlgorithm

ICON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "imgs", "busstop.png"
)


class GTFSGoProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(ExtractRoutesAndStopsAlgorithm())
        self.addAlgorithm(AggregateFrequencyAlgorithm())

    def id(self):
        return "gtfsgo"

    def name(self):
        return "GTFS-GO"

    def icon(self):
        return QIcon(ICON_PATH)
