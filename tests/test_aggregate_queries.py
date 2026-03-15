"""Tests for SQL query generation in gtfs_aggregate (requires duckdb for syntax validation)."""

import re
from pathlib import Path

import pytest
from plugin_dir.algorithms.gtfs_aggregate import (
    _aggregated_segments_query,
    _aggregated_stops_query,
    _stop_grouping_cte,
    _time_filter_cte,
)
from plugin_dir.gtfs_duckdb import init_gtfs_connection

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
    def test_returns_valid_sql(self, minimal_gtfs: Path):
        """Query should execute without syntax errors on actual GTFS data."""
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            query = _aggregated_stops_query("_", 0.003)
            result = gtfs.conn.execute(query).fetchall()
            assert isinstance(result, list)
        finally:
            gtfs.conn.close()

    def test_output_columns(self, minimal_gtfs: Path):
        gtfs = init_gtfs_connection(str(minimal_gtfs))
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
    def test_returns_valid_sql(self, minimal_gtfs: Path):
        """Query should execute without syntax errors on actual GTFS data."""
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            query = _aggregated_segments_query("_", 0.003)
            result = gtfs.conn.execute(query).fetchall()
            assert isinstance(result, list)
        finally:
            gtfs.conn.close()

    def test_output_columns(self, minimal_gtfs: Path):
        gtfs = init_gtfs_connection(str(minimal_gtfs))
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

    def test_dot_delimiter(self, minimal_gtfs: Path):
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            query = _aggregated_stops_query(".", 0.003)
            gtfs.conn.execute(query).fetchall()
        finally:
            gtfs.conn.close()

    def test_hyphen_delimiter(self, minimal_gtfs: Path):
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            query = _aggregated_stops_query("-", 0.003)
            gtfs.conn.execute(query).fetchall()
        finally:
            gtfs.conn.close()


class TestTimeFilterCte:
    """Tests for _time_filter_cte and datetime-filtered queries."""

    def test_no_filter_returns_effective_stop_times(self):
        result = _time_filter_cte(None, None)
        assert "effective_stop_times" in result
        assert "FROM stop_times" in result

    def test_filter_contains_active_services(self):
        result = _time_filter_cte("2024-01-01 00:00:00", "2024-01-02 00:00:00")
        assert "_active_services" in result
        assert "effective_stop_times" in result
        assert "gtfs_datetime" in result


class TestFilteredStopsQuery:
    """Datetime-filtered stops aggregation queries."""

    def test_no_filter_matches_original(self, minimal_gtfs: Path):
        """Without filter, result should equal the unfiltered query."""
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            r_orig = gtfs.conn.execute(
                _aggregated_stops_query("_", 0.003)
            ).fetchall()
            r_none = gtfs.conn.execute(
                _aggregated_stops_query("_", 0.003, None, None)
            ).fetchall()
            assert r_orig == r_none
        finally:
            gtfs.conn.close()

    def test_weekday_has_trips(self, minimal_gtfs: Path):
        """2024-01-01 (Monday) — service WD is active, should have trips."""
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            query = _aggregated_stops_query(
                "_", 0.003, "2024-01-01 00:00:00", "2024-01-02 00:00:00"
            )
            result = gtfs.conn.execute(query).fetchall()
            total_trips = sum(row[3] for row in result)
            assert total_trips > 0
        finally:
            gtfs.conn.close()

    def test_weekend_has_no_trips(self, minimal_gtfs: Path):
        """2024-01-06 (Saturday) — service WD is inactive, should have 0 trips."""
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            query = _aggregated_stops_query(
                "_", 0.003, "2024-01-06 00:00:00", "2024-01-07 00:00:00"
            )
            result = gtfs.conn.execute(query).fetchall()
            total_trips = sum(row[3] for row in result)
            assert total_trips == 0
        finally:
            gtfs.conn.close()

    def test_calendar_dates_exception(self, minimal_gtfs: Path):
        """2024-01-03 (Wednesday) removed by calendar_dates — 0 trips."""
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            query = _aggregated_stops_query(
                "_", 0.003, "2024-01-03 00:00:00", "2024-01-04 00:00:00"
            )
            result = gtfs.conn.execute(query).fetchall()
            total_trips = sum(row[3] for row in result)
            assert total_trips == 0
        finally:
            gtfs.conn.close()

    def test_time_window_filters(self, minimal_gtfs: Path):
        """Only T1 departs 08:00-08:20; filtering 07:00-08:05 should catch only S1."""
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            query = _aggregated_stops_query(
                "_", 0.003, "2024-01-01 07:00:00", "2024-01-01 08:05:00"
            )
            result = gtfs.conn.execute(query).fetchall()
            # Only S1 at 08:00 falls in [07:00, 08:05)
            total_trips = sum(row[3] for row in result)
            assert total_trips == 1
        finally:
            gtfs.conn.close()


class TestFilteredSegmentsQuery:
    """Datetime-filtered segments aggregation queries."""

    def test_weekday_has_segments(self, minimal_gtfs: Path):
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            query = _aggregated_segments_query(
                "_", 0.003, "2024-01-01 00:00:00", "2024-01-02 00:00:00"
            )
            result = gtfs.conn.execute(query).fetchall()
            total_trips = sum(row[4] for row in result)
            assert total_trips > 0
        finally:
            gtfs.conn.close()

    def test_weekend_has_no_segments(self, minimal_gtfs: Path):
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            query = _aggregated_segments_query(
                "_", 0.003, "2024-01-06 00:00:00", "2024-01-07 00:00:00"
            )
            result = gtfs.conn.execute(query).fetchall()
            total_trips = sum(row[4] for row in result)
            assert total_trips == 0
        finally:
            gtfs.conn.close()

    def test_multi_day_range(self, minimal_gtfs: Path):
        """Mon-Fri range should give 4x single-day count (Wed removed)."""
        gtfs = init_gtfs_connection(str(minimal_gtfs))
        try:
            q_one = _aggregated_stops_query(
                "_", 0.003, "2024-01-01 00:00:00", "2024-01-02 00:00:00"
            )
            one_day = sum(row[3] for row in gtfs.conn.execute(q_one).fetchall())

            # Mon-Fri (Jan 1-5): 4 active days (Wed removed)
            q_week = _aggregated_stops_query(
                "_", 0.003, "2024-01-01 00:00:00", "2024-01-06 00:00:00"
            )
            week = sum(row[3] for row in gtfs.conn.execute(q_week).fetchall())
            assert week == one_day * 4
        finally:
            gtfs.conn.close()
