import json
import os
import glob
import zipfile
import tempfile
from functools import lru_cache

import pandas as pd

from .constants import GTFS_JP_DATATYPES


class GTFSParser:
    def __init__(self, src_dir: str):
        """
        Generates a dataframe from the zip file.

        Args:
            src_dir (str): path to the zip file holding the GTFS data

        Raises:
            FileNotFoundError: Error raised when there is a missing required file.
        """
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
                raise FileNotFoundError(f'{datatype} column does not exists.')

    def stops_count(self):
        """
        Counts the number of stops inside the dataset

        Returns:
            stops (int): Number of stops inside the GTFS dataset
        """
        stops_df = self.dataframes['stops']
        return len(stops_df)

    def read_stops(self, ignore_no_route=False, diagram_mode=False):
        """
        Read the stops data and transform them into GeoJSON

        Args:
            ignore_no_route (bool, optional): Ignore stops without route. Defaults to False.
            diagram_mode (bool, optional):　if True it will create a diagram key in the json with routes, destination and stop_id. Defaults to False.

        Yields:
            feature (GeoJSON): Yields a geojson of a point composed by the details of the stop.
            None (None): Yields None in case there is no data to return.
        """
        stops_df = self.dataframes['stops'][[
            'stop_id', 'stop_lat', 'stop_lon', 'stop_name']]
        stop_times_df = self.dataframes['stop_times'].reindex(
            columns=['stop_id', 'trip_id', 'departure_time'])
        trips_df = self.dataframes['trips']
        routes_df = self.dataframes['routes']

        for idx in range(stops_df.shape[0]):
            # extract key datas from Dataframe
            stop_id = stops_df['stop_id'].iloc[idx]
            stop_lat = stops_df['stop_lat'].iloc[idx]
            stop_lon = stops_df['stop_lon'].iloc[idx]
            stop_name = stops_df['stop_name'].iloc[idx]

            diagrams = None
            if diagram_mode:
                filtered = stop_times_df[stop_times_df['stop_id'] == stop_id]
                merged = pd.merge(
                    pd.merge(
                        filtered,
                        trips_df,
                        on='trip_id'),
                    routes_df,
                    on='route_id')

                diagrams = {}
                for idx in range(merged.shape[0]):
                    # extract key datas from Dataframe
                    route_id = merged['route_id'].iloc[idx]
                    departure_time = merged['departure_time'].iloc[idx]
                    service_id = merged['service_id'].iloc[idx]
                    trip_id = merged['trip_id'].iloc[idx]

                    # get route name from long or short
                    route_data = routes_df[routes_df['route_id']
                                           == route_id].iloc[0]
                    route_name = self.get_route_name_from(route_data)

                    departure_time = str(departure_time)
                    service_id = str(service_id)
                    destination = str(self.get_destination_stop_of(
                        trip_id)['stop_name'].values[0])

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

            route_ids = self.get_route_ids_by(stop_id)
            if ignore_no_route and len(route_ids) == 0:
                yield None
                continue

            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [stop_lon, stop_lat]
                },
                'properties': {
                    'stop_id': str(stop_id),
                    'stop_name': stop_name,
                    'diagrams': diagrams,
                    'route_ids': route_ids
                }
            }
            yield feature

    def interpolated_stops_count(self):
        """
        Counts the stops with unique names.

        Returns:
            stop counts (int): Count of unique stops
        """
        stops_df = self.dataframes['stops']
        stop_names = stops_df['stop_name'].unique()
        return len(stop_names)

    def read_interpolated_stops(self):
        """
        Return unique stops.

        Yields:
            feature (GeoJSON): Yields a geojson of a the unique point composed by the details of the stop.
        """
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

    def get_route_ids_by(self, stop_id):
        """
        Return ids of routes that pass through that stop_id.

        Args:
            stop_id (string): The id of the stop whose routes are to be returned.

        Returns:
            route_ids (list): list of route_ids that
        """
        stop_times_df = self.dataframes['stop_times'][['stop_id', 'trip_id']]
        trip_id_series = stop_times_df[stop_times_df['stop_id']
                                       == stop_id]['trip_id']
        trip_ids = trip_id_series.unique().astype(str).tolist()

        trips_df = self.dataframes['trips'][['trip_id', 'route_id']]
        filtered = trips_df[trips_df['trip_id'].isin(trip_ids)]
        return filtered['route_id'].unique().astype(str).tolist()

    def get_route_name_from(self, route_data):
        """
        Returns the route name from the route_data
        Args:
            route_data (dict): dict object containing the route data

        Returns:
            route_name (str): route name
        """
        if not str(route_data['route_long_name']) == 'nan':
            return str(route_data['route_long_name'])
        elif not str(route_data['route_short_name']) == 'nan':
            return str(route_data['route_short_name'])
        else:
            ValueError(
                f'{route_data} have neither "route_long_name" or "route_short_time".')

    def routes_count(self, no_shapes=False):
        """
        Counts the routes

        Args:
            no_shapes (bool, optional): whether to count the routes from shapes or not. Defaults to False.

        Returns:
            routes (int): how may routes in the dataset.
        """
        shapes_df = self.dataframes.get('shapes')
        if shapes_df is not None and not no_shapes:
            shape_ids = shapes_df['shape_id'].unique()
            return len(shape_ids)
        else:
            trips_df = self.dataframes['trips']
            route_ids = trips_df['route_id'].unique()
            return len(route_ids)

    def read_routes(self, no_shapes=False):
        """
        Read routes and yields them as geojson

        Args:
            no_shapes (bool, optional): whether to read the routes from the shapes or not. Defaults to False.

        Yields:
            feature (GeoJSON): A geojson of a route data as a linestring.
        """
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

    @ lru_cache(maxsize=None)
    def get_destination_stop_of(self, trip_id):
        """
        Returns the final stop of the trip

        Args:
            trip_id (str): Id of the trip

        Returns:
            destination_stop (pd.DataFrame): last stop of the trip
        """
        stop_times_df = self.dataframes['stop_times']
        filtered = stop_times_df[stop_times_df['trip_id'] == trip_id]
        max_stop_sequence_idx = filtered['stop_sequence'].idxmax()
        stops_df = self.dataframes['stops']
        destination_stop = stops_df[stops_df['stop_id'] ==
                                    stop_times_df['stop_id'].iloc[max_stop_sequence_idx]]
        return destination_stop

    @ lru_cache(maxsize=None)
    def get_trips_filtered_by(self, route_id: str):
        """
        Returns the trips that pass through that route.

        Args:
            route_id (str): The id of the route linked with the trips

        Returns:
            trips (pandas.core.series.Series): Series of trips which can be done through that route
        """
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
    parser.add_argument('--diagram_mode', action='store_true')
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

    routes_features = [route for route in gtfs_jp.read_routes(
        no_shapes=args.no_shapes)]
    routes_geojson = {
        'type': 'FeatureCollection',
        'features': routes_features
    }

    stops_features = [stop for stop in gtfs_jp.read_stops(
        empty_stops=args.empty_stops, diagram_mode=args.diagram_mode)]
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
