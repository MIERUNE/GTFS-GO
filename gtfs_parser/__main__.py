import json
import os
import glob
import zipfile
import tempfile
from functools import lru_cache

import pandas as pd

try:
    # QGIS-import
    from .constants import GTFS_JP_DATATYPES
except:
    from constants import GTFS_JP_DATATYPES


class GTFSParser:
    def __init__(self, src_dir: str):
        txts = glob.glob(os.path.join(
            src_dir, '**', '*.txt'), recursive=True)
        self.dataframes = {}
        for txt in txts:
            datatype = os.path.basename(txt).split('.')[0]
            if os.path.basename(datatype) not in GTFS_JP_DATATYPES:
                print(f'{datatype} is not specified in GTFS-JP, skipping...')
                continue
            with open(txt, encoding='utf-8_sig') as t:
                df = pd.read_csv(t)
                if len(df) == 0:
                    print(f'{datatype}.txt is empty, skipping...')
                    continue
                self.dataframes[os.path.basename(txt).split('.')[0]] = df
        for datatype in GTFS_JP_DATATYPES:
            if GTFS_JP_DATATYPES[datatype]['required'] and \
                    datatype not in self.dataframes:
                raise FileNotFoundError(f'{datatype} is not exists.')

    def stops_count(self):
        stops_df = self.dataframes['stops']
        return len(stops_df)

    def read_stops(self, ignore_no_route=False):
        stops_df = self.dataframes['stops'][[
            'stop_id', 'stop_lat', 'stop_lon', 'stop_name']]
        route_id_on_stops = self.get_route_ids_on_stops()

        for stop in stops_df.itertuples():
            if stop.stop_id in route_id_on_stops:
                route_ids = route_id_on_stops.at[stop.stop_id].tolist()
            else:
                if ignore_no_route:
                    continue
                route_ids = []

            yield {
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
            }

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
        stops_df = self.dataframes.get('stops')
        stops_df['similar_stops_centroid'] = stops_df['stop_id'].apply(
            self.get_similar_stops_centroid)
        stop_dicts = stops_df[[
            'stop_id', 'stop_name', 'similar_stops_centroid']].to_dict(orient='records')
        for stop_dict in stop_dicts:
            # extract keys from Dataframe
            yield {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': stop_dict['similar_stops_centroid']
                },
                'properties': {
                    'stop_name': stop_dict['stop_name'],
                    'stop_id': stop_dict['stop_id'],
                }
            }

    def read_route_frequency(self, all_trips=False):
        stop_times_df = self.dataframes.get(
            'stop_times')[['stop_id', 'trip_id', 'stop_sequence']].copy()

        stops_df = self.dataframes.get('stops')[['stop_id']].copy()
        stops_df['similar_stops_centroid'] = stops_df['stop_id'].apply(
            self.get_similar_stops_centroid)

        merged_df = pd.merge(stop_times_df, stops_df, on='stop_id')

        path_data = {}
        merged_dicts = merged_df.sort_values(
            ['trip_id', 'stop_sequence']).to_dict(orient='records')
        for i in range(len(merged_dicts) - 1):
            prev_trip_id = merged_dicts[i]['trip_id']
            next_trip_id = merged_dicts[i + 1]['trip_id']
            if prev_trip_id != next_trip_id:
                continue
            prev_stop_latlon = merged_dicts[i]['similar_stops_centroid']
            next_stop_latlon = merged_dicts[i + 1]['similar_stops_centroid']
            path_id = ''.join(
                map(str, prev_stop_latlon)) + ''.join(map(str, next_stop_latlon))

            if path_data.get(path_id) is None:
                path_data[path_id] = {
                    'frequency': 1,
                    'prev_stop_latlon': prev_stop_latlon,
                    'next_stop_latlon': next_stop_latlon
                }
            else:
                path_data[path_id]['frequency'] += 1

        for path_id in path_data:
            yield {
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': (path_data[path_id]['prev_stop_latlon'],
                                    path_data[path_id]['next_stop_latlon'])
                },
                'properties': {
                    'frequency': path_data[path_id]['frequency']
                }
            }

    @ lru_cache(maxsize=None)
    def get_similar_stops_centroid(self, stop_id: str, max_distance_degree=0.01, delimiter='-'):
        """
        基準となる停留所の名称・位置から、名寄せすべき停留所の平均座標を算出
        Args:
            stop_id (str): 基準となる停留所のstop_id
            max_distance_degree (float, optional): 近傍判定のおける許容範囲、経緯度での距離 Defaults to 0.01.
        Returns:
            [float, float]: 名寄せされた停留所の平均座標
        """
        stops_df = self.dataframes['stops']
        if 'parent_station' not in stops_df.columns:
            # parent_stationカラムがない場合はあとで比較するために'nan'で埋めておく
            stops_df['parent_station'] = 'nan'

        stop = stops_df[stops_df['stop_id'] == stop_id].iloc[0]

        if str(stop['parent_station']) == 'nan':
            if delimiter:
                stops_df_id_delimited = self.get_stops_id_delimited(delimiter)
                stop_id_prefix = stop_id.rsplit(delimiter, 1)[0]
                similar_stops = stops_df_id_delimited[stops_df_id_delimited['stop_id_prefix']
                                                      == stop_id_prefix]
            else:
                similar_stops = self.get_similar_stops_by(stop['stop_name'])
                similar_stops = similar_stops.query(
                    f'(stop_lon - {stop["stop_lon"]}) ** 2 + (stop_lat - {stop["stop_lat"]}) ** 2  < {max_distance_degree ** 2}')
            return similar_stops[['stop_lon', 'stop_lat']].mean().values.tolist()
        else:
            return stops_df[stops_df['stop_id'] == stop['parent_station']].iloc[0][['stop_lon', 'stop_lat']].values.tolist()

    @ lru_cache(maxsize=None)
    def get_stops_id_delimited(self, delimiter):
        stops_df = self.dataframes.get('stops')
        stops_df['stop_id_prefix'] = stops_df['stop_id'].map(
            lambda stop_id: stop_id.rsplit(delimiter, 1)[0])
        return stops_df

    @ lru_cache(maxsize=None)
    def get_similar_stops_by(self, stop_name):
        """
        名称が類似する停留所を抽出する
        Args:
            stop_name ([type]): 停留所名
        Returns:
            [type]: 類似するstops_df
        """
        stops_df = self.dataframes['stops']
        similar_name_stops = stops_df[stops_df['stop_name'] == stop_name]
        return similar_name_stops

    def get_route_name_from(self, route_data):
        if not str(route_data['route_long_name']) == 'nan':
            return str(route_data['route_long_name'])
        elif not str(route_data['route_short_name']) == 'nan':
            return str(route_data['route_short_name'])
        else:
            ValueError(
                f'{route_data} have neither "route_long_name" or "route_short_time".')

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

    def read_routes(self, no_shapes=False):
        if self.dataframes.get('shapes') is None or no_shapes:
            # no-shape routes
            routes_df = self.dataframes.get('routes')
            trips_df = self.dataframes['trips']
            route_ids = trips_df['route_id'].unique()
            for route_id in route_ids:
                trip_id = trips_df[trips_df['route_id'] == route_id]['trip_id'].unique()[
                    0]
                stop_times_df = self.dataframes.get('stop_times')
                filtered = stop_times_df[stop_times_df['trip_id'] == trip_id]
                stops_df = self.dataframes.get('stops')
                merged = pd.merge(filtered, stops_df, on='stop_id')[
                    ['stop_lon', 'stop_lat']]
                route_data = routes_df[routes_df['route_id']
                                       == route_id].iloc[0]
                route_name = self.get_route_name_from(route_data)
                yield {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': merged.values.tolist()
                    },
                    'properties': {
                        'route_id': str(route_id),
                        'route_name': route_name,
                    }
                }
        else:
            for route in self.dataframes.get('routes').itertuples():
                shape_coords = self.get_shapes_coordinates()
                shape_ids_on_routes = self.get_shape_ids_on_routes()
                coordinates = [shape_coords.at[shape_id]
                               for shape_id in shape_ids_on_routes[route.route_id]]

                route_name = self.get_route_name_from_tupple(route)
                yield {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'MultiLineString',
                        'coordinates': coordinates
                    },
                    'properties': {
                        'route_id': str(route.route_id),
                        'route_name': route_name,
                    }
                }

    @ lru_cache(maxsize=None)
    def get_destination_stop_of(self, trip_id):
        stop_times_df = self.dataframes['stop_times']
        filtered = stop_times_df[stop_times_df['trip_id'] == trip_id]
        max_stop_sequence_idx = filtered['stop_sequence'].idxmax()
        stops_df = self.dataframes['stops']
        destination_stop = stops_df[stops_df['stop_id'] ==
                                    stop_times_df['stop_id'].iloc[max_stop_sequence_idx]]
        return destination_stop

    @ lru_cache(maxsize=None)
    def get_trips_filtered_by(self, route_id: str):
        trips_df = self.dataframes.get('trips')
        filtered = trips_df[trips_df['route_id'] == route_id]
        if len(filtered['route_id'].unique()) > 1:
            print(f'number of trips filterd by "{route_id}" is larger than 1')
        trips = filtered.iloc[:, 1:-1].to_dict(orient='records')
        return trips


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
    args = parser.parse_args()

    if args.zip is None and args.src_dir is None:
        raise RuntimeError('gtfs-jp-parser needs zipfile or src_dir.')

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
        stops_features = [
            route for route in gtfs_parser.read_interpolated_stops()]
        stops_geojson = {
            'type': 'FeatureCollection',
            'features': stops_features
        }
        print('stop finished')
        routes_features = [
            route for route in gtfs_parser.read_route_frequency()]
        routes_geojson = {
            'type': 'FeatureCollection',
            'features': routes_features
        }
        print('routes finished')
    else:
        routes_features = [route for route in gtfs_parser.read_routes(
            no_shapes=args.no_shapes)]
        routes_geojson = {
            'type': 'FeatureCollection',
            'features': routes_features
        }
        stops_features = [stop for stop in gtfs_parser.read_stops(
            ignore_no_route=args.ignore_no_route)]
        stops_geojson = {
            'type': 'FeatureCollection',
            'features': stops_features
        }

    print('writing geojsons...')
    with open(os.path.join(output_dir, 'routes.geojson'), mode='w', encoding='utf-8') as f:
        json.dump(routes_geojson, f, ensure_ascii=False)
    with open(os.path.join(output_dir, 'stops.geojson'), mode='w', encoding='utf-8') as f:
        json.dump(stops_geojson, f, ensure_ascii=False)
