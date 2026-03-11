"""Tests for CsvTableModel (requires QGIS/Qt environment)."""

from qgis.PyQt.QtCore import Qt

from plugin_dir.ui.csv_table_widget import CsvTableModel


def _make_model(
    headers=None, rows=None
) -> CsvTableModel:
    if headers is None:
        headers = ["stop_id", "stop_name", "stop_lat", "stop_lon"]
    if rows is None:
        rows = [
            ["S1", "Stop A", "35.0", "139.0"],
            ["S2", "Stop B", "35.1", "139.1"],
        ]
    return CsvTableModel(headers, rows)


class TestBasicAccess:
    def test_row_count(self):
        model = _make_model()
        assert model.rowCount() == 2

    def test_column_count(self):
        model = _make_model()
        assert model.columnCount() == 4

    def test_data_display_role(self):
        model = _make_model()
        idx = model.index(0, 0)
        assert model.data(idx, Qt.DisplayRole) == "S1"

    def test_data_edit_role(self):
        model = _make_model()
        idx = model.index(1, 1)
        assert model.data(idx, Qt.EditRole) == "Stop B"

    def test_data_invalid_index(self):
        model = _make_model()
        from qgis.PyQt.QtCore import QModelIndex
        assert model.data(QModelIndex(), Qt.DisplayRole) is None

    def test_header_data_horizontal(self):
        model = _make_model()
        assert model.headerData(0, Qt.Horizontal) == "stop_id"
        assert model.headerData(2, Qt.Horizontal) == "stop_lat"

    def test_header_data_vertical(self):
        model = _make_model()
        assert model.headerData(0, Qt.Vertical) == "1"
        assert model.headerData(1, Qt.Vertical) == "2"

    def test_flags_editable(self):
        model = _make_model()
        idx = model.index(0, 0)
        assert model.flags(idx) & Qt.ItemIsEditable

    def test_get_headers(self):
        model = _make_model()
        assert model.get_headers() == ["stop_id", "stop_name", "stop_lat", "stop_lon"]

    def test_get_rows(self):
        model = _make_model()
        assert len(model.get_rows()) == 2


class TestSetData:
    def test_set_data(self):
        model = _make_model()
        idx = model.index(0, 1)
        result = model.setData(idx, "New Name", Qt.EditRole)
        assert result is True
        assert model.data(idx, Qt.DisplayRole) == "New Name"

    def test_set_data_wrong_role(self):
        model = _make_model()
        idx = model.index(0, 0)
        result = model.setData(idx, "X", Qt.DecorationRole)
        assert result is False

    def test_update_cell(self):
        model = _make_model()
        model.update_cell(0, 2, "99.9")
        assert model.get_rows()[0][2] == "99.9"


class TestRowOperations:
    def test_insert_row(self):
        model = _make_model()
        model.insert_row(1)
        assert model.rowCount() == 3
        assert model.get_rows()[1] == ["", "", "", ""]

    def test_insert_row_at_beginning(self):
        model = _make_model()
        model.insert_row(0)
        assert model.rowCount() == 3
        assert model.get_rows()[0] == ["", "", "", ""]
        assert model.get_rows()[1][0] == "S1"

    def test_insert_row_at_end(self):
        model = _make_model()
        model.insert_row(2)
        assert model.rowCount() == 3
        assert model.get_rows()[2] == ["", "", "", ""]

    def test_remove_rows(self):
        model = _make_model()
        model.remove_rows([0])
        assert model.rowCount() == 1
        assert model.get_rows()[0][0] == "S2"

    def test_remove_multiple_rows(self):
        rows = [["A", "1", "2", "3"], ["B", "4", "5", "6"], ["C", "7", "8", "9"]]
        model = _make_model(rows=rows)
        model.remove_rows([0, 2])
        assert model.rowCount() == 1
        assert model.get_rows()[0][0] == "B"

    def test_remove_rows_reverse_order(self):
        """Rows given in non-sorted order should be handled correctly."""
        rows = [["A", "1", "2", "3"], ["B", "4", "5", "6"], ["C", "7", "8", "9"]]
        model = _make_model(rows=rows)
        model.remove_rows([2, 0])
        assert model.rowCount() == 1
        assert model.get_rows()[0][0] == "B"


class TestFkValidation:
    def test_set_valid_values(self):
        model = _make_model()
        model.set_valid_values("stop_id", {"S1", "S2"})
        # No error brush for valid values
        idx = model.index(0, 0)
        assert model.data(idx, Qt.BackgroundRole) is None

    def test_invalid_value_returns_error_brush(self):
        model = _make_model()
        model.set_valid_values("stop_id", {"S1"})  # S2 is invalid
        idx = model.index(1, 0)  # S2
        result = model.data(idx, Qt.BackgroundRole)
        assert result is not None  # Should be _ERROR_BRUSH

    def test_empty_value_no_error(self):
        """Empty cell values should not trigger FK error."""
        model = _make_model(rows=[["", "Stop A", "35.0", "139.0"]])
        model.set_valid_values("stop_id", {"S1"})
        idx = model.index(0, 0)
        assert model.data(idx, Qt.BackgroundRole) is None

    def test_set_valid_values_unknown_column(self):
        """Setting valid values for non-existent column should be a no-op."""
        model = _make_model()
        model.set_valid_values("nonexistent", {"X"})
        # Should not raise


class TestIndex:
    def test_build_index_and_find(self):
        model = _make_model()
        model.build_index("stop_id")
        assert model.find_row_by_key("S1") == 0
        assert model.find_row_by_key("S2") == 1

    def test_find_missing_key(self):
        model = _make_model()
        model.build_index("stop_id")
        assert model.find_row_by_key("S999") is None

    def test_build_index_unknown_column(self):
        """Building index on non-existent column should be a no-op."""
        model = _make_model()
        model.build_index("nonexistent")
        assert model.find_row_by_key("S1") is None
