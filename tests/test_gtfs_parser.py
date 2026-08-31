"""Regression tests for the vendored gtfs_parser submodule.

Guards the pandas `.sum("count")` bug that broke aggregation on the
pandas shipped with QGIS 3.44+ (MIERUNE/gtfs-parser#26).
"""

import os

import pytest

try:
    from gtfs_parser import gtfs_parser
except ImportError:
    import gtfs_parser

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "gtfs_parser", "tests", "fixture"
)


@pytest.fixture
def gtfs():
    return gtfs_parser.GTFSFactory(FIXTURE_DIR)


def test_read_interpolated_stops(gtfs):
    aggregator = gtfs_parser.aggregate.Aggregator(gtfs)
    stops = aggregator.read_interpolated_stops()

    assert len(stops) > 0
    for stop in stops:
        assert stop["properties"]["count"] > 0
