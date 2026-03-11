from __future__ import annotations

from qgis.PyQt.QtCore import QAbstractTableModel, QModelIndex, Qt
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

_ERROR_BRUSH = QBrush(QColor(255, 200, 200))


class CsvTableModel(QAbstractTableModel):
    """Editable table model backed by a list-of-lists."""

    def __init__(
        self, headers: list[str], rows: list[list[str]], parent=None
    ) -> None:
        super().__init__(parent)
        self._headers = headers
        self._rows = rows
        self._row_index: dict[str, int] = {}
        # col_index -> set of valid values (for FK validation)
        self._valid_values: dict[int, set[str]] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.DisplayRole, Qt.EditRole):
            return self._rows[index.row()][index.column()]
        if role == Qt.BackgroundRole:
            col = index.column()
            if col in self._valid_values:
                value = self._rows[index.row()][col]
                if value and value not in self._valid_values[col]:
                    return _ERROR_BRUSH
        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if role == Qt.EditRole and index.isValid():
            self._rows[index.row()][index.column()] = str(value)
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            return True
        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return super().flags(index) | Qt.ItemIsEditable

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal and section < len(self._headers):
                return self._headers[section]
            if orientation == Qt.Vertical:
                return str(section + 1)
        return None

    def get_headers(self) -> list[str]:
        return self._headers

    def get_rows(self) -> list[list[str]]:
        return self._rows

    def update_cell(self, row: int, col: int, value: str) -> None:
        """Programmatically update a cell value (for geometry feedback)."""
        self._rows[row][col] = value
        index = self.index(row, col)
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])

    def insert_row(self, row: int) -> None:
        """Insert an empty row at the given position."""
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.insert(row, [""] * len(self._headers))
        self.endInsertRows()

    def remove_rows(self, rows: list[int]) -> None:
        """Remove rows at the given indices (in any order)."""
        for row in sorted(rows, reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._rows[row]
            self.endRemoveRows()

    def set_valid_values(self, column: str, valid: set[str]) -> None:
        """Set valid values for FK validation on a column."""
        if column not in self._headers:
            return
        col_idx = self._headers.index(column)
        if self._valid_values.get(col_idx) is valid:
            return
        self._valid_values[col_idx] = valid

    def build_index(self, key_column: str) -> None:
        """Build a lookup index mapping key_column values to row indices."""
        if key_column not in self._headers:
            return
        col_idx = self._headers.index(key_column)
        self._row_index = {row[col_idx]: i for i, row in enumerate(self._rows)}

    def find_row_by_key(self, value: str) -> int | None:
        """Find row index by key value. Requires build_index() first."""
        return self._row_index.get(value)


class CsvTableWidget(QWidget):
    """Widget wrapping a QTableView with a CsvTableModel."""

    def __init__(
        self, headers: list[str], rows: list[list[str]], parent=None
    ) -> None:
        super().__init__(parent)
        self.model = CsvTableModel(headers, rows, self)
        self.view = QTableView(self)
        self.view.setModel(self.model)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)

        add_btn = QPushButton("+")
        add_btn.setFixedWidth(30)
        add_btn.setToolTip("Add row")
        add_btn.clicked.connect(self._on_add_row)
        toolbar.addWidget(add_btn)

        remove_btn = QPushButton("-")
        remove_btn.setFixedWidth(30)
        remove_btn.setToolTip("Remove selected rows")
        remove_btn.clicked.connect(self._on_remove_rows)
        toolbar.addWidget(remove_btn)

        self._toolbar = toolbar
        toolbar.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self.view)

    def add_toolbar_button(self, text: str, tooltip: str, callback) -> QPushButton:
        """Add a custom button to the toolbar (before the stretch)."""
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        # Insert before the stretch item
        self._toolbar.insertWidget(self._toolbar.count() - 1, btn)
        return btn

    def _on_add_row(self) -> None:
        """Insert a new row below the current selection, or at the end."""
        indexes = self.view.selectionModel().selectedIndexes()
        if indexes:
            row = max(idx.row() for idx in indexes) + 1
        else:
            row = self.model.rowCount()
        self.model.insert_row(row)

    def _on_remove_rows(self) -> None:
        """Remove all selected rows."""
        indexes = self.view.selectionModel().selectedIndexes()
        if not indexes:
            return
        rows = sorted(set(idx.row() for idx in indexes))
        self.model.remove_rows(rows)
