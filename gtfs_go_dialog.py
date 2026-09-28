import datetime
import functools
import json
import os
import shutil
import tempfile
from typing import Optional

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProject,
    QgsReferencedRectangle,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QDate, QSortFilterProxyModel, Qt, QVariant
from qgis.PyQt.QtWidgets import QAbstractItemView, QDialog, QLineEdit

import constants
import i18n
import repository
from gtfs_go_styles import (
    style_aggregated_routes_layer,
    style_aggregated_stops_layer,
    style_routes_layer,
    style_stops_layer,
)
from gtfs_go_task import AlgorithmJob, GTFSGoTask
from processing_provider.aggregate_frequency import AggregateFrequencyAlgorithm
from processing_provider.extract_routes_stops import ExtractRoutesAndStopsAlgorithm
from processing_provider.search_japan_dpf import SearchJapanDpfAlgorithm
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
        i18n.translate_widget(self)
        with open(DATALIST_JSON_PATH, encoding="utf-8") as f:
            self.datalist = json.load(f)
        self.iface = iface
        self.task: Optional[GTFSGoTask] = None
        self.combobox_zip_text = i18n.tr("---Load local ZipFile---")
        self.init_gui()

    def init_gui(self):
        # repository combobox
        self.repositoryCombobox.addItem(i18n.tr("Preset"), REPOSITORY_ENUM["preset"])
        self.repositoryCombobox.addItem(
            i18n.tr("[Japan]GTFS data repository"), REPOSITORY_ENUM["japanDpf"]
        )

        # local repository data select combobox
        self.ui.comboBox.addItem(self.combobox_zip_text, None)
        for data in self.datalist:
            self.ui.comboBox.addItem(self.make_combobox_text(data), data)

        self.init_local_repository_gui()
        self.init_japan_dpf_gui()

        # set refresh event on some ui
        self.ui.repositoryCombobox.currentIndexChanged.connect(self.refresh)
        self.ui.outputDirFileWidget.lineEdit().setPlaceholderText(
            i18n.tr("[Create temporary layers]")
        )
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

        self.japanDpfPrefectureCombobox.addItem(i18n.tr("any"), None)
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

        self.ui.progressBar.setValue(0)
        self.task = GTFSGoTask(
            self.get_target_feed_infos(),
            self.make_algorithm_jobs(),
            self.outputDirFileWidget.filePath(),
            TEMP_DIR,
            self.on_task_finished,
        )
        self.task.progressChanged.connect(self.on_task_progress)
        QgsApplication.taskManager().addTask(self.task)
        # prevent re-execution while running
        self.refresh()

    def make_algorithm_jobs(self) -> list:
        """Read the options on the main thread, to be used in the task"""
        jobs = []
        if self.ui.simpleCheckbox.isChecked():
            jobs.append(
                AlgorithmJob(
                    ExtractRoutesAndStopsAlgorithm(),
                    {
                        "IGNORE_SHAPES": self.ui.ignoreShapesCheckbox.isChecked(),
                        "IGNORE_NO_ROUTE": self.ui.ignoreNoRouteStopsCheckbox.isChecked(),
                    },
                    [
                        (
                            "OUTPUT_ROUTES",
                            "routes.geojson",
                            "routes",
                            style_routes_layer,
                        ),
                        ("OUTPUT_STOPS", "stops.geojson", "stops", style_stops_layer),
                    ],
                )
            )
        if self.ui.aggregateCheckbox.isChecked():
            jobs.append(
                AlgorithmJob(
                    AggregateFrequencyAlgorithm(),
                    {
                        "UNIFY_STOPS": self.ui.unifyCheckBox.isChecked(),
                        "DELIMITER": self.get_delimiter(),
                        "DATE": self.get_date(),
                        "BEGIN_TIME": self.get_time_filter(self.ui.beginTimeLineEdit),
                        "END_TIME": self.get_time_filter(self.ui.endTimeLineEdit),
                    },
                    [
                        (
                            "OUTPUT_ROUTES",
                            "aggregated_routes.geojson",
                            "aggregated_routes",
                            style_aggregated_routes_layer,
                        ),
                        (
                            "OUTPUT_STOPS",
                            "aggregated_stops.geojson",
                            "aggregated_stops",
                            functools.partial(
                                style_aggregated_stops_layer,
                                scale_stop_size=self.ui.scaleStopSizeCheckBox.isChecked(),
                            ),
                        ),
                        (
                            "OUTPUT_STOP_RELATIONS",
                            "result.csv",
                            "result",
                            lambda layer: layer.setProviderEncoding("UTF-8"),
                        ),
                    ],
                )
            )
        return jobs

    def on_task_progress(self, value: float):
        # ignore the progress queued after the task finished
        if self.task is not None:
            self.ui.progressBar.setValue(int(value))

    def on_task_finished(self, task: GTFSGoTask, result: bool):
        """Called on the main thread when the task is finished or canceled"""
        self.task = None
        self.ui.progressBar.setValue(0)
        self.refresh()

        for error in task.errors:
            self.iface.messageBar().pushCritical(i18n.tr("Error"), error)
        if not result:
            return

        for feed_result in task.results:
            self.show_layers(
                feed_result.group,
                [
                    (
                        self.take_result_layer(feed_result.context, output_id, name),
                        style_func,
                    )
                    for name, output_id, style_func in feed_result.outputs
                ],
            )
        if task.results:
            self.iface.messageBar().pushInfo(
                i18n.tr("finish"), i18n.tr("GTFS data has been loaded.")
            )
            self.ui.close()

    @staticmethod
    def take_result_layer(
        context: QgsProcessingContext, output_id: str, name: str
    ) -> QgsVectorLayer:
        """
        Args:
            output_id: layer id of a temporary layer, or path of a written file
        """
        layer = context.takeResultLayer(output_id)
        if layer is None:
            layer = QgsVectorLayer(output_id, name, "ogr")
        layer.setName(name)
        return layer

    def run_algorithm(
        self,
        algorithm: QgsProcessingAlgorithm,
        parameters: dict,
        context: Optional[QgsProcessingContext] = None,
    ) -> Optional[dict]:
        """
        Returns:
            results of the algorithm, None if failed
        """
        alg = algorithm.create()
        if context is None:
            context = QgsProcessingContext()
            context.setProject(QgsProject.instance())
        feedback = QgsProcessingFeedback()
        ok, message = alg.checkParameterValues(parameters, context)
        results = None
        if ok:
            results, ok = alg.run(parameters, context, feedback)
            message = feedback.textLog()
        if not ok:
            self.iface.messageBar().pushCritical(
                i18n.tr("Error"),
                alg.displayName() + ": " + message,
            )
            return None
        return results

    def get_date(self) -> Optional[QDate]:
        if not self.ui.filterByDateCheckBox.isChecked():
            return None
        return self.ui.filterByDateDateEdit.date()

    def get_delimiter(self):
        if not self.ui.unifyCheckBox.isChecked():
            return ""
        if not self.ui.delimiterCheckBox.isChecked():
            return ""
        return self.ui.delimiterLineEdit.text()

    def get_time_filter(self, line_edit: QLineEdit):
        if not self.ui.timeFilterCheckBox.isChecked():
            return ""
        return line_edit.text()

    def show_layers(self, group_name: str, layers: list):
        """
        Args:
            layers: list of (QgsVectorLayer, style function), from bottom to top
        """
        root = QgsProject().instance().layerTreeRoot()
        group = root.insertGroup(0, group_name)
        group.setExpanded(True)

        for layer, style_func in layers:
            style_func(layer)
            QgsProject.instance().addMapLayer(layer, False)
            group.insertLayer(0, layer)

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
            self.task is None
            and (len(self.get_target_feed_infos()) > 0)
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
        self.japanDpfSearchButton.setText(i18n.tr("Searching..."))

        extent = self.japanDpfExtentGroupBox.outputExtent()
        pref_name = self.japanDpfPrefectureCombobox.currentData()
        parameters = {
            "TARGET_DATE": self.ui.japanDpfTargetDateEdit.date(),
            "EXTENT": None
            if extent.isEmpty()
            else QgsReferencedRectangle(
                extent, self.japanDpfExtentGroupBox.outputCrs()
            ),
            "PREF": 0
            if pref_name is None
            else constants.JAPAN_PREFS_NAME_TO_CODE[pref_name],
            "OUTPUT": "memory:",
        }

        try:
            context = QgsProcessingContext()
            results = self.run_algorithm(SearchJapanDpfAlgorithm(), parameters, context)
            if results is not None:
                layer = context.getMapLayer(results["OUTPUT"])
                fields = layer.fields().names()
                self.japan_dpf_set_table(
                    [
                        {
                            # NULL is QVariant in PyQt5
                            name: None if isinstance(value, QVariant) else value
                            for name, value in zip(fields, f.attributes())
                        }
                        for f in layer.getFeatures()
                    ]
                )
        finally:
            self.japanDpfSearchButton.setEnabled(True)
            self.japanDpfSearchButton.setText(i18n.tr("Search"))
            self.refresh()

    def japan_dpf_set_table(self, results: list):
        """
        Args:
            results: list of feeds, output of SearchJapanDpfAlgorithm as dicts
        """
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
