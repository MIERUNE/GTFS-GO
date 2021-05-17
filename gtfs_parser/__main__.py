import json
import os
import glob
import zipfile
import tempfile
from functools import lru_cache
import datetime

import pandas as pd

try:
    # QGIS-import
    from .constants import GTFS_DATATYPES
except:
    from constants import GTFS_DATATYPES


class GTFSParser:
    def __init__(self, src_dir: str, as_frequency=False, delimiter='', max_distance_degree=0.01):
        txts = glob.glob(os.path.join(
            src_dir, '**', '*.txt'), recursive=True)
        self.dataframes = {}
        for txt in txts:
            datatype = os.path.basename(txt).split('.')[0]
            if os.path.basename(datatype) not in GTFS_DATATYPES:
                print(f'{datatype} is not specified in GTFS, skipping...')
                continue
            with open(txt, encoding='utf-8_sig') as t:
                df = pd.read_csv(t, dtype=str)
                if len(df) == 0:
                    print(f'{datatype}.txt is empty, skipping...')
                    continue
                self.dataframes[os.path.basename(txt).split('.')[0]] = df
        for datatype in GTFS_DATATYPES:
            if GTFS_DATATYPES[datatype]['required'] and \
                    datatype not in self.dataframes:
                raise FileNotFoundError(f'{datatype} is not exists.')

        # cast some numeric value columns to int or float
        self.dataframes['stops'] = self.dataframes['stops'].astype(
            {'stop_lon': float, 'stop_lat': float})
        self.dataframes['stop_times'] = self.dataframes['stop_times'].astype({
                                                                             'stop_sequence': int})
        self.dataframes['shapes'] = self.dataframes['shapes'].astype(
            {'shape_pt_lon': float, 'shape_pt_lat': float, 'shape_pt_sequence': int})

        if 'parent_station' not in self.dataframes.get('stops').columns:
            # parent_station is optional column on GTFS but use in this module
            # when parent_station is not in stops, fill by 'nan' (not NaN)
            self.dataframes['stops']['parent_station'] = 'nan'

        if as_frequency:
            self.dataframes['stops']['similar_stops_centroid'] = self.dataframes['stops']['stop_id'].map(
                lambda stop_id: self.get_similar_stops_centroid(stop_id, delimiter, max_distance_degree))

    def read_stops(self, ignore_no_route=False) -> list:
        """
        read stops by stops table

        Args:
            ignore_no_route (bool, optional): stops unconnected to routes are skipped. Defaults to False.

        Returns:
            list: [description]
        """

        stops_df = self.dataframes['stops'][[
            'stop_id', 'stop_lat', 'stop_lon', 'stop_name']]
        route_id_on_stops = self.get_route_ids_on_stops()

        features = []
        for stop in stops_df.itertuples():
            if stop.stop_id in route_id_on_stops:
                route_ids = route_id_on_stops.at[stop.stop_id].tolist()
            else:
                if ignore_no_route:
                    continue
                route_ids = []

            features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [stop.stop_lon, stop.stop_lat]
                },
                'properties': {
                    'stop_id': stop.stop_id,
                    'stop_name': stop.stop_name,
                    'route_ids': route_ids
                }
            })
        return features

    def get_route_ids_on_stops(self):
        stop_times_trip_df = pd.merge(
            self.dataframes['stop_times'],
            self.dataframes['trips'],
            on='trip_id',
        )
        group = stop_times_trip_df.groupby('stop_id')['route_id'].unique()
        group.apply(lambda x: x.sort())
        return group

    def read_interpolated_stops(self):
        """
        Read stops "interpolated" by parent station or stop_id or stop_name and distance.
        There are many similar stops that are near to each, has same name, or has same prefix in stop_id.
        In traffic analyzing, it is good for that similar stops to be grouped as same stop.
        This method group them by some elements, parent, id, name and distance.

        Args:
            delimiter (str, optional): stop_id delimiter, sample_A, sample_B, then delimiter is '_'. Defaults to ''.
            max_distance_degree (float, optional): distance limit in grouping by stop_name. Defaults to 0.01.

        Returns:
            [type]: [description]
        """
        stops_df = self.dataframes.get('stops')
        stop_dicts = stops_df[[
            'stop_id', 'stop_name', 'similar_stops_centroid']].to_dict(orient='records')
        return [{
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': stop['similar_stops_centroid']
            },
            'properties': {
                'stop_name': stop['stop_name'],
                'stop_id': stop['stop_id'],
            }
        } for stop in stop_dicts]

    def read_route_frequency(self, yyyymmdd=''):
        """
        By grouped stops, aggregate route frequency.
        Filtering trips by a date, you can aggregate frequency only route serviced on the date.

        Args:
            yyyymmdd (str, optional): date, like 20210401. Defaults to ''.
            delimiter (str, optional): stop_id delimiter, sample_A, sample_B, then delimiter is '_'. Defaults to ''.
            max_distance_degree (float, optional): distance limit in grouping by stop_name. Defaults to 0.01.

        Returns:
            [type]: [description]
        """
        stop_times_df = self.dataframes.get(
            'stop_times')[['stop_id', 'trip_id', 'stop_sequence']].sort_values(
            ['trip_id', 'stop_sequence']).copy()

        # filter stop_times by whether serviced or not
        if yyyymmdd:
            trips_filtered_by_day = self.get_trips_on_a_date(yyyymmdd)
            stop_times_df = pd.merge(
                stop_times_df, trips_filtered_by_day, on='trip_id', how='left')
            stop_times_df = stop_times_df[stop_times_df['service_flag'] == 1]

        # join agency info)
        stop_times_df = pd.merge(stop_times_df, self.dataframes['trips'][[
                                 'trip_id', 'route_id']], on='trip_id', how='left')
        stop_times_df = pd.merge(stop_times_df, self.dataframes['routes'][[
                                 'route_id', 'agency_id']], on='route_id', how='left')
        stop_times_df = pd.merge(stop_times_df, self.dataframes['agency'][[
                                 'agency_id', 'agency_name']], on='agency_id', how='left')

        # get prev and next stops_id, stop_name, trip_id
        stop_times_df = pd.merge(stop_times_df, self.dataframes['stops'][[
                                 'stop_id', 'stop_name', 'similar_stops_centroid']], on='stop_id', how='left')
        stop_times_df['prev_stop_id'] = stop_times_df['stop_id']
        stop_times_df['prev_trip_id'] = stop_times_df['trip_id']
        stop_times_df['prev_stop_name'] = stop_times_df['stop_name']
        stop_times_df['prev_similar_stops_centroid'] = stop_times_df['similar_stops_centroid']
        stop_times_df['next_stop_id'] = stop_times_df['stop_id'].shift(-1)
        stop_times_df['next_trip_id'] = stop_times_df['trip_id'].shift(-1)
        stop_times_df['next_stop_name'] = stop_times_df['stop_name'].shift(-1)
        stop_times_df['next_similar_stops_centroid'] = stop_times_df['similar_stops_centroid'].shift(
            -1)

        # drop last stops (-> stops has no next stop)
        stop_times_df = stop_times_df.drop(
            index=stop_times_df.query('prev_trip_id != next_trip_id').index)

        # define path_id by prev-stops-centroid and next-stops-centroid
        def latlon_to_str(latlon): return ''.join(
            list(map(lambda coord: str(round(coord, 4)), latlon)))
        stop_times_df['path_id'] = stop_times_df['prev_similar_stops_centroid'].map(
            latlon_to_str) + stop_times_df['next_similar_stops_centroid'].map(latlon_to_str)

        # aggregate path-frequency
        path_frequency = stop_times_df[['stop_id', 'path_id']].groupby(
            'path_id').count().reset_index()
        path_frequency.columns = ['path_id', 'path_count']
        path_data = pd.merge(path_frequency, stop_times_df.drop_duplicates(
            subset='path_id'), on='path_id')
        path_data_dict = path_data.to_dict(orient='records')

        return [{
            'type': 'Feature',
            'geometry': {
                'type': 'LineString',
                'coordinates': (path['prev_similar_stops_centroid'],
                                path['next_similar_stops_centroid'])
            },
            'properties': {
                'frequency': path['path_count'],
                'prev_stop_id': path['prev_stop_id'],
                'prev_stop_name': path['prev_stop_name'],
                'next_stop_id': path['next_stop_id'],
                'next_stop_name': path['next_stop_name'],
                'agency_id':path['agency_id'],
                'agency_name': path['agency_name']
            }
        } for path in path_data_dict]

    @ lru_cache(maxsize=None)
    def get_similar_stops_centroid(self, stop_id: str, delimiter='', max_distance_degree=0.01):
        """
        With one stop_id, group stops by parent, stop_id, or stop_name and each distance, and calc centroid of them.
        - parent: this is simple, if stop has parent_station, the 'centroid' is parent_station lat-lon
        - stop_id: by delimiter seperate stop_id into prefix and suffix, and group stops having same stop_id-prefix
        - name and distance: group stops by stop_name, excluding stops are far than max_distance_degree

        Args:
            stop_id (str): target stop_id
            max_distance_degree (float, optional): distance limit on grouping, Defaults to 0.01.
        Returns:
            [float, float]: centroid of grouped stops
        """
        stops_df = self.dataframes['stops']
        stop = stops_df[stops_df['stop_id'] == stop_id].iloc[0]

        if str(stop['parent_station']) != 'nan':
            return stops_df[stops_df['stop_id'] == stop['parent_station']][['stop_lon', 'stop_lat']].iloc[0].values.tolist()

        if delimiter:
            stops_df_id_delimited = self.get_stops_id_delimited(delimiter)
            stop_id_prefix = stop_id.rsplit(delimiter, 1)[0]
            if stop_id_prefix != stop_id:
                seperated_only_stops = stops_df_id_delimited[stops_df_id_delimited['delimited']]
                similar_stops = seperated_only_stops[seperated_only_stops['stop_id_prefix'] == stop_id_prefix][[
                    'similar_stops_centroid_lon', 'similar_stops_centroid_lat']]
                return similar_stops.values.tolist()[0]
            else:
                # when cannot seperate stop_id, grouping by name and distance
                stops_df = stops_df_id_delimited[~stops_df_id_delimited['delimited']]

        # grouping by name and distance
        similar_stops = stops_df[stops_df['stop_name'] == stop['stop_name']][[
            'stop_lon', 'stop_lat']]
        similar_stops = similar_stops.query(
            f'(stop_lon - {stop["stop_lon"]}) ** 2 + (stop_lat - {stop["stop_lat"]}) ** 2  < {max_distance_degree ** 2}')
        return similar_stops.mean().values.tolist()

    def get_similar_stops_by_name_and_distance(self, stop_name, distance):
        similar_stops = self.stops_df[self.stops_df['stop_name'] == stop['stop_name']][[
            'stop_lon', 'stop_lat']].copy()
        similar_stops = similar_stops.query(
            f'(stop_lon - {stop["stop_lon"]}) ** 2 + (stop_lat - {stop["stop_lat"]}) ** 2  < {max_distance_degree ** 2}')
        return similar_stops

    @ lru_cache(maxsize=None)
    def get_stops_id_delimited(self, delimiter):
        stops_df = self.dataframes.get(
            'stops')[['stop_id', 'stop_name', 'stop_lon', 'stop_lat', 'parent_station']].copy()
        stops_df['stop_id_prefix'] = stops_df['stop_id'].map(
            lambda stop_id: stop_id.rsplit(delimiter, 1)[0])
        stops_df['delimited'] = stops_df['stop_id'] != stops_df['stop_id_prefix']
        grouped_by_prefix = stops_df[[
            'stop_id_prefix', 'stop_lon', 'stop_lat']].groupby('stop_id_prefix').mean().reset_index()
        grouped_by_prefix.columns = [
            'stop_id_prefix', 'similar_stops_centroid_lon', 'similar_stops_centroid_lat']
        stops_df_with_centroid = pd.merge(
            stops_df, grouped_by_prefix, on='stop_id_prefix', how='left')
        return stops_df_with_centroid

    @ classmethod
    def get_route_name_from_tupple(cls, route):
        if not pd.isna(route.route_short_name):
            return route.route_short_name
        elif not pd.isna(route.route_long_name):
            return route.route_long_name
        else:
            ValueError(
                f'{route} have neither "route_long_name" or "route_short_time".')

    def routes_count(self, no_shapes=False):
        if self.dataframes.get('shapes') is None or no_shapes:
            route_ids = self.dataframes.get('trips')['route_id'].unique()
            return len(route_ids)
        else:
            shape_ids = self.dataframes.get('shapes')['shape_id'].unique()
            return len(shape_ids)

    @ lru_cache(maxsize=None)
    def get_shape_ids_on_routes(self):
        trips_with_shape_df = self.dataframes['trips'][[
            'route_id', 'shape_id']].dropna(subset=['shape_id'])
        group = trips_with_shape_df.groupby('route_id')['shape_id'].unique()
        group.apply(lambda x: x.sort())
        return group

    @ lru_cache(maxsize=None)
    def get_shapes_coordinates(self):
        shapes_df = self.dataframes['shapes'].copy()
        shapes_df.sort_values('shape_pt_sequence')
        shapes_df['pt'] = shapes_df[[
            'shape_pt_lon', 'shape_pt_lat']].values.tolist()
        return shapes_df.groupby('shape_id')['pt'].apply(list)

    def get_trips_on_a_date(self, yyyymmdd: str):
        """
        get trips are on service on a date.

        Args:
            yyyymmdd (str): [description]

        Returns:
            [type]: [description]
        """
        # sunday, monday, tuesday...
        day_of_week = datetime.date(int(yyyymmdd[0:4]), int(
            yyyymmdd[4:6]), int(yyyymmdd[6:8])).strftime('%A').lower()

        # filter services by day
        calendar_df = self.dataframes['calendar'].copy()
        calendar_df = calendar_df.astype({'start_date': int, 'end_date': int})
        calendar_df = calendar_df[calendar_df[day_of_week] == '1']
        calendar_df = calendar_df.query(
            f'start_date <= {int(yyyymmdd)} and {int(yyyymmdd)} <= end_date', engine='python')

        services_on_a_day = calendar_df[['service_id']]

        calendar_dates_df = self.dataframes.get('calendar_dates')
        if calendar_dates_df is not None:
            filtered = calendar_dates_df[calendar_dates_df['date'] == yyyymmdd][[
                'service_id', 'exception_type']]
            to_be_removed_services = filtered[filtered['exception_type'] == '2']
            to_be_appended_services = filtered[filtered['exception_type'] == '1'][[
                'service_id']]

            services_on_a_day = pd.merge(
                services_on_a_day, to_be_removed_services, on='service_id', how='left')
            services_on_a_day = services_on_a_day[services_on_a_day['exception_type'] != '2']
            services_on_a_day = pd.concat(
                [services_on_a_day, to_be_appended_services])

        services_on_a_day['service_flag'] = 1

        # filter trips
        trips_df = self.dataframes['trips'].copy()
        trip_service = pd.merge(trips_df, services_on_a_day, on='service_id')
        trip_service = trip_service[trip_service['service_flag'] == 1]

        return trip_service[['trip_id', 'service_flag']]

    def read_routes(self, no_shapes=False) -> list:
        """
        read routes by shapes or stop_times
        First, this method try to load shapes and parse it into routes,
        but shapes is optional table in GTFS. Then is shapes does not exist or no_shapes is True,
        this parse routes by stop_time, stops, trips, and routes.

        Args:
            no_shapes (bool, optional): ignore shapes table. Defaults to False.

        Returns:
            [list]: list of GeoJSON-Feature-dict
        """
        if self.dataframes.get('shapes') is None or no_shapes:
            # no-shape routes

            # trip-route-merge:A
            trips_df = self.dataframes['trips'][['trip_id', 'route_id']]
            routes_df = self.dataframes['routes'][[
                'route_id', 'route_long_name', 'route_short_name']]
            trips_routes = pd.merge(trips_df, routes_df, on='route_id')

            # stop_times-stops-merge:B
            stop_times_df = self.dataframes['stop_times'][[
                'stop_id', 'trip_id', 'stop_sequence']]
            stops_df = self.dataframes.get(
                'stops')[['stop_id', 'stop_lon', 'stop_lat']]
            merged = pd.merge(
                stop_times_df, stops_df[['stop_id', 'stop_lon', 'stop_lat']], on='stop_id')

            # A-B-merge
            merged = pd.merge(merged, trips_routes, on='trip_id')
            merged['route_concat_name'] = merged['route_long_name'].fillna('') + \
                merged['route_short_name'].fillna('')

            # parse routes
            route_ids = merged['route_id'].unique()
            features = []
            for route_id in route_ids:
                route = merged[merged['route_id'] == route_id]
                trip_id = route['trip_id'].unique()[0]
                route = route[route['trip_id'] ==
                              trip_id].sort_values('stop_sequence')
                features.append({
                    'type': 'Feature',
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': route[['stop_lon', 'stop_lat']].values.tolist()
                    },
                    'properties': {
                        'route_id': str(route_id),
                        'route_name': route.route_concat_name.values.tolist()[0],
                    }
                })
            return features
        else:
            shape_coords = self.get_shapes_coordinates()
            shape_ids_on_routes = self.get_shape_ids_on_routes()
            features = []
            for route in self.dataframes.get('routes').itertuples():
                if shape_ids_on_routes.get(route.route_id) is None:
                    continue
                coordinates = [shape_coords.at[shape_id]
                               for shape_id in shape_ids_on_routes[route.route_id]]
                route_name = self.get_route_name_from_tupple(route)
                features.append({
                    'type': 'Feature',
                    'geometry': {
                        'type': 'MultiLineString',
                        'coordinates': coordinates
                    },
                    'properties': {
                        'route_id': str(route.route_id),
                        'route_name': route_name,
                    }
                })

            # list-up already loaded shape_ids, dropping dupulicates
            loaded_shape_ids = list(set(sum([list(val)
                                             for val in shape_ids_on_routes], [])))

            # load shape_ids unloaded yet
            for shape_id in shape_coords.index:
                if shape_id in loaded_shape_ids:
                    continue
                features.append({
                    'type': 'Feature',
                    'geometry': {
                        'type': 'MultiLineString',
                        'coordinates': [shape_coords.at[shape_id]]
                    },
                    'properties': {
                        'route_id': None,
                        'route_name': str(shape_id),
                    }
                })
            return features


if __name__ == "__main__":
    import argparse
    import shutil
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip')
    parser.add_argument('--src_dir')
    parser.add_argument('--output_dir')
    parser.add_argument('--no_shapes', action='store_true')
    parser.add_argument('--ignore_no_route', action='store_true')
    parser.add_argument('--frequency', action='store_true')
    parser.add_argument('--yyyymmdd')
    parser.add_argument('--delimiter')
    args = parser.parse_args()

    if args.zip is None and args.src_dir is None:
        raise RuntimeError('gtfs-jp-parser needs zipfile or src_dir.')

    if args.yyyymmdd:
        if len(args.yyyymmdd) != 8:
            raise RuntimeError(
                f'yyyymmdd must be 8 characters string, for example 20210401, your is {args.yyyymmdd} ({len(args.yyyymmdd)} characters)')

    if args.zip:
        print('extracting zipfile...')
        temp_dir = os.path.join(tempfile.gettempdir(), 'gtfs-jp-parser')
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.mkdir(temp_dir)
        with zipfile.ZipFile(args.zip) as z:
            z.extractall(temp_dir)
        output_dir = temp_dir
    else:
        output_dir = args.src_dir
    gtfs_parser = GTFSParser(
        output_dir, as_frequency=args.frequency, delimiter=args.delimiter)

    print('GTFS loaded.')

    if args.output_dir:
        output_dir = args.output_dir

    if args.frequency:
        stops_features = gtfs_parser.read_interpolated_stops()
        stops_geojson = {
            'type': 'FeatureCollection',
            'features': stops_features
        }
        routes_features = gtfs_parser.read_route_frequency(
            yyyymmdd=args.yyyymmdd)
        routes_geojson = {
            'type': 'FeatureCollection',
            'features': routes_features
        }
    else:
        routes_features = gtfs_parser.read_routes(no_shapes=args.no_shapes)
        routes_geojson = {
            'type': 'FeatureCollection',
            'features': routes_features
        }
        stops_features = gtfs_parser.read_stops(
            ignore_no_route=args.ignore_no_route)
        stops_geojson = {
            'type': 'FeatureCollection',
            'features': stops_features
        }

    print('writing geojsons...')
    with open(os.path.join(output_dir, 'routes.geojson'), mode='w', encoding='utf-8') as f:
        json.dump(routes_geojson, f, ensure_ascii=False)
    with open(os.path.join(output_dir, 'stops.geojson'), mode='w', encoding='utf-8') as f:
        json.dump(stops_geojson, f, ensure_ascii=False)
