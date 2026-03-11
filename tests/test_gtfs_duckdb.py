"""Tests for gtfs_duckdb module (requires duckdb, no QGIS)."""

import csv
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

from plugin_dir.gtfs_duckdb import init_gtfs_connection


class TestInitGtfsConnection:
    def test_basic_init(self, minimal_gtfs: Path):
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            assert gtfs.conn is not None
        finally:
            gtfs.conn.close()

    def test_has_shapes_false(self, minimal_gtfs: Path):
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            assert gtfs.has_shapes is False
        finally:
            gtfs.conn.close()

    def test_has_shapes_true(self, minimal_gtfs: Path):
        with open(minimal_gtfs / "shapes.txt", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["shape_id", "shape_pt_sequence", "shape_pt_lon", "shape_pt_lat"]
            )
            writer.writerow(["SH1", "1", "139.0", "35.0"])
            writer.writerow(["SH1", "2", "139.1", "35.1"])

        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            assert gtfs.has_shapes is True
        finally:
            gtfs.conn.close()

    def test_stops_geo_has_geom_column(self, minimal_gtfs: Path):
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            cols = [
                row[0]
                for row in gtfs.conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'stops_geo'"
                ).fetchall()
            ]
            assert "geom" in cols
        finally:
            gtfs.conn.close()

    def test_parent_station_column_added(self, minimal_gtfs: Path):
        """parent_station column should exist even if not in source CSV."""
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            cols = [
                row[0]
                for row in gtfs.conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'stops_geo'"
                ).fetchall()
            ]
            assert "parent_station" in cols
        finally:
            gtfs.conn.close()

    def test_stop_count(self, minimal_gtfs: Path):
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            count = gtfs.conn.execute("SELECT COUNT(*) FROM stops_geo").fetchone()[0]
            assert count == 3
        finally:
            gtfs.conn.close()

    def test_tables_created(self, minimal_gtfs: Path):
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            tables = [row[0] for row in gtfs.conn.execute("SHOW TABLES").fetchall()]
            assert "stops_geo" in tables
            assert "stop_times" in tables
            assert "trips" in tables
            assert "routes" in tables
            assert "shapes" in tables  # Empty table created when no shapes.txt
        finally:
            gtfs.conn.close()
