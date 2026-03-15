"""pytest conftest: make plugin importable as 'plugin_dir' package."""

import csv
import os
import sys
import types
from pathlib import Path

import pytest

# The plugin root is this directory. For relative imports like
# `from ...kumoy` (in processing/upload_vector/algorithm.py) to work,
# the plugin root must be importable as a package — not as top-level.
#
# Register a virtual 'plugin_dir' package whose __path__ points to the
# plugin root.  This avoids creating a filesystem symlink outside the
# project directory (which can fail in Docker / read-only environments).
_plugin_root = Path(__file__).resolve().parent

_pkg = types.ModuleType("plugin_dir")
_pkg.__path__ = [str(_plugin_root)]
sys.modules["plugin_dir"] = _pkg

# Remove the plugin root from sys.path so that plugin subpackages
# (e.g. 'processing/') don't shadow QGIS built-in modules.
# Plugin modules must be imported via 'plugin_dir.xxx' instead.
_plugin_root_str = str(_plugin_root)
sys.path[:] = [p for p in sys.path if p not in (_plugin_root_str, "")]


@pytest.fixture(scope="session")
def qgis_plugin_path(qgis_app):
    """Add QGIS's built-in plugin directory to sys.path.

    Depends on qgis_app (provided by pytest-qgis) to ensure
    QgsApplication is fully initialized before querying pkgDataPath().
    """
    from qgis.core import QgsApplication

    qgis_plugins = os.path.join(QgsApplication.pkgDataPath(), "python", "plugins")
    if os.path.isdir(qgis_plugins) and qgis_plugins not in sys.path:
        sys.path.append(qgis_plugins)


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


@pytest.fixture()
def minimal_gtfs(tmp_path: Path) -> Path:
    """Create a minimal set of GTFS CSV files and return the folder path."""
    _create_minimal_gtfs(tmp_path)
    return tmp_path


def _create_minimal_gtfs(folder: Path) -> None:
    """Create a minimal set of GTFS CSV files for testing."""
    _write_csv(
        folder / "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [
            ["S1", "Stop A", "35.0", "139.0"],
            ["S2", "Stop B", "35.1", "139.1"],
            ["S3", "Stop C", "35.2", "139.2"],
        ],
    )
    _write_csv(
        folder / "routes.txt",
        ["route_id", "route_short_name", "route_long_name", "route_type"],
        [
            ["R1", "Route 1", "Route One", "3"],
        ],
    )
    _write_csv(
        folder / "trips.txt",
        ["route_id", "service_id", "trip_id"],
        [
            ["R1", "WD", "T1"],
            ["R1", "WD", "T2"],
        ],
    )
    _write_csv(
        folder / "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [
            ["T1", "08:00:00", "08:00:00", "S1", "1"],
            ["T1", "08:10:00", "08:10:00", "S2", "2"],
            ["T1", "08:20:00", "08:20:00", "S3", "3"],
            ["T2", "09:00:00", "09:00:00", "S1", "1"],
            ["T2", "09:10:00", "09:10:00", "S3", "2"],
        ],
    )
    _write_csv(
        folder / "calendar.txt",
        [
            "service_id",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "start_date",
            "end_date",
        ],
        [
            ["WD", "1", "1", "1", "1", "1", "0", "0", "20240101", "20241231"],
        ],
    )
    _write_csv(
        folder / "calendar_dates.txt",
        ["service_id", "date", "exception_type"],
        [
            # Remove WD service on 2024-01-03 (Wednesday)
            ["WD", "20240103", "2"],
        ],
    )
