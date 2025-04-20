import csv
import datetime
import json
import os
import shutil
import sys
import tempfile
import urllib
import uuid

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsSymbolLayer,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QDate, QSortFilterProxyModel, Qt
from qgis.PyQt.QtWidgets import QAbstractItemView, QDialog, QLineEdit, QMessageBox

import constants
import gtfs_parser
import repository
from gtfs_go_labeling import get_labeling_for_stops
from gtfs_go_renderer import Renderer
from gtfs_go_settings import STOPS_MINIMUM_VISIBLE_SCALE

# Tweeked to import gtfs_parser for Python 3.11
try:
    from gtfs_parser import gtfs_parser
except ImportError:
    # Python 3.9 or 3.10
    import gtfs_parser

from repository.japan_dpf.table import HEADERS, HEADERS_TO_HIDE

DATALIST_JSON_PATH = os.path.join(os.path.dirname(__file__), "gtfs_go_datalist.json")
TEMP_DIR = os.path.join(tempfile.gettempdir(), "GTFSGo")

REPOSITORY_ENUM = {"preset": 0, "japanDpf": 1}


class GTFSGoDialog(QDialog):
    def __init__(self, iface: QgisInterface):
        """Constructor."""
        super().__init__()
        self.ui = uic.loadUi(
            os.path.join(os.path.dirname(__file__), "gtfs_go_dialog_base.ui"), self
        )
        with open(DATALIST_JSON_PATH, encoding="utf-8") as f:
            self.datalist = json.load(f)
        self.iface = iface
        self.combobox_zip_text = self.tr("---Load local ZipFile---")
        self.init_gui()

    def init_gui(self):
        # repository combobox
        self.repositoryCombobox.addItem(self.tr("Preset"), REPOSITORY_ENUM["preset"])
        self.repositoryCombobox.addItem(
            self.tr("[Japan]GTFS data repository"), REPOSITORY_ENUM["japanDpf"]
        )

        # local repository data select combobox
        self.ui.comboBox.addItem(self.combobox_zip_text, None)
        for data in self.datalist:
            self.ui.comboBox.addItem(self.make_combobox_text(data), data)

        self.init_local_repository_gui()
        self.init_japan_dpf_gui()

        # set refresh event on some ui
        self.ui.repositoryCombobox.currentIndexChanged.connect(self.refresh)
        self.ui.outputDirFileWidget.fileChanged.connect(self.refresh)
        self.ui.unifyCheckBox.stateChanged.connect(self.refresh)
        self.ui.timeFilterCheckBox.stateChanged.connect(self.refresh)
        self.ui.simpleCheckbox.clicked.connect(self.refresh)
        self.ui.aggregateCheckbox.clicked.connect(self.refresh)

        # time filter - validate user input
        self.ui.beginTimeLineEdit.editingFinished.connect(
            lambda: self.validate_time_lineedit(self.ui.beginTimeLineEdit)
        )
        self.ui.endTimeLineEdit.editingFinished.connect(
            lambda: self.validate_time_lineedit(self.ui.endTimeLineEdit)
        )

        # set today DateEdit
        now = datetime.datetime.now()
        self.ui.filterByDateDateEdit.setDate(QDate(now.year, now.month, now.day))

        self.refresh()

        self.ui.pushButton.clicked.connect(self.execution)

    def init_local_repository_gui(self):
        self.ui.comboBox.currentIndexChanged.connect(self.refresh)
        self.ui.zipFileWidget.fileChanged.connect(self.refresh)

    def init_japan_dpf_gui(self):
        self.japanDpfResultTableView.clicked.connect(self.refresh)

        self.japanDpfResultTableView.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.japan_dpf_set_table([])
        for idx, header in enumerate(HEADERS):
            if header in HEADERS_TO_HIDE:
                self.japanDpfResultTableView.hideColumn(idx)
        # set default column width
        self.japanDpfResultTableView.setColumnWidth(HEADERS.index("organization"), 110)
        self.japanDpfResultTableView.setColumnWidth(HEADERS.index("feed"), 150)

        self.japanDpfPrefectureCombobox.addItem(self.tr("any"), None)
        for prefname in constants.JAPAN_PREFS_NAME_TO_CODE.keys():
            self.japanDpfPrefectureCombobox.addItem(prefname, prefname)

        now = datetime.datetime.now()
        self.ui.japanDpfTargetDateEdit.setDate(QDate(now.year, now.month, now.day))

        self.japanDpfExtentGroupBox.setMapCanvas(self.iface.mapCanvas())
        self.japanDpfExtentGroupBox.setOutputCrs(
            QgsCoordinateReferenceSystem("EPSG:4326")
        )

        self.japanDpfSearchButton.clicked.connect(self.japan_dpf_search)

    def make_combobox_text(self, data):
        """
        parse data to combobox-text
        data-schema: {
            country: str,
            region: str,
            name: str,
            url: str
        }

        Args:
            data ([type]): [description]

        Returns:
            str: combobox-text
        """
        return "[" + data["country"] + "]" + "[" + data["region"] + "]" + data["name"]

    def download_zip(self, url: str) -> str:
        data = urllib.request.urlopen(url).read()
        download_path = os.path.join(TEMP_DIR, str(uuid.uuid4()) + ".zip")
        with open(download_path, mode="wb") as f:
            f.write(data)

        return download_path

    def get_target_feed_infos(self):
        feed_infos = []
        if self.repositoryCombobox.currentData() == REPOSITORY_ENUM["preset"]:
            if self.ui.comboBox.currentData():
                feed_infos.append(
                    {
                        "path": self.ui.comboBox.currentData().get("url"),
                        "group": self.ui.comboBox.currentData().get("name"),
                        "dir": self.ui.comboBox.currentData().get("name"),
                    }
                )
            elif (
                self.ui.comboBox.currentData() is None
                and self.ui.zipFileWidget.filePath()
            ):
                feed_infos.append(
                    {
                        "path": self.ui.zipFileWidget.filePath(),
                        "group": os.path.basename(
                            self.ui.zipFileWidget.filePath()
                        ).split(".")[0],
                        "dir": os.path.basename(self.ui.zipFileWidget.filePath()).split(
                            "."
                        )[0],
                    }
                )
        elif self.repositoryCombobox.currentData() == REPOSITORY_ENUM["japanDpf"]:
            selected_rows = self.japanDpfResultTableView.selectionModel().selectedRows()
            for row in selected_rows:
                row_data = self.get_selected_row_data_in_japan_dpf_table(row.row())
                feed_infos.append(
                    {
                        "path": row_data["file_url"],
                        "group": row_data["organization"] + "-" + row_data["feed"],
                        "dir": row_data["organization_id"]
                        + "-"
                        + row_data["feed_id"]
                        + "-"
                        + row_data["file_uid"],
                    }
                )
        return feed_infos

    def execution(self):
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR, exist_ok=True)

        for feed_info in self.get_target_feed_infos():
            if feed_info["path"].startswith("http"):
                feed_info["path"] = self.download_zip(feed_info["path"])

            output_dir = os.path.join(
                self.outputDirFileWidget.filePath(), feed_info["dir"]
            )
            os.makedirs(output_dir, exist_ok=True)

            written_files = {
                "routes": "",
                "stops": "",
                "aggregated_routes": "",
                "aggregated_stops": "",
                "aggregated_csv": "",
            }

            gtfs = gtfs_parser.GTFSFactory(feed_info["path"])

            if self.ui.simpleCheckbox.isChecked():
                routes_geojson = {
                    "type": "FeatureCollection",
                    "features": gtfs_parser.parse.read_routes(
                        gtfs, ignore_shapes=self.ui.ignoreShapesCheckbox.isChecked()
                    ),
                }
                stops_geojson = {
                    "type": "FeatureCollection",
                    "features": gtfs_parser.parse.read_stops(
                        gtfs,
                        ignore_no_route=self.ui.ignoreNoRouteStopsCheckbox.isChecked(),
                    ),
                }
                # write
                written_files["routes"] = os.path.join(output_dir, "routes.geojson")
                written_files["stops"] = os.path.join(output_dir, "stops.geojson")
                with open(
                    written_files["routes"],
                    mode="w",
                    encoding="utf-8",
                ) as f:
                    json.dump(routes_geojson, f, ensure_ascii=False)

                with open(
                    written_files["stops"],
                    mode="w",
                    encoding="utf-8",
                ) as f:
                    json.dump(stops_geojson, f, ensure_ascii=False)

            if self.ui.aggregateCheckbox.isChecked():
                aggregator = gtfs_parser.aggregate.Aggregator(
                    gtfs,
                    no_unify_stops=not self.ui.unifyCheckBox.isChecked(),
                    delimiter=self.get_delimiter(),
                    yyyymmdd=self.get_yyyymmdd(),
                    begin_time=self.get_time_filter(self.ui.beginTimeLineEdit),
                    end_time=self.get_time_filter(self.ui.endTimeLineEdit),
                )
                aggregated_routes_geojson = {
                    "type": "FeatureCollection",
                    "features": aggregator.read_route_frequency(),
                }
                aggregated_stops_geojson = {
                    "type": "FeatureCollection",
                    "features": aggregator.read_interpolated_stops(),
                }
                stop_relations = aggregator.read_stop_relations()
                # write
                written_files["aggregated_routes"] = os.path.join(
                    output_dir, "aggregated_routes.geojson"
                )
                written_files["aggregated_stops"] = os.path.join(
                    output_dir, "aggregated_stops.geojson"
                )
                written_files["aggregated_csv"] = os.path.join(output_dir, "result.csv")
                with open(
                    written_files["aggregated_stops"],
                    mode="w",
                    encoding="utf-8",
                ) as f:
                    json.dump(aggregated_stops_geojson, f, ensure_ascii=False)
                with open(
                    written_files["aggregated_routes"],
                    mode="w",
                    encoding="utf-8",
                ) as f:
                    json.dump(aggregated_routes_geojson, f, ensure_ascii=False)
                with open(
                    written_files["aggregated_csv"],
                    mode="w",
                    encoding="utf-8",
                    errors="ignore",
                    newline="",
                ) as f:
                    writer = csv.DictWriter(f, fieldnames=stop_relations[0].keys())
                    writer.writeheader()
                    writer.writerows(stop_relations)

            self.show_geojson(
                feed_info["group"],
                written_files["stops"],
                written_files["routes"],
                written_files["aggregated_stops"],
                written_files["aggregated_routes"],
                written_files["aggregated_csv"],
            )

    def get_yyyymmdd(self):
        if not self.ui.filterByDateCheckBox.isChecked():
            return ""
        date = self.ui.filterByDateDateEdit.date()
        yyyy = str(date.year()).zfill(4)
        mm = str(date.month()).zfill(2)
        dd = str(date.day()).zfill(2)
        return yyyy + mm + dd

    def get_delimiter(self):
        if not self.ui.unifyCheckBox.isChecked():
            return ""
        if not self.ui.delimiterCheckBox.isChecked():
            return ""
        return self.ui.delimiterLineEdit.text()

    def get_time_filter(self, line_edit: QLineEdit):
        if not self.ui.timeFilterCheckBox.isChecked():
            return ""
        return line_edit.text().replace(":", "")

    def show_geojson(
        self,
        group_name: str,
        stops_geojson: str,
        routes_geojson: str,
        aggregated_stops_geojson: str,
        aggregated_routes_geojson: str,
        aggregated_csv: str,
    ):
        root = QgsProject().instance().layerTreeRoot()
        group = root.insertGroup(0, group_name)
        group.setExpanded(True)

        if routes_geojson != "":
            routes_vlayer = QgsVectorLayer(
                routes_geojson, os.path.basename(routes_geojson).split(".")[0], "ogr"
            )
            routes_renderer = Renderer(routes_vlayer, "route_name")
            routes_vlayer.setRenderer(routes_renderer.make_renderer())

            QgsProject.instance().addMapLayer(routes_vlayer, False)
            group.insertLayer(0, routes_vlayer)

        if stops_geojson != "":
            stops_vlayer = QgsVectorLayer(
                stops_geojson, os.path.basename(stops_geojson).split(".")[0], "ogr"
            )
            # make and set labeling for stops
            stops_labeling = get_labeling_for_stops("stop_name")
            stops_vlayer.setLabelsEnabled(True)
            stops_vlayer.setLabeling(stops_labeling)

            # adjust layer visibility
            stops_vlayer.setMinimumScale(STOPS_MINIMUM_VISIBLE_SCALE)
            stops_vlayer.setScaleBasedVisibility(True)

            stops_renderer = Renderer(stops_vlayer, "stop_name")
            stops_vlayer.setRenderer(stops_renderer.make_renderer())

            QgsProject.instance().addMapLayer(stops_vlayer, False)
            group.insertLayer(0, stops_vlayer)

        if aggregated_routes_geojson != "":
            aggregated_routes_vlayer = QgsVectorLayer(
                aggregated_routes_geojson,
                os.path.basename(aggregated_routes_geojson).split(".")[0],
                "ogr",
            )
            aggregated_routes_vlayer.loadNamedStyle(
                os.path.join(os.path.dirname(__file__), "aggregated_routes.qml")
            )

            QgsProject.instance().addMapLayer(aggregated_routes_vlayer, False)
            group.insertLayer(0, aggregated_routes_vlayer)

        if aggregated_stops_geojson != "":
            aggregated_stops_vlayer = QgsVectorLayer(
                aggregated_stops_geojson,
                os.path.basename(aggregated_stops_geojson).split(".")[0],
                "ogr",
            )
            aggregated_stops_vlayer.loadNamedStyle(
                os.path.join(os.path.dirname(__file__), "aggregated_stops.qml")
            )

            scale_stop_size = self.ui.scaleStopSizeCheckBox.isChecked()
            dd_props = (
                aggregated_stops_vlayer.renderer()
                .symbol()
                .symbolLayers()[0]
                .dataDefinedProperties()
            )
            if dd_props.hasProperty(QgsSymbolLayer.PropertySize):
                dd_props.property(QgsSymbolLayer.PropertySize).setActive(
                    scale_stop_size
                )

            QgsProject.instance().addMapLayer(aggregated_stops_vlayer, False)
            group.insertLayer(0, aggregated_stops_vlayer)

        if aggregated_csv != "":
            aggregated_csv_vlayer = QgsVectorLayer(
                aggregated_csv,
                os.path.basename(aggregated_csv).split(".")[0],
                "ogr",
            )
            aggregated_csv_vlayer.setProviderEncoding("UTF-8")

            QgsProject.instance().addMapLayer(aggregated_csv_vlayer, False)
            group.insertLayer(0, aggregated_csv_vlayer)

        self.iface.messageBar().pushInfo(
            self.tr("finish"), self.tr("generated geojson files: ")
        )
        self.ui.close()

    def refresh(self):
        self.localDataSelectAreaWidget.setVisible(
            self.repositoryCombobox.currentData() == REPOSITORY_ENUM["preset"]
        )
        self.japanDpfDataSelectAreaWidget.setVisible(
            self.repositoryCombobox.currentData() == REPOSITORY_ENUM["japanDpf"]
        )

        # idiom to shrink window to fit its content
        self.resize(0, 0)
        self.adjustSize()

        self.ui.zipFileWidget.setEnabled(
            self.ui.comboBox.currentText() == self.combobox_zip_text
        )

        # set executable
        self.ui.pushButton.setEnabled(
            (len(self.get_target_feed_infos()) > 0)
            and (self.ui.outputDirFileWidget.filePath() != "")
            and (
                self.ui.simpleCheckbox.isChecked()
                or self.ui.aggregateCheckbox.isChecked()
            )
        )

        # stops unify mode
        is_unify = self.ui.unifyCheckBox.isChecked()
        self.ui.delimiterCheckBox.setEnabled(is_unify)
        self.ui.delimiterLineEdit.setEnabled(is_unify)

        # filter by times mode
        has_time_filter = self.ui.timeFilterCheckBox.isChecked()
        self.ui.beginTimeLineEdit.setEnabled(has_time_filter)
        self.ui.endTimeLineEdit.setEnabled(has_time_filter)

        # mode toggle
        self.ui.simpleFrame.setEnabled(self.ui.simpleCheckbox.isChecked())
        self.ui.freqFrame.setEnabled(self.ui.aggregateCheckbox.isChecked())

    @staticmethod
    def validate_time_lineedit(lineedit: QLineEdit):
        digits = "".join(
            list(filter(lambda char: char.isdigit(), list(lineedit.text())))
        ).ljust(6, "0")[-6:]

        # limit to 29:59:59
        hh = str(min(29, int(digits[0:2]))).zfill(2)
        mm = str(min(59, int(digits[2:4]))).zfill(2)
        ss = str(min(59, int(digits[4:6]))).zfill(2)

        formatted_time_text = hh + ":" + mm + ":" + ss
        lineedit.setText(formatted_time_text)

    def japan_dpf_search(self):
        self.ui.pushButton.setEnabled(False)
        self.japanDpfSearchButton.setEnabled(False)
        self.japanDpfSearchButton.setText(self.tr("Searching..."))

        target_date = self.ui.japanDpfTargetDateEdit.date()
        yyyy = str(target_date.year()).zfill(4)
        mm = str(target_date.month()).zfill(2)
        dd = str(target_date.day()).zfill(2)

        extent = (
            None
            if self.japanDpfExtentGroupBox.outputExtent().isEmpty()
            else self.japanDpfExtentGroupBox.outputExtent()
            .toString()
            .replace(" : ", ",")
        )

        pref_code = (
            None
            if self.japanDpfPrefectureCombobox.currentData() is None
            else constants.JAPAN_PREFS_NAME_TO_CODE.get(
                self.japanDpfPrefectureCombobox.currentData()
            )
        )

        try:
            results = repository.japan_dpf.api.get_feeds(
                f"{yyyy}-{mm}-{dd}",
                extent=extent,
                pref=pref_code,
            )
            self.japan_dpf_set_table(results)
        except Exception as e:
            QMessageBox.information(
                self,
                self.tr("Error"),
                self.tr(
                    "Error occured, please check:\n- Internet connection.\n- Repository-server"
                )
                + "\n\n"
                + e,
            )
        finally:
            self.japanDpfSearchButton.setEnabled(True)
            self.japanDpfSearchButton.setText(self.tr("Search"))
            self.refresh()

    def japan_dpf_set_table(self, results: list):
        # replace pref code to pref name
        for result in results:
            result["feed_pref"] = constants.JAPAN_PREFS_CODE_TO_NAME[
                result["feed_pref_id"]
            ]
        model = repository.japan_dpf.table.Model(results)
        proxy_model = QSortFilterProxyModel()
        proxy_model.setDynamicSortFilter(True)
        proxy_model.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        proxy_model.setSourceModel(model)

        self.japanDpfResultTableView.setModel(proxy_model)
        self.japanDpfResultTableView.setCornerButtonEnabled(True)
        self.japanDpfResultTableView.setSortingEnabled(True)
        # -1 is no sort indicator
        self.japanDpfResultTableView.sortByColumn(-1, Qt.SortOrder.AscendingOrder)

        # resize columns and rows
        self.japanDpfResultTableView.resizeColumnToContents(HEADERS.index("pref"))
        self.japanDpfResultTableView.resizeColumnToContents(HEADERS.index("license"))
        self.japanDpfResultTableView.resizeColumnToContents(HEADERS.index("from_date"))
        self.japanDpfResultTableView.resizeColumnToContents(HEADERS.index("to_date"))
        self.japanDpfResultTableView.resizeRowsToContents()

    def get_selected_row_data_in_japan_dpf_table(self, row: int):
        data = {}
        for col_idx, col_name in enumerate(repository.japan_dpf.table.HEADERS):
            data[col_name] = (
                self.japanDpfResultTableView.model().index(row, col_idx).data()
            )
        return data
