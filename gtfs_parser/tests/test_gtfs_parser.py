import os
import unittest
import glob
import tempfile

from gtfs_parser.__main__ import GTFSParser  # nopep8

FIXTURE_DIR = os.path.join(os.path.dirname(
    __file__), 'fixture')


class TestGtfsParser(unittest.TestCase):
    gtfs_parser = GTFSParser(FIXTURE_DIR)
    gtfs_parser_frequency = GTFSParser(FIXTURE_DIR, as_frequency=True)
    gtfs_parser_frequency_unify = GTFSParser(FIXTURE_DIR,
                                             as_frequency=True,
                                             as_unify_stops=True)

    def test_init(self):
        # 13 txt files are in ./fixture
        self.assertEqual(
            13, len(glob.glob(os.path.join(FIXTURE_DIR, '*.txt'))))
        # read tables in constants.py
        self.assertEqual(12, len(self.gtfs_parser.dataframes.keys()))

        # as_frequency: some columns regarding frequency aggregation
        self.assertFalse(
            "similar_stop_id" in self.gtfs_parser.dataframes["stops"].columns)
        self.assertTrue(
            "similar_stop_id" in self.gtfs_parser_frequency.dataframes["stops"].columns)
        self.assertTrue(
            "similar_stop_id" in self.gtfs_parser_frequency_unify.dataframes["stops"].columns)

        # as_unify: some columns regarding stop-grouping added
        self.assertFalse(
            "position_id" in self.gtfs_parser.dataframes["stops"].columns)
        self.assertFalse(
            "position_id" in self.gtfs_parser_frequency.dataframes["stops"].columns)
        self.assertTrue(
            "position_id" in self.gtfs_parser_frequency_unify.dataframes["stops"].columns)

    def test_read_stops(self):
        # list of geojson-feature
        self.assertEqual(899, len(self.gtfs_parser.read_stops()))
        # num of features is not changed by aggregation
        self.assertEqual(899, len(self.gtfs_parser_frequency.read_stops()))
        self.assertEqual(
            899, len(self.gtfs_parser_frequency_unify.read_stops()))
        # remove no-route stops
        self.assertEqual(
            896, len(self.gtfs_parser.read_stops(ignore_no_route=True)))

    def test_read_routes(self):
        # num of features read_routes() outputs correspond to routes defined in routes.txt
        self.assertEqual(32, len(self.gtfs_parser.read_routes()))
        self.assertEqual(32, len(self.gtfs_parser.read_routes(no_shapes=True)))

        self.assertEqual(
            956, len(self.gtfs_parser_frequency.read_route_frequency()))
        self.assertEqual(
            918, len(self.gtfs_parser_frequency_unify.read_route_frequency()))
