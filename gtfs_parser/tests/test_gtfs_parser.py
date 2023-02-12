import os
import unittest
import glob

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
        # num of stops is not changed by aggregation
        self.assertEqual(899, len(self.gtfs_parser_frequency.read_stops()))
        # num of stops is not changed by as_unify_stops
        self.assertEqual(
            899, len(self.gtfs_parser_frequency_unify.read_stops()))

        # remove no-route stops
        self.assertEqual(
            896, len(self.gtfs_parser.read_stops(ignore_no_route=True)))

    def test_read_routes(self):
        # num of features in routes.geojson depends on not shapes.txt but routes.txt
        self.assertEqual(32, len(self.gtfs_parser.read_routes()))
        self.assertEqual(32, len(self.gtfs_parser.read_routes(no_shapes=True)))
        # as_frequency and as_unify make no effect to read_routes()
        self.assertEqual(
            32, len(self.gtfs_parser_frequency.read_routes(no_shapes=True)))
        self.assertEqual(
            32, len(self.gtfs_parser_frequency_unify.read_routes(no_shapes=True)))

    def test_read_interpolated_stops(self):
        with self.assertRaises(TypeError):
            # read_interpolated_stops() needs as_frequency=True
            self.gtfs_parser.read_interpolated_stops()

        # read_interpolated_stops unify stops having same lat-lon into one featrure.
        # there are no stops having same lat-lon in fixture
        self.assertEqual(
            899, len(self.gtfs_parser_frequency.read_interpolated_stops()))

        # as_unify means near and similar named stops move into same lat-lon(centroid of them)
        self.assertEqual(
            518, len(self.gtfs_parser_frequency_unify.read_interpolated_stops()))

    def test_read_route_frequency(self):
        with self.assertRaises(KeyError):
            self.gtfs_parser.read_route_frequency()

        # each route_frequency feature is drawn between 2 stops
        self.assertEqual(
            956, len(self.gtfs_parser_frequency.read_route_frequency()))
        # unify some 'similar' stops into same position, this decrease num of route_frequency features
        self.assertEqual(
            918, len(self.gtfs_parser_frequency_unify.read_route_frequency()))

        # out of service of GTFS -> 0
        self.assertEqual(0, len(
            self.gtfs_parser_frequency_unify.read_route_frequency(yyyymmdd="20210530")))

        # some routes are not in service on 20210730, Friday
        freq20210730 = self.gtfs_parser_frequency_unify.read_route_frequency(
            yyyymmdd="20210730")
        self.assertEqual(916, len(freq20210730))
        self.assertEqual(114, freq20210730[0]["properties"]["frequency"])

        # 20210801 - Sunday
        freq20210801 = self.gtfs_parser_frequency_unify.read_route_frequency(
            yyyymmdd="20210801")
        self.assertEqual(736, len(freq20210801))
        self.assertEqual(62, freq20210801[0]["properties"]["frequency"])
