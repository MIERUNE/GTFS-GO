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
    def __init__(self, src_dir: str):
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

    def read_stops(self, ignore_no_route=False):
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

    def read_interpolated_stops(self, delimiter='', max_distance_degree=0.01):
        stops_df = self.dataframes.get('stops')
        stops_df['similar_stops_centroid'] = stops_df['stop_id'].map(
            lambda stop_id: self.get_similar_stops_centroid(stop_id, delimiter, max_distance_degree))
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

    def read_route_frequency(self, yyyymmdd='', delimiter='', max_distance_degree=0.01):
        stop_times_df = self.dataframes.get(
            'stop_times')[['stop_id', 'trip_id', 'stop_sequence']].sort_values(
            ['trip_id', 'stop_sequence']).copy()

        # filter stop_times by whether serviced or not
        if yyyymmdd:
            trips_filtered_by_day = self.get_trips_on_a_day(yyyymmdd)
            stop_times_df = pd.merge(
                stop_times_df, trips_filtered_by_day, on='trip_id', how='left')
            stop_times_df = stop_times_df[stop_times_df['service_flag'] == 1]

        stop_times_df['prev_stop_id'] = stop_times_df['stop_id']
        stop_times_df['prev_trip_id'] = stop_times_df['trip_id']
        stop_times_df['next_stop_id'] = stop_times_df['stop_id'].shift(-1)
        stop_times_df['next_trip_id'] = stop_times_df['trip_id'].shift(-1)

        # drop last stops (-> stops has no next stop)
        stop_times_df = stop_times_df.drop(
            index=stop_times_df.query('prev_trip_id != next_trip_id').index)

        # calculate similar stops centroid
        stop_times_df['prev_similar_stops_centroid'] = stop_times_df['prev_stop_id'].map(
            lambda stop_id: self.get_similar_stops_centroid(stop_id,
                                                            delimiter,
                                                            max_distance_degree))
        stop_times_df['next_similar_stops_centroid'] = stop_times_df['next_stop_id'].map(
            lambda stop_id: self.get_similar_stops_centroid(stop_id,
                                                            delimiter,
                                                            max_distance_degree))

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
                'frequency': path['path_count']
            }
        } for path in path_data_dict]

    @ lru_cache(maxsize=None)
    def get_similar_stops_centroid(self, stop_id: str, delimiter='', max_distance_degree=0.01):
        """
        基準となる停留所の名称・位置から、名寄せすべき停留所の平均座標を算出
        Args:
            stop_id (str): 基準となる停留所のstop_id
            max_distance_degree (float, optional): 近傍判定における許容範囲、経緯度での距離 Defaults to 0.01.
        Returns:
            [float, float]: 名寄せされた停留所の平均座標
        """
        stops_df = self.dataframes['stops']
        stop = stops_df[stops_df['stop_id'] == stop_id].iloc[0]

        if str(stop['parent_station']) == 'nan':
            if delimiter:
                stops_df_id_delimited = self.get_stops_id_delimited(delimiter)
                stop_id_prefix = stop_id.rsplit(delimiter, 1)[0]
                similar_stops = stops_df_id_delimited[stops_df_id_delimited['stop_id_prefix']
                                                      == stop_id_prefix][['stop_lon', 'stop_lat']]
            else:
                similar_stops = self.get_similar_stops_by(
                    stop['stop_name'])[['stop_lon', 'stop_lat']].copy()
                similar_stops = similar_stops.query(
                    f'(stop_lon - {stop["stop_lon"]}) ** 2 + (stop_lat - {stop["stop_lat"]}) ** 2  < {max_distance_degree ** 2}')
            return similar_stops.mean().values.tolist()
        else:
            return stops_df[stops_df['stop_id'] == stop['parent_station']][['stop_lon', 'stop_lat']].iloc[0].values.tolist()

    @ lru_cache(maxsize=None)
    def get_stops_id_delimited(self, delimiter):
        stops_df = self.dataframes.get(
            'stops')[['stop_id', 'stop_lon', 'stop_lat']].copy()
        stops_df['stop_id_prefix'] = stops_df['stop_id'].map(
            lambda stop_id: stop_id.rsplit(delimiter, 1)[0])
        return stops_df

    @ lru_cache(maxsize=None)
    def get_similar_stops_by(self, stop_name):
        """
        名称が一致する近傍停留所を抽出する
        Args:
            stop_name ([type]): 停留所名
        Returns:
            [type]: 類似するstops_df
        """
        stops_df = self.dataframes['stops']
        similar_name_stops = stops_df[stops_df['stop_name'] == stop_name]
        return similar_name_stops

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

    def get_trips_on_a_day(self, yyyymmdd: str):
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

    def read_routes(self, no_shapes=False):
        if self.dataframes.get('shapes') is None or no_shapes:
            # no-shape routes
            trips_df = self.dataframes['trips'][['trip_id', 'route_id']]
            routes_df = self.dataframes['routes'][[
                'route_id', 'route_long_name', 'route_short_name']]

            trips_routes = pd.merge(trips_df, routes_df, on='route_id')

            stop_times_df = self.dataframes['stop_times'][[
                'stop_id', 'trip_id', 'stop_sequence']]
            stops_df = self.dataframes.get(
                'stops')[['stop_id', 'stop_lon', 'stop_lat']]

            merged = pd.merge(
                stop_times_df, stops_df[['stop_id', 'stop_lon', 'stop_lat']], on='stop_id')
            merged = pd.merge(merged, trips_routes, on='trip_id')
            merged['route_concat_name'] = merged['route_long_name'].fillna('') + \
                merged['route_short_name'].fillna('')

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
        gtfs_parser = GTFSParser(temp_dir)
        output_dir = temp_dir
    else:
        gtfs_parser = GTFSParser(args.src_dir)
        output_dir = args.src_dir

    print('GTFS loaded.')

    if args.output_dir:
        output_dir = args.output_dir

    if args.frequency:
        stops_features = gtfs_parser.read_interpolated_stops(
            delimiter=args.delimiter)
        stops_geojson = {
            'type': 'FeatureCollection',
            'features': stops_features
        }
        routes_features = gtfs_parser.read_route_frequency(
            yyyymmdd=args.yyyymmdd, delimiter=args.delimiter)
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
