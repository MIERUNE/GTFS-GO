from pathlib import Path

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms.gtfs_aggregate import GtfsAggregateAlgorithm
from .algorithms.gtfs_extract import GtfsExtractAlgorithm


class GTFSGoProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(GtfsExtractAlgorithm())
        self.addAlgorithm(GtfsAggregateAlgorithm())

    def id(self):
        return "gtfsgo"

    def name(self):
        return "GTFS-GO"

    def icon(self):
        path = Path(__file__).parent / "imgs" / "busstop.png"
        return QIcon(str(path))
