# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GTFSViewerDockWidget
                                 A QGIS plugin
 The plugin to show routes and stops from GTFS
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2020-10-29
        git sha              : $Format:%H$
        copyright            : (C) 2020 by MIERUNE Inc.
        email                : info@mierune.co.jp
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
import json

from qgis.PyQt import QtWidgets, uic
from qgis.core import *

from .gtfs_viewer_loader import GTFSViewerLoader
from .gtfs_viewer_renderer import Renderer
from .gtfs_viewer_labeling import get_labeling_for_stops
from .gtfs_viewer_settings import (
    STOPS_MINIMUM_VISIBLE_SCALE,
    FILENAME_ROUTES_GEOJSON,
    FILENAME_STOPS_GEOJSON,
    LAYERNAME_ROUTES,
    LAYERNAME_STOPS
)

DATALIST_JSON_PATH = os.path.join(
    os.path.dirname(__file__), 'gtfs_viewer_datalist.json')


class GTFSViewerDialog(QtWidgets.QDialog):

    combobox_placeholder_text = '---読み込むデータを選択---'
    combobox_zip_text = '---zipファイルから読み込み---'

    def __init__(self, iface):
        """Constructor."""
        super().__init__()
        self.ui = uic.loadUi(os.path.join(os.path.dirname(
            __file__), 'gtfs_viewer_dialog_base.ui'), self)
        with open(DATALIST_JSON_PATH) as f:
            print(f)
            self.datalist = json.load(f)
        self.iface = iface
        self.init_gui()

    def init_gui(self):
        self.ui.comboBox.addItem(self.combobox_placeholder_text, None)
        self.ui.comboBox.addItem(self.combobox_zip_text, None)
        for data in self.datalist:
            self.ui.comboBox.addItem(self.make_combobox_text(data), data)
        self.ui.comboBox.currentIndexChanged.connect(self.refresh)
        self.ui.zipFileWidget.fileChanged.connect(self.refresh)
        self.ui.outputDirFileWidget.fileChanged.connect(self.refresh)
        self.refresh()

        self.ui.pushButton.clicked.connect(self.execution)

    def make_combobox_text(self, data):
        """
        parse data to combobox-text
        data-schema: {
            region: str,
            name: str,
            url: str
        }

        Args:
            data ([type]): [description]

        Returns:
            str: combobox-text
        """
        if data.get('region') is None:
            return data["name"]
        return f'[{data["region"]}] {data["name"]}'

    def execution(self):
        loader = GTFSViewerLoader(
            self.get_source(),
            os.path.join(self.outputDirFileWidget.filePath(),
                         self.get_group_name()),
            self.ui.ignoreShapesCheckbox.isChecked(),
            self.ui.ignoreNoRouteStopsCheckbox.isChecked())
        loader.geojsonWritingFinished.connect(
            lambda output_dir: self.show_geojson(output_dir))
        loader.loadingAborted.connect(self.ui.show)
        loader.show()
        self.ui.hide()

    def show_geojson(self, geojson_dir: str):
        # these geojsons will already have been generated
        stops_geojson = os.path.join(geojson_dir, FILENAME_STOPS_GEOJSON)
        routes_geojson = os.path.join(geojson_dir, FILENAME_ROUTES_GEOJSON)

        stops_vlayer = QgsVectorLayer(stops_geojson, LAYERNAME_STOPS, 'ogr')
        routes_vlayer = QgsVectorLayer(routes_geojson, LAYERNAME_ROUTES, 'ogr')

        # make and set renderer for each layers
        stops_renderer = Renderer(stops_vlayer, 'stop_name')
        routes_renderer = Renderer(routes_vlayer, 'route_name')
        stops_vlayer.setRenderer(stops_renderer.make_renderer())
        routes_vlayer.setRenderer(routes_renderer.make_renderer())

        # make and set labeling for stops
        stops_labeling = get_labeling_for_stops()
        stops_vlayer.setLabelsEnabled(True)
        stops_vlayer.setLabeling(stops_labeling)

        # adjust layer visibility
        stops_vlayer.setMinimumScale(STOPS_MINIMUM_VISIBLE_SCALE)
        stops_vlayer.setScaleBasedVisibility(True)

        # add two layers as a group
        group_name = self.get_group_name()
        self.add_layers_as_group(group_name, [routes_vlayer, stops_vlayer])

        self.iface.messageBar().pushInfo(
            '完了', f'{geojson_dir}に.geojsonファイルが出力されました')
        self.ui.close()

    def get_source(self):
        if self.ui.comboBox.currentData():
            return self.ui.comboBox.currentData().get("url")
        elif self.ui.comboBox.currentData() is None and self.ui.zipFileWidget.filePath():
            return self.ui.zipFileWidget.filePath()
        else:
            return None

    def refresh(self):
        self.ui.zipFileWidget.setEnabled(
            self.ui.comboBox.currentText() == self.combobox_zip_text)
        self.ui.pushButton.setEnabled((self.get_source() is not None) and
                                      (not self.ui.outputDirFileWidget.filePath() == ''))

    def get_group_name(self):
        if self.ui.comboBox.currentData():
            return self.ui.comboBox.currentData().get("name")
        elif self.ui.comboBox.currentData() is None and self.ui.zipFileWidget.filePath():
            return os.path.basename(self.ui.zipFileWidget.filePath()).split(".")[0]
        else:
            return "no named group"

    def add_layers_as_group(self, group_name: str, layers: [QgsMapLayer]):
        """
        add layers into project as a group.
        the order of layers is reverse to layers list order.
        if layers: [layer_A, layer_B, layer_C]
        then in tree:
        - layer_C
        - layer_B
        - layer_A

        Args:
            group_name (str): [description]
            layers ([type]): [description]
        """
        root = QgsProject().instance().layerTreeRoot()
        group = root.addGroup(group_name)
        group.setExpanded(True)
        for layer in layers:
            QgsProject.instance().addMapLayer(layer, False)
            group.insertLayer(0, layer)
