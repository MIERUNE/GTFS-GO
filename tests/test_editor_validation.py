"""Tests for FK validation logic used in the GTFS editor (requires QGIS/Qt)."""

import pytest

from plugin_dir.ui.csv_table_widget import CsvTableModel
from plugin_dir.ui.gtfs_editor_dock import _FK_RELATIONS

pytestmark = pytest.mark.usefixtures("qgis_plugin_path")


def _build_models() -> dict[str, CsvTableModel]:
    """Build a minimal set of CsvTableModels matching GTFS tables."""
    return {
        "stops.txt": CsvTableModel(
            ["stop_id", "stop_name", "stop_lat", "stop_lon", "parent_station"],
            [
                ["S1", "Stop A", "35.0", "139.0", ""],
                ["S2", "Stop B", "35.1", "139.1", ""],
            ],
        ),
        "routes.txt": CsvTableModel(
            ["route_id", "route_short_name", "route_long_name", "route_type"],
            [["R1", "Route 1", "Route One", "3"]],
        ),
        "trips.txt": CsvTableModel(
            ["route_id", "service_id", "trip_id"],
            [
                ["R1", "WD", "T1"],
                ["R1", "WD", "T2"],
            ],
        ),
        "stop_times.txt": CsvTableModel(
            ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
            [
                ["T1", "08:00:00", "08:00:00", "S1", "1"],
                ["T1", "08:10:00", "08:10:00", "S2", "2"],
            ],
        ),
        "calendar.txt": CsvTableModel(
            ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"],
            [["WD", "1", "1", "1", "1", "1", "0", "0", "20240101", "20241231"]],
        ),
    }


def _apply_fk_validation(models: dict[str, CsvTableModel]) -> None:
    """Reproduce the FK validation logic from GtfsEditorDock._update_validation."""
    id_sets: dict[tuple[str, str], set[str]] = {}
    for _, _, target_file, target_col in _FK_RELATIONS:
        key = (target_file, target_col)
        if key in id_sets:
            continue
        model = models.get(target_file)
        if not model:
            continue
        headers = model.get_headers()
        if target_col not in headers:
            continue
        col_idx = headers.index(target_col)
        id_sets[key] = {row[col_idx] for row in model.get_rows() if row[col_idx]}

    for src_file, src_col, target_file, target_col in _FK_RELATIONS:
        model = models.get(src_file)
        if not model:
            continue
        valid = id_sets.get((target_file, target_col))
        if valid is not None:
            model.set_valid_values(src_col, valid)


def _collect_violations(models: dict[str, CsvTableModel]) -> list[str]:
    """Reproduce the violation collection logic from GtfsEditorDock._collect_violations."""
    _apply_fk_validation(models)
    violations: list[str] = []
    for src_file, src_col, target_file, target_col in _FK_RELATIONS:
        model = models.get(src_file)
        if not model:
            continue
        headers = model.get_headers()
        if src_col not in headers:
            continue
        col_idx = headers.index(src_col)
        valid = model._valid_values.get(col_idx)
        if valid is None:
            continue

        invalid_values: set[str] = set()
        for row in model.get_rows():
            value = row[col_idx]
            if value and value not in valid:
                invalid_values.add(value)
        if invalid_values:
            violations.append(
                f"{src_file}.{src_col} -> {target_file}.{target_col}"
            )
    return violations


class TestFkRelations:
    def test_fk_relations_defined(self):
        assert len(_FK_RELATIONS) > 0

    def test_fk_relations_structure(self):
        for rel in _FK_RELATIONS:
            assert len(rel) == 4
            src_file, src_col, target_file, target_col = rel
            assert src_file.endswith(".txt")
            assert target_file.endswith(".txt")


class TestValidDataNoViolations:
    def test_no_violations_with_valid_data(self):
        models = _build_models()
        violations = _collect_violations(models)
        assert violations == []

    def test_valid_values_applied(self):
        models = _build_models()
        _apply_fk_validation(models)

        # stop_times.stop_id should have S1, S2 as valid
        st_model = models["stop_times.txt"]
        headers = st_model.get_headers()
        col_idx = headers.index("stop_id")
        assert col_idx in st_model._valid_values
        assert "S1" in st_model._valid_values[col_idx]
        assert "S2" in st_model._valid_values[col_idx]


class TestFkViolationDetection:
    def test_invalid_stop_id_in_stop_times(self):
        models = _build_models()
        # Add a row with invalid stop_id
        models["stop_times.txt"]._rows.append(
            ["T1", "08:30:00", "08:30:00", "INVALID_STOP", "3"]
        )
        violations = _collect_violations(models)
        assert any("stop_times.txt.stop_id" in v for v in violations)

    def test_invalid_trip_id_in_stop_times(self):
        models = _build_models()
        models["stop_times.txt"]._rows.append(
            ["INVALID_TRIP", "08:30:00", "08:30:00", "S1", "3"]
        )
        violations = _collect_violations(models)
        assert any("stop_times.txt.trip_id" in v for v in violations)

    def test_invalid_route_id_in_trips(self):
        models = _build_models()
        models["trips.txt"]._rows.append(["INVALID_ROUTE", "WD", "T3"])
        violations = _collect_violations(models)
        assert any("trips.txt.route_id" in v for v in violations)

    def test_invalid_service_id_in_trips(self):
        models = _build_models()
        models["trips.txt"]._rows.append(["R1", "INVALID_SVC", "T3"])
        violations = _collect_violations(models)
        assert any("trips.txt.service_id" in v for v in violations)

    def test_invalid_parent_station(self):
        models = _build_models()
        # Set a parent_station that doesn't exist as stop_id
        models["stops.txt"]._rows.append(
            ["S3", "Stop C", "35.2", "139.2", "INVALID_PARENT"]
        )
        violations = _collect_violations(models)
        assert any("stops.txt.parent_station" in v for v in violations)

    def test_empty_fk_value_not_flagged(self):
        """Empty FK values should not be treated as violations."""
        models = _build_models()
        # parent_station is empty for all stops - should be fine
        violations = _collect_violations(models)
        assert not any("parent_station" in v for v in violations)
