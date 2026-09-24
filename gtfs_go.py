import os

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

import i18n

# Import the code for the DockWidget
from gtfs_go_dialog import GTFSGoDialog
from processing_provider.provider import GTFSGoProvider


class GTFSGo:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        i18n.load(QgsApplication.instance().locale())

        # Declare instance attributes
        self.actions = []
        self.menu = "&GTFS GO"

        # print "** INITIALIZING GTFSGo"

        self.pluginIsActive = False
        self.dialog = None
        self.provider = None

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_plugin_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None,
    ):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_plugin_toolbar: Flag indicating whether the action should also
            be added to the plugin toolbar. Defaults to True.
        :type add_to_plugin_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_menu:
            self.iface.addPluginToWebMenu(self.menu, action)

        if add_to_plugin_toolbar:
            self.iface.addToolBarIcon(action)

        self.actions.append(action)

        return action

    def initProcessing(self):
        self.provider = GTFSGoProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        self.initProcessing()

        icon_path = os.path.join(os.path.dirname(__file__), "imgs", "busstop.png")
        self.add_action(
            icon_path,
            text="GTFS GO",
            callback=self.run,
            parent=self.iface.mainWindow(),
            add_to_menu=True,
            add_to_plugin_toolbar=True,
        )

    # --------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        # print "** CLOSING GTFSGo"

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        # self.dockwidget = None

        self.pluginIsActive = False

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        # print "** UNLOAD GTFSGo"

        for action in self.actions:
            self.iface.removePluginWebMenu("&GTFS GO", action)
            self.iface.removeToolBarIcon(action)

        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

    # --------------------------------------------------------------------------

    def run(self):
        """Run method that loads and starts the plugin"""
        if self.dialog is None:
            self.dialog = GTFSGoDialog(self.iface)
        self.dialog.show()
