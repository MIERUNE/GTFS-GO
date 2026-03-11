"""Tests for SQL query generation in gtfs_aggregate (requires duckdb for syntax validation)."""

import re

import duckdb
import pytest
from plugin_dir.algorithms.gtfs_aggregate import (
    _aggregated_segments_query,
    _aggregated_stops_query,
    _stop_grouping_cte,
)
from plugin_dir.gtfs_duckdb import init_gtfs_connection

from conftest import create_minimal_gtfs

pytestmark = pytest.mark.usefixtures("qgis_plugin_path")


class TestStopGroupingCte:
    def test_returns_string(self):
        result = _stop_grouping_cte("_", 0.003)
        assert isinstance(result, str)

    def test_contains_key_cte_names(self):
        result = _stop_grouping_cte("_", 0.003)
        assert "parent_station_groups" in result
        assert "id_prefix_groups" in result
        assert "proximity_groups" in result
        assert "all_stop_relations" in result
        assert "similar_stop_attributes" in result

    def test_delimiter_escaped(self):
        """Special regex characters in delimiter should be escaped."""
        result = _stop_grouping_cte(".", 0.003)
        assert re.escape(".") in result

    def test_max_distance_in_query(self):
        result = _stop_grouping_cte("_", 0.005)
        assert "0.005" in result


class TestAggregatedStopsQuery:
    def test_returns_valid_sql(self, tmp_path):
        """Query should execute without syntax errors on actual GTFS data."""
        create_minimal_gtfs(tmp_path)
        gtfs = init_gtfs_connection(str(tmp_path))
        try:
            query = _aggregated_stops_query("_", 0.003)
            result = gtfs.conn.execute(query).fetchall()
            assert isinstance(result, list)
        finally:
            gtfs.conn.close()

    def test_output_columns(self, tmp_path):
        create_minimal_gtfs(tmp_path)
        gtfs = init_gtfs_connection(str(tmp_path))
        try:
            query = _aggregated_stops_query("_", 0.003)
            desc = gtfs.conn.execute(query).description
            col_names = [d[0] for d in desc]
            assert "similar_stop_id" in col_names
            assert "similar_stop_name" in col_names
            assert "stop_count" in col_names
            assert "trip_count" in col_names
            assert "wkt" in col_names
        finally:
            gtfs.conn.close()


class TestAggregatedSegmentsQuery:
    def test_returns_valid_sql(self, tmp_path):
        """Query should execute without syntax errors on actual GTFS data."""
        create_minimal_gtfs(tmp_path)
        gtfs = init_gtfs_connection(str(tmp_path))
        try:
            query = _aggregated_segments_query("_", 0.003)
            result = gtfs.conn.execute(query).fetchall()
            assert isinstance(result, list)
        finally:
            gtfs.conn.close()

    def test_output_columns(self, tmp_path):
        create_minimal_gtfs(tmp_path)
        gtfs = init_gtfs_connection(str(tmp_path))
        try:
            query = _aggregated_segments_query("_", 0.003)
            desc = gtfs.conn.execute(query).description
            col_names = [d[0] for d in desc]
            assert "from_similar_stop" in col_names
            assert "to_similar_stop" in col_names
            assert "trip_count" in col_names
            assert "wkt" in col_names
        finally:
            gtfs.conn.close()


class TestDifferentDelimiters:
    """Ensure queries work with various delimiter characters."""

    def test_dot_delimiter(self, tmp_path):
        create_minimal_gtfs(tmp_path)
        gtfs = init_gtfs_connection(str(tmp_path))
        try:
            query = _aggregated_stops_query(".", 0.003)
            gtfs.conn.execute(query).fetchall()
        finally:
            gtfs.conn.close()

    def test_hyphen_delimiter(self, tmp_path):
        create_minimal_gtfs(tmp_path)
        gtfs = init_gtfs_connection(str(tmp_path))
        try:
            query = _aggregated_stops_query("-", 0.003)
            gtfs.conn.execute(query).fetchall()
        finally:
            gtfs.conn.close()
