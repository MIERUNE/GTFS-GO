import os

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .provider import GTFSGoProvider


class GTFSGo:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = "&GTFS GO"
        self.provider = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "imgs", "busstop.png")
        icon = QIcon(icon_path)
        action = QAction(icon, "GTFS GO", self.iface.mainWindow())
        action.triggered.connect(self.run)
        self.iface.addPluginToWebMenu(self.menu, action)
        self.iface.addToolBarIcon(action)
        self.actions.append(action)

        self.provider = GTFSGoProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginWebMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

    def run(self):
        pass
