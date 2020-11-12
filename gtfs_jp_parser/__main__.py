import json
import os
import glob
import zipfile
import tempfile
import math
from functools import lru_cache

import pandas as pd

from .constants import GTFS_JP_DATATYPES


class GTFS_JP:
    def __init__(self, src_dir: str):
        txts = glob.glob(os.path.join(
            src_dir, '**', '*.txt'), recursive=True)
        self.dataframes = {}
        for txt in txts:
            datatype = os.path.basename(txt).split('.')[0]
            if os.path.basename(datatype) not in GTFS_JP_DATATYPES:
                print(f'{datatype} is not specified in GTFS-JP, skipping...')
                continue
            with open(txt) as t:
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

    def read_stops(self, empty_stops=False, no_diagrams=False):
        stops_df = self.dataframes['stops']
        stop_times_df = self.dataframes['stop_times']
        trips_df = self.dataframes['trips']
        routes_df = self.dataframes['routes']

        for stop in stops_df.itertuples():
            filtered = stop_times_df[stop_times_df['stop_id']
                                     == stop.stop_id]
            merged = pd.merge(pd.merge(filtered, trips_df,
                                       on='trip_id'), routes_df, on='route_id')

            diagrams = None
            if not no_diagrams:
                diagrams = {}
                for row in merged.itertuples():
                    # get route name from long or short
                    route_data = routes_df[routes_df['route_id']
                                           == row.route_id].iloc[0]
                    route_name = self.get_route_name_from(route_data)

                    departure_time = str(row.departure_time)
                    service_id = str(row.service_id)
                    destination = str(self.get_destination_stop_of(
                        row.trip_id)['stop_name'].values[0])

                    # update diagrams data
                    if diagrams.get(route_name, {}).get(service_id):
                        diagrams[route_name][service_id].append(departure_time)
                    elif diagrams.get(route_name):
                        diagrams[route_name].update({
                            service_id: [departure_time],
                            'destination': destination
                        })
                    else:
                        diagrams[route_name] = {
                            service_id: [departure_time],
                            'destination': destination
                        }

            if diagrams == {} and not empty_stops:
                print(f'stop_id={stop.stop_id} has no route, skipping...')
                continue

            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [stop.stop_lon, stop.stop_lat]
                },
                'properties': {
                    'stop_id': str(stop.stop_id),
                    'stop_name': stop.stop_name,
                    'diagrams': diagrams,
                    'route_ids': self.get_route_ids_by(stop.stop_id)
                }
            }
            yield feature

    def interpolated_stops_count(self):
        stops_df = self.dataframes['stops']
        stop_names = stops_df['stop_name'].unique()
        return len(stop_names)

    def read_interpolated_stops(self):
        stops_df = self.dataframes['stops']
        stop_names = stops_df['stop_name'].unique()
        for stop_name in stop_names:
            same_named_stops = stops_df[stops_df['stop_name'] == stop_name]
            same_named_stops_ids = same_named_stops['stop_id'].unique()

            route_ids = []
            for stop_id in same_named_stops_ids:
                route_ids.extend(self.get_route_ids_by(stop_id))
            route_ids = list(set(route_ids))

            lonlats = same_named_stops[['stop_lon', 'stop_lat']]
            centroid = lonlats.mean()

            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': centroid.values.tolist()
                },
                'properties': {
                    'stop_name': stop_name,
                    'stop_ids': same_named_stops_ids.tolist(),
                    'route_ids': route_ids
                }
            }
            yield feature

    @lru_cache(maxsize=None)
    def get_route_ids_by(self, stop_id):
        stops_df = self.dataframes['stops']
        stop = stops_df[stops_df['stop_id'] == stop_id]
        stop_times_df = self.dataframes['stop_times']
        trips_df = self.dataframes['trips']
        merged = pd.merge(pd.merge(stop, stop_times_df,
                                   on='stop_id'), trips_df, on='trip_id')
        return merged['route_id'].unique().astype(str).tolist()

    def get_route_name_from(self, route_data):
        if not str(route_data['route_long_name']) == 'nan':
            return str(route_data['route_long_name'])
        elif not str(route_data['route_short_name']) == 'nan':
            return str(route_data['route_short_name'])
        else:
            ValueError(
                f'{route_data} have neither "route_long_name" or "route_short_time".')

    def routes_count(self, no_shapes=False):
        shapes_df = self.dataframes.get('shapes')
        if shapes_df is not None and not no_shapes:
            shape_ids = shapes_df['shape_id'].unique()
            return len(shape_ids)
        else:
            trips_df = self.dataframes['trips']
            route_ids = trips_df['route_id'].unique()
            return len(route_ids)

    def read_routes(self, no_shapes=False):
        shapes_df = self.dataframes.get('shapes')
        routes_df = self.dataframes.get('routes')
        trips_df = self.dataframes['trips']
        if shapes_df is not None and not no_shapes:
            shape_ids = shapes_df['shape_id'].unique()
            for shape_id in shape_ids:
                filtered = shapes_df[shapes_df['shape_id'] ==
                                     shape_id][['shape_pt_lon', 'shape_pt_lat']]
                route_ids = trips_df[trips_df['shape_id']
                                     == shape_id]['route_id'].unique()
                for route_id in route_ids:
                    route_data = routes_df[routes_df['route_id']
                                           == route_id].iloc[0]
                    route_name = self.get_route_name_from(route_data)
                    trip_id = trips_df[trips_df['route_id']
                                       == route_id]['trip_id'].values[0]
                    destination = str(self.get_destination_stop_of(
                        trip_id)['stop_name'].values[0])
                    feature = {
                        'type': 'Feature',
                        'geometry': {
                            'type': 'LineString',
                            'coordinates': filtered.values.tolist()
                        },
                        'properties': {
                            'route_id': str(route_id),
                            'route_name': route_name,
                            'destination': destination
                        }
                    }
                    yield feature
        else:
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
                trip_id = trips_df[trips_df['route_id']
                                   == route_id]['trip_id'].values[0]
                destination = str(self.get_destination_stop_of(
                    trip_id)['stop_name'].values[0])
                feature = {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': merged.values.tolist()
                    },
                    'properties': {
                        'route_id': str(route_id),
                        'route_name': route_name,
                        'destination': destination
                    }
                }
                yield feature

    @lru_cache(maxsize=None)
    def get_destination_stop_of(self, trip_id):
        stop_times_df = self.dataframes['stop_times']
        filtered = stop_times_df[stop_times_df['trip_id'] == trip_id]
        max_stop_sequence_idx = filtered['stop_sequence'].idxmax()
        stops_df = self.dataframes['stops']
        destination_stop = stops_df[stops_df['stop_id'] ==
                                    stop_times_df['stop_id'].iloc[max_stop_sequence_idx]]
        return destination_stop

    @lru_cache(maxsize=None)
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
    parser.add_argument('--empty_stops', action='store_true')
    parser.add_argument('--no_diagrams', action='store_true')
    parser.add_argument('--interpolate', action='store_true')
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
        gtfs_jp = GTFS_JP(temp_dir)
        output_dir = temp_dir
    else:
        gtfs_jp = GTFS_JP(args.src_dir)
        output_dir = args.src_dir

    print('GTFS loaded.')

    if args.output_dir:
        output_dir = args.output_dir

    routes_features = [route for route in gtfs_jp.read_routes(no_shapes=args.no_shapes)]
    routes_geojson = {
        'type': 'FeatureCollection',
        'features': routes_features
    }

    stops_features = [stop for stop in gtfs_jp.read_stops(
        empty_stops=args.empty_stops, no_diagrams=args.no_diagrams)]
    stops_geojson = {
        'type': 'FeatureCollection',
        'features': stops_features
    }

    print('writing geojsons...')
    with open(os.path.join(output_dir, 'routes.geojson'), mode='w') as f:
        json.dump(routes_geojson, f, ensure_ascii=False)
    with open(os.path.join(output_dir, 'stops.geojson'), mode='w') as f:
        json.dump(stops_geojson, f, ensure_ascii=False)

    if args.interpolate:
        interpolated_stops_features = gtfs_jp.read_interpolated_stops()
        interpolated_stops_geojson = {
            'type': 'FeatureCollection',
            'features': interpolated_stops_features
        }
        with open(os.path.join(output_dir, 'interpolated_stops.geojson'), mode='w') as f:
            json.dump(interpolated_stops_geojson, f, ensure_ascii=False)
