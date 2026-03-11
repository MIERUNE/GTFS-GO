from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import tempfile

from ..gtfs_csv import CsvTable, load_gtfs_folder, save_gtfs_folder
from ..gtfs_duckdb import init_gtfs_connection
from .csv_table_widget import CsvTableWidget

_CRS_4326 = QgsCoordinateReferenceSystem.fromEpsgId(4326)

# Preferred tab order for common GTFS files
_TAB_ORDER = [
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
    "shapes.txt",
    "calendar.txt",
    "calendar_dates.txt",
]

# FK relations: (source_file, source_column) -> (target_file, target_column)
_FK_RELATIONS: list[tuple[str, str, str, str]] = [
    ("stop_times.txt", "stop_id", "stops.txt", "stop_id"),
    ("stop_times.txt", "trip_id", "trips.txt", "trip_id"),
    ("trips.txt", "route_id", "routes.txt", "route_id"),
    ("trips.txt", "service_id", "calendar.txt", "service_id"),
    ("stops.txt", "parent_station", "stops.txt", "stop_id"),
]


class GtfsEditorDock(QDockWidget):
    def __init__(self, iface, parent=None) -> None:
        super().__init__("GTFS Editor", parent)
        self.iface = iface
        self.folder: str | None = None
        self.tables: dict[str, CsvTable] = {}
        self.table_widgets: dict[str, CsvTableWidget] = {}
        self.stops_layer: QgsVectorLayer | None = None
        self.routes_layer: QgsVectorLayer | None = None
        self._routes_has_shapes: bool = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)

        # Toolbar
        toolbar = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText("Select GTFS folder...")
        toolbar.addWidget(self.folder_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        toolbar.addWidget(browse_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        toolbar.addWidget(save_btn)

        update_map_btn = QPushButton("Update Map")
        update_map_btn.clicked.connect(self._on_update_map)
        toolbar.addWidget(update_map_btn)

        layout.addLayout(toolbar)

        # Tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        self.setWidget(container)

    # -- Folder selection & loading --

    def _on_browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select GTFS Folder", "", QFileDialog.ShowDirsOnly
        )
        if not folder:
            return
        self._load_folder(folder)

    def _load_folder(self, folder: str) -> None:
        self.folder = folder
        self.folder_edit.setText(folder)
        self.tables = load_gtfs_folder(folder)

        # Clear old tabs
        self.tab_widget.clear()
        self.table_widgets.clear()

        # Build ordered list of filenames
        ordered = [f for f in _TAB_ORDER if f in self.tables]
        ordered += sorted(f for f in self.tables if f not in _TAB_ORDER)

        for filename in ordered:
            table = self.tables[filename]
            widget = CsvTableWidget(table.headers, list(table.rows), self)
            self.tab_widget.addTab(widget, filename)
            self.table_widgets[filename] = widget

        # Build stop_id index and add zoom button for stops tab
        if "stops.txt" in self.table_widgets:
            self.table_widgets["stops.txt"].model.build_index("stop_id")
            self.table_widgets["stops.txt"].add_toolbar_button(
                "Zoom to", "Zoom to selected stop", self._on_zoom_to_stop
            )

        # Validate FK on tab switch
        self.tab_widget.currentChanged.connect(self._update_validation)
        self._update_validation()

    def _update_validation(self) -> None:
        """Rebuild FK validation sets for all tables."""
        # Collect valid ID sets from target tables
        id_sets: dict[tuple[str, str], set[str]] = {}
        for _, _, target_file, target_col in _FK_RELATIONS:
            key = (target_file, target_col)
            if key in id_sets:
                continue
            widget = self.table_widgets.get(target_file)
            if not widget:
                continue
            headers = widget.model.get_headers()
            if target_col not in headers:
                continue
            col_idx = headers.index(target_col)
            id_sets[key] = {
                row[col_idx] for row in widget.model.get_rows() if row[col_idx]
            }

        # Apply to source models
        for src_file, src_col, target_file, target_col in _FK_RELATIONS:
            widget = self.table_widgets.get(src_file)
            if not widget:
                continue
            valid = id_sets.get((target_file, target_col))
            if valid is not None:
                widget.model.set_valid_values(src_col, valid)

    def _on_zoom_to_stop(self) -> None:
        """Zoom the map canvas to the selected stop's coordinates."""
        widget = self.table_widgets.get("stops.txt")
        if not widget:
            return
        indexes = widget.view.selectionModel().selectedIndexes()
        if not indexes:
            return

        row = indexes[0].row()
        headers = widget.model.get_headers()
        rows = widget.model.get_rows()
        try:
            lon = float(rows[row][headers.index("stop_lon")])
            lat = float(rows[row][headers.index("stop_lat")])
        except (ValueError, IndexError):
            return

        canvas = self.iface.mapCanvas()
        center = QgsPointXY(lon, lat)
        canvas.setCenter(center)
        canvas.zoomScale(5000)
        canvas.refresh()

    # -- Save --

    def _on_save(self) -> None:
        if not self.folder or not self.tables:
            return
        # Sync model data back to tables dict
        for filename, widget in self.table_widgets.items():
            self.tables[filename] = CsvTable(
                headers=widget.model.get_headers(),
                rows=widget.model.get_rows(),
            )
        save_gtfs_folder(self.folder, self.tables)
        self.iface.messageBar().pushSuccess("GTFS Editor", "Saved successfully.")

    # -- Update Map --

    def _current_tables(self) -> dict[str, CsvTable]:
        """Get current table data from all models (without saving to disk)."""
        return {
            filename: CsvTable(
                headers=widget.model.get_headers(),
                rows=widget.model.get_rows(),
            )
            for filename, widget in self.table_widgets.items()
        }

    def _on_update_map(self) -> None:
        if not self.folder:
            return
        self._disconnect_stops_layer()
        self._remove_existing_gtfs_layers()

        # Write current table data to a temp folder for DuckDB
        tables = self._current_tables()
        with tempfile.TemporaryDirectory() as tmpdir:
            save_gtfs_folder(tmpdir, tables)
            gtfs = init_gtfs_connection(tmpdir)
            try:
                stops_layer = self._create_stops_layer(gtfs.conn)
                routes_layer = self._create_routes_layer(gtfs.conn, gtfs.has_shapes)
                self._routes_has_shapes = gtfs.has_shapes
            finally:
                gtfs.conn.close()

        layers = [l for l in [stops_layer, routes_layer] if l is not None]
        if layers:
            QgsProject.instance().addMapLayers(layers)

        self.routes_layer = routes_layer
        if stops_layer is not None:
            self._connect_stops_layer(stops_layer)

    def _create_stops_layer(self, conn) -> QgsVectorLayer:
        layer = QgsVectorLayer(
            "Point?crs=EPSG:4326&field=stop_id:string&field=stop_name:string",
            "GTFS Stops",
            "memory",
        )
        layer.setCustomProperty("gtfs_go_role", "stops")

        result = conn.execute(
            "SELECT stop_id, stop_name, ST_AsText(geom) AS wkt FROM stops_geo"
        ).fetchall()

        features = []
        for stop_id, stop_name, wkt in result:
            feat = QgsFeature(layer.fields())
            feat.setAttribute("stop_id", stop_id)
            feat.setAttribute("stop_name", stop_name)
            feat.setGeometry(QgsGeometry.fromWkt(wkt))
            features.append(feat)

        layer.dataProvider().addFeatures(features)
        return layer

    def _create_routes_layer(self, conn, has_shapes: bool) -> QgsVectorLayer | None:
        if has_shapes:
            id_field = "shape_id"
            query = """
                SELECT shape_id,
                       ST_AsText(ST_MakeLine(
                           LIST(ST_Point(shape_pt_lon, shape_pt_lat)
                                ORDER BY shape_pt_sequence)
                       )) AS wkt
                FROM shapes GROUP BY shape_id
            """
        else:
            id_field = "trip_id"
            query = """
                SELECT st.trip_id,
                       ST_AsText(ST_MakeLine(
                           LIST(sg.geom ORDER BY st.stop_sequence)
                       )) AS wkt
                FROM stop_times st
                JOIN stops_geo sg ON st.stop_id = sg.stop_id
                GROUP BY st.trip_id
            """

        layer = QgsVectorLayer(
            f"LineString?crs=EPSG:4326&field={id_field}:string",
            "GTFS Routes",
            "memory",
        )
        layer.setCustomProperty("gtfs_go_role", "routes")

        result = conn.execute(query).fetchall()
        features = []
        for id_value, wkt in result:
            feat = QgsFeature(layer.fields())
            feat.setAttribute(id_field, id_value)
            feat.setGeometry(QgsGeometry.fromWkt(wkt))
            features.append(feat)

        layer.dataProvider().addFeatures(features)
        return layer

    def _remove_existing_gtfs_layers(self) -> None:
        project = QgsProject.instance()
        to_remove = [
            layer_id
            for layer_id, layer in project.mapLayers().items()
            if layer.customProperty("gtfs_go_role") in ("stops", "routes")
        ]
        for layer_id in to_remove:
            project.removeMapLayer(layer_id)

    # -- Geometry feedback --

    def _connect_stops_layer(self, layer: QgsVectorLayer) -> None:
        self.stops_layer = layer
        self.stops_layer.editingStarted.connect(self._on_editing_started)
        self.stops_layer.editingStopped.connect(self._on_editing_stopped)
        QgsProject.instance().layerWillBeRemoved.connect(self._on_layer_will_be_removed)

    def _disconnect_stops_layer(self) -> None:
        if self.stops_layer is None:
            return
        try:
            self.stops_layer.editingStarted.disconnect(self._on_editing_started)
            self.stops_layer.editingStopped.disconnect(self._on_editing_stopped)
            self._disconnect_edit_buffer()
            QgsProject.instance().layerWillBeRemoved.disconnect(
                self._on_layer_will_be_removed
            )
        except TypeError:
            pass
        self.stops_layer = None

    def _on_editing_started(self) -> None:
        """Connect to editBuffer's geometryChanged when editing begins."""
        if self.stops_layer is None or self.stops_layer.editBuffer() is None:
            return
        self.stops_layer.editBuffer().geometryChanged.connect(
            self._on_geometry_changed
        )

    def _disconnect_edit_buffer(self) -> None:
        """Disconnect from editBuffer's geometryChanged if connected."""
        if self.stops_layer is None or self.stops_layer.editBuffer() is None:
            return
        try:
            self.stops_layer.editBuffer().geometryChanged.disconnect(
                self._on_geometry_changed
            )
        except TypeError:
            pass

    def _on_geometry_changed(self, fid: int, geometry: QgsGeometry) -> None:
        if "stops.txt" not in self.table_widgets or self.stops_layer is None:
            return
        feature = self.stops_layer.getFeature(fid)
        stop_id = str(feature["stop_id"])
        point = geometry.asPoint()

        # Update stops table
        model = self.table_widgets["stops.txt"].model
        row = model.find_row_by_key(stop_id)
        if row is None:
            return

        headers = model.get_headers()
        col_lon = headers.index("stop_lon") if "stop_lon" in headers else None
        col_lat = headers.index("stop_lat") if "stop_lat" in headers else None
        if col_lon is not None:
            model.update_cell(row, col_lon, str(point.x()))
        if col_lat is not None:
            model.update_cell(row, col_lat, str(point.y()))

        # Rebuild routes layer
        self._rebuild_routes_from_tables()

    def _rebuild_routes_from_tables(self) -> None:
        """Rebuild routes layer from current in-memory CSV table data."""
        if not self.routes_layer or self._routes_has_shapes:
            return

        stops_widget = self.table_widgets.get("stops.txt")
        stop_times_widget = self.table_widgets.get("stop_times.txt")
        if not stops_widget or not stop_times_widget:
            return

        # Build stop_id -> QgsPointXY from current table data
        sh = stops_widget.model.get_headers()
        sid_col = sh.index("stop_id")
        lon_col = sh.index("stop_lon")
        lat_col = sh.index("stop_lat")
        stop_pos: dict[str, QgsPointXY] = {}
        for row in stops_widget.model.get_rows():
            try:
                stop_pos[row[sid_col]] = QgsPointXY(
                    float(row[lon_col]), float(row[lat_col])
                )
            except (ValueError, IndexError):
                continue

        # Build trip_id -> ordered stop_ids from stop_times table
        sth = stop_times_widget.model.get_headers()
        trip_col = sth.index("trip_id")
        st_stop_col = sth.index("stop_id")
        seq_col = sth.index("stop_sequence")
        trip_stops: dict[str, list[tuple[int, str]]] = {}
        for row in stop_times_widget.model.get_rows():
            try:
                trip_stops.setdefault(row[trip_col], []).append(
                    (int(row[seq_col]), row[st_stop_col])
                )
            except (ValueError, IndexError):
                continue

        # Build new features
        features = []
        for trip_id, stops in trip_stops.items():
            stops.sort(key=lambda x: x[0])
            points = [
                stop_pos[sid] for _, sid in stops if sid in stop_pos
            ]
            if len(points) < 2:
                continue
            feat = QgsFeature(self.routes_layer.fields())
            feat.setAttribute("trip_id", trip_id)
            feat.setGeometry(QgsGeometry.fromPolylineXY(points))
            features.append(feat)

        # Replace all features in existing layer
        provider = self.routes_layer.dataProvider()
        provider.truncate()
        provider.addFeatures(features)
        self.routes_layer.updateExtents()
        self.routes_layer.triggerRepaint()

    def _on_editing_stopped(self) -> None:
        """Re-sync stop coordinates and routes after edit session ends."""
        if self.stops_layer is None or "stops.txt" not in self.table_widgets:
            return
        model = self.table_widgets["stops.txt"].model
        headers = model.get_headers()
        col_lon = headers.index("stop_lon") if "stop_lon" in headers else None
        col_lat = headers.index("stop_lat") if "stop_lat" in headers else None
        if col_lon is None or col_lat is None:
            return

        for feature in self.stops_layer.getFeatures():
            stop_id = str(feature["stop_id"])
            row = model.find_row_by_key(stop_id)
            if row is None:
                continue
            point = feature.geometry().asPoint()
            model.update_cell(row, col_lon, str(point.x()))
            model.update_cell(row, col_lat, str(point.y()))

        self._rebuild_routes_from_tables()

    def _on_layer_will_be_removed(self, layer_id: str) -> None:
        if self.stops_layer and self.stops_layer.id() == layer_id:
            self._disconnect_stops_layer()
        if self.routes_layer and self.routes_layer.id() == layer_id:
            self.routes_layer = None

    def cleanup(self) -> None:
        """Disconnect all signals. Called from plugin unload."""
        self._disconnect_stops_layer()
