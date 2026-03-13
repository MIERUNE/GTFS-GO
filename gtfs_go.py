import os

import processing
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolButton

from .provider import GTFSGoProvider


class GTFSGo:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = "&GTFS GO"
        self.provider = None
        self.dock = None
        self.tool_button = None
        self.tool_button_action = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "imgs", "busstop.png")
        icon = QIcon(icon_path)

        # Create actions
        open_editor_action = QAction(icon, "Editorを開く", self.iface.mainWindow())
        open_editor_action.triggered.connect(self.run)
        self.actions.append(open_editor_action)

        extract_action = QAction(
            icon, "Extract GTFS Stops / Routes", self.iface.mainWindow()
        )
        extract_action.triggered.connect(self._run_extract)
        self.actions.append(extract_action)

        aggregate_action = QAction(
            icon, "Aggregate GTFS Stops / Segments", self.iface.mainWindow()
        )
        aggregate_action.triggered.connect(self._run_aggregate)
        self.actions.append(aggregate_action)

        # Create QToolButton with dropdown menu
        self.tool_button = QToolButton(self.iface.mainWindow())
        self.tool_button.setIcon(icon)
        self.tool_button.setPopupMode(QToolButton.MenuButtonPopup)

        tool_menu = QMenu(self.iface.mainWindow())
        tool_menu.addAction(open_editor_action)
        tool_menu.addSeparator()
        tool_menu.addAction(extract_action)
        tool_menu.addAction(aggregate_action)
        self.tool_button.setMenu(tool_menu)

        # Set default action (last used action)
        self.tool_button.setDefaultAction(open_editor_action)
        tool_menu.triggered.connect(self.tool_button.setDefaultAction)

        # Add to toolbar and web menu
        toolbar = self.iface.pluginToolBar()
        self.tool_button_action = toolbar.addWidget(self.tool_button)

        for action in self.actions:
            self.iface.addPluginToWebMenu(self.menu, action)

        self.provider = GTFSGoProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginWebMenu(self.menu, action)

        if self.tool_button_action:
            self.iface.pluginToolBar().removeAction(self.tool_button_action)
            self.tool_button_action = None

        if self.tool_button:
            self.tool_button.deleteLater()
            self.tool_button = None

        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

        if self.dock:
            self.dock.cleanup()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

    def _run_extract(self):
        processing.execAlgorithmDialog("gtfsgo:extract")

    def _run_aggregate(self):
        processing.execAlgorithmDialog("gtfsgo:aggregate")

    def run(self):
        if self.dock is None:
            from .ui.gtfs_editor_dock import GtfsEditorDock

            self.dock = GtfsEditorDock(self.iface, self.iface.mainWindow())
            self.iface.addDockWidget(Qt.BottomDockWidgetArea, self.dock)
        self.dock.show()
        self.dock.raise_()
