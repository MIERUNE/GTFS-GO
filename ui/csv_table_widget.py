from __future__ import annotations

from qgis.PyQt.QtCore import QAbstractTableModel, QModelIndex, Qt
from qgis.PyQt.QtWidgets import QTableView, QVBoxLayout, QWidget


class CsvTableModel(QAbstractTableModel):
    """Editable table model backed by a list-of-lists."""

    def __init__(
        self, headers: list[str], rows: list[list[str]], parent=None
    ) -> None:
        super().__init__(parent)
        self._headers = headers
        self._rows = rows
        self._row_index: dict[str, int] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.DisplayRole, Qt.EditRole):
            return self._rows[index.row()][index.column()]
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
