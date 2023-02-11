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


def latlon_to_str(latlon):
    return "".join(list(map(lambda coord: str(round(coord, 4)), latlon)))


class GTFSParser:
    def __init__(
        self,
        src_dir: str,
        as_frequency=False,
        as_unify_stops=False,
        delimiter="",
        max_distance_degree=0.01,
    ):

        txts = glob.glob(os.path.join(src_dir, "**", "*.txt"), recursive=True)
        self.dataframes = self.__load_tables(txts)

        if as_frequency:
            self.similar_stops_df = None
            if as_unify_stops:
                self.aggregate_similar_stops(delimiter, max_distance_degree)
            else:
                # no unifying stops
                self.dataframes["stops"]["similar_stop_id"] = self.dataframes["stops"][
                    "stop_id"
                ]
                self.dataframes["stops"]["similar_stop_name"] = self.dataframes[
                    "stops"
                ]["stop_name"]
                self.dataframes["stops"]["similar_stops_centroid"] = self.dataframes[
                    "stops"
                ][["stop_lon", "stop_lat"]].values.tolist()
                self.similar_stops_df = self.dataframes["stops"][
                    ["similar_stop_id", "similar_stop_name", "similar_stops_centroid"]
                ].copy()

    @staticmethod
    def __load_tables(text_files: list[str]) -> dict:
        tables = {}
        for txt in text_files:
            datatype = os.path.basename(txt).split(".")[0]
            if datatype not in GTFS_DATATYPES:
                print(f"{datatype} is not specified in GTFS, skipping...")
                continue
            with open(txt, encoding="utf-8_sig") as f:
                df = pd.read_csv(f, dtype=str)
                if len(df) == 0:
                    print(f"{datatype}.txt is empty, skipping...")
                    continue
                tables[os.path.basename(txt).split(".")[0]] = df
        for datatype in GTFS_DATATYPES:
            if GTFS_DATATYPES[datatype]["required"] and datatype not in tables:
                raise FileNotFoundError(f"{datatype} is not exists.")

        # cast some numeric columns from str to numeric
        tables["stops"] = tables["stops"].astype({"stop_lon": float, "stop_lat": float})
        tables["stop_times"] = tables["stop_times"].astype({"stop_sequence": int})
        if tables.get("shapes") is not None:
            tables["shapes"] = tables["shapes"].astype(
                {"shape_pt_lon": float, "shape_pt_lat": float, "shape_pt_sequence": int}
            )

        # parent_station is optional column on GTFS but use in this module
        # when parent_station is not in stops, fill by 'nan' (not NaN)
        if "parent_station" not in tables.get("stops").columns:
            tables["stops"]["parent_station"] = "nan"

        return tables

    def aggregate_similar_stops(self, delimiter, max_distance_degree):
        parent_ids = self.dataframes["stops"]["parent_station"].unique()
        self.dataframes["stops"]["is_parent"] = self.dataframes["stops"]["stop_id"].map(
            lambda stop_id: 1 if stop_id in parent_ids else 0
        )

        self.dataframes["stops"][
            ["similar_stop_id", "similar_stop_name", "similar_stops_centroid"]
        ] = (
            self.dataframes["stops"]["stop_id"]
            .map(
                lambda stop_id: self.get_similar_stop_tuple(
                    stop_id, delimiter, max_distance_degree
                )
            )
            .apply(pd.Series)
        )
        self.dataframes["stops"]["position_id"] = self.dataframes["stops"][
            "similar_stops_centroid"
        ].map(latlon_to_str)
        self.dataframes["stops"]["unique_id"] = (
            self.dataframes["stops"]["similar_stop_id"]
            + self.dataframes["stops"]["position_id"]
        )

        # sometimes stop_name accidently becomes pd.Series instead of str.
        self.dataframes["stops"]["similar_stop_name"] = self.dataframes["stops"][
            "similar_stop_name"
        ].map(lambda val: val if type(val) == str else val.stop_name)

        self.similar_stops_df = (
            self.dataframes["stops"]
            .drop_duplicates(subset="unique_id")[
                [
                    "position_id",
                    "similar_stop_id",
                    "similar_stop_name",
                    "similar_stops_centroid",
                ]
            ]
            .copy()
        )

    def read_stops(self, ignore_no_route=False) -> list:
        """
        read stops by stops table

        Args:
            ignore_no_route (bool, optional): stops unconnected to routes are skipped. Defaults to False.

        Returns:
            list: [description]
        """

        # get unique list of route_id related to each stop
        stop_times_trip_df = pd.merge(
            self.dataframes["stop_times"],
            self.dataframes["trips"],
            on="trip_id",
        )
        route_ids_on_stops = stop_times_trip_df.groupby("stop_id")["route_id"].unique()
        route_ids_on_stops.apply(lambda x: x.sort())

        # parse stops to GeoJSON-Features
        features = []
        for stop in self.dataframes["stops"][
            ["stop_id", "stop_lat", "stop_lon", "stop_name"]
        ].itertuples():
            # get all route_id related to the stop
            route_ids = []
            if stop.stop_id in route_ids_on_stops:
                route_ids = route_ids_on_stops.at[stop.stop_id].tolist()

            if len(route_ids) == 0 and ignore_no_route:
                # skip to output the stop
                continue

            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": (stop.stop_lon, stop.stop_lat),
                    },
                    "properties": {
                        "stop_id": stop.stop_id,
                        "stop_name": stop.stop_name,
                        "route_ids": route_ids,
                    },
                }
            )
        return features

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

        stop_dicts = self.similar_stops_df[
            ["similar_stop_id", "similar_stop_name", "similar_stops_centroid"]
        ].to_dict(orient="records")
        return [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": stop["similar_stops_centroid"],
                },
                "properties": {
                    "similar_stop_name": stop["similar_stop_name"],
                    "similar_stop_id": stop["similar_stop_id"],
                },
            }
            for stop in stop_dicts
        ]

    def read_route_frequency(self, yyyymmdd="", begin_time="", end_time=""):
        """
        By grouped stops, aggregate route frequency.
        Filtering trips by a date, you can aggregate frequency only route serviced on the date.

        Args:
            yyyymmdd (str, optional): date, like 20210401. Defaults to ''.
            begin_time (str, optional): 'hhmmss' <= departure time, like 030000. Defaults to ''.
            end_time (str, optional): 'hhmmss' > departure time, like 280000. Defaults to ''.

        Returns:
            [type]: [description]
        """
        stop_times_df = (
            self.dataframes.get("stop_times")[
                ["stop_id", "trip_id", "stop_sequence", "departure_time"]
            ]
            .sort_values(["trip_id", "stop_sequence"])
            .copy()
        )

        # filter stop_times by whether serviced or not
        if yyyymmdd:
            trips_filtered_by_day = self.get_trips_on_a_date(yyyymmdd)
            stop_times_df = pd.merge(
                stop_times_df, trips_filtered_by_day, on="trip_id", how="left"
            )
            stop_times_df = stop_times_df[stop_times_df["service_flag"] == 1]

        # join agency info)
        stop_times_df = pd.merge(
            stop_times_df,
            self.dataframes["trips"][["trip_id", "route_id"]],
            on="trip_id",
            how="left",
        )
        stop_times_df = pd.merge(
            stop_times_df,
            self.dataframes["routes"][["route_id", "agency_id"]],
            on="route_id",
            how="left",
        )
        stop_times_df = pd.merge(
            stop_times_df,
            self.dataframes["agency"][["agency_id", "agency_name"]],
            on="agency_id",
            how="left",
        )

        # get prev and next stops_id, stop_name, trip_id
        stop_times_df = pd.merge(
            stop_times_df,
            self.dataframes["stops"][
                [
                    "stop_id",
                    "similar_stop_id",
                    "similar_stop_name",
                    "similar_stops_centroid",
                ]
            ],
            on="stop_id",
            how="left",
        )
        stop_times_df["prev_stop_id"] = stop_times_df["similar_stop_id"]
        stop_times_df["prev_trip_id"] = stop_times_df["trip_id"]
        stop_times_df["prev_stop_name"] = stop_times_df["similar_stop_name"]
        stop_times_df["prev_similar_stops_centroid"] = stop_times_df[
            "similar_stops_centroid"
        ]
        stop_times_df["next_stop_id"] = stop_times_df["similar_stop_id"].shift(-1)
        stop_times_df["next_trip_id"] = stop_times_df["trip_id"].shift(-1)
        stop_times_df["next_stop_name"] = stop_times_df["similar_stop_name"].shift(-1)
        stop_times_df["next_similar_stops_centroid"] = stop_times_df[
            "similar_stops_centroid"
        ].shift(-1)

        # drop last stops (-> stops has no next stop)
        stop_times_df = stop_times_df.drop(
            index=stop_times_df.query("prev_trip_id != next_trip_id").index
        )

        # time filter
        if begin_time and end_time:
            stop_times_df = self.stop_time_filter(stop_times_df, begin_time, end_time)

        # define path_id by prev-stops-centroid and next-stops-centroid
        stop_times_df["path_id"] = (
            stop_times_df["prev_stop_id"]
            + stop_times_df["next_stop_id"]
            + stop_times_df["prev_similar_stops_centroid"].map(latlon_to_str)
            + stop_times_df["next_similar_stops_centroid"].map(latlon_to_str)
        )

        # aggregate path-frequency
        path_frequency = (
            stop_times_df[["similar_stop_id", "path_id"]]
            .groupby("path_id")
            .count()
            .reset_index()
        )
        path_frequency.columns = ["path_id", "path_count"]
        path_data = pd.merge(
            path_frequency,
            stop_times_df.drop_duplicates(subset="path_id"),
            on="path_id",
        )
        path_data_dict = path_data.to_dict(orient="records")

        return [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": (
                        path["prev_similar_stops_centroid"],
                        path["next_similar_stops_centroid"],
                    ),
                },
                "properties": {
                    "frequency": path["path_count"],
                    "prev_stop_id": path["prev_stop_id"],
                    "prev_stop_name": path["prev_stop_name"],
                    "next_stop_id": path["next_stop_id"],
                    "next_stop_name": path["next_stop_name"],
                    "agency_id": path["agency_id"],
                    "agency_name": path["agency_name"],
                },
            }
            for path in path_data_dict
        ]

    def stop_time_filter(self, stop_time_df, begin_time, end_time):
        # departure_time is nullable and expressed in "hh:mm:ss" or "h:mm:ss" format.
        # Hour can be mor than 24.
        # Therefore, drop null records and convert times to integers.
        df = stop_time_df[stop_time_df.departure_time != ""]
        int_dep_times = stop_time_df.departure_time.str.replace(":", "").astype(int)
        return df[(int_dep_times >= int(begin_time)) & (int_dep_times < int(end_time))]

    @lru_cache(maxsize=None)
    def get_similar_stop_tuple(
        self, stop_id: str, delimiter="", max_distance_degree=0.01
    ):
        """
        With one stop_id, group stops by parent, stop_id, or stop_name and each distance.
        - parent: if stop has parent_station, the 'centroid' is parent_station lat-lon
        - stop_id: by delimiter seperate stop_id into prefix and suffix, and group stops having same stop_id-prefix
        - name and distance: group stops by stop_name, excluding stops are far than max_distance_degree

        Args:
            stop_id (str): target stop_id
            max_distance_degree (float, optional): distance limit on grouping, Defaults to 0.01.
        Returns:
            str, str, [float, float]: similar_stop_id, similar_stop_name, similar_stops_centroid
        """
        stops_df = self.dataframes["stops"].sort_values("stop_id")
        stop = stops_df[stops_df["stop_id"] == stop_id].iloc[0]

        if stop["is_parent"] == 1:
            return (
                stop["stop_id"],
                stop["stop_name"],
                [stop["stop_lon"], stop["stop_lat"]],
            )

        if str(stop["parent_station"]) != "nan":
            similar_stop_id = stop["parent_station"]
            similar_stop = stops_df[stops_df["stop_id"] == similar_stop_id]
            similar_stop_name = similar_stop[["stop_name"]].iloc[0]
            similar_stop_centroid = (
                similar_stop[["stop_lon", "stop_lat"]].iloc[0].values.tolist()
            )
            return similar_stop_id, similar_stop_name, similar_stop_centroid

        if delimiter:
            stops_df_id_delimited = self.get_stops_id_delimited(delimiter)
            stop_id_prefix = stop_id.rsplit(delimiter, 1)[0]
            if stop_id_prefix != stop_id:
                similar_stop_id = stop_id_prefix
                seperated_only_stops = stops_df_id_delimited[
                    stops_df_id_delimited["delimited"]
                ]
                similar_stops = seperated_only_stops[
                    seperated_only_stops["stop_id_prefix"] == stop_id_prefix
                ][
                    [
                        "stop_name",
                        "similar_stops_centroid_lon",
                        "similar_stops_centroid_lat",
                    ]
                ]
                similar_stop_name = similar_stops[["stop_name"]].iloc[0]
                similar_stop_centroid = similar_stops[
                    ["similar_stops_centroid_lon", "similar_stops_centroid_lat"]
                ].values.tolist()[0]
                return similar_stop_id, similar_stop_name, similar_stop_centroid
            else:
                # when cannot seperate stop_id, grouping by name and distance
                stops_df = stops_df_id_delimited[~stops_df_id_delimited["delimited"]]

        # grouping by name and distance
        similar_stops = stops_df[stops_df["stop_name"] == stop["stop_name"]][
            ["stop_id", "stop_name", "stop_lon", "stop_lat"]
        ]
        similar_stops = similar_stops.query(
            f'(stop_lon - {stop["stop_lon"]}) ** 2 + (stop_lat - {stop["stop_lat"]}) ** 2  < {max_distance_degree ** 2}'
        )
        similar_stop_centroid = (
            similar_stops[["stop_lon", "stop_lat"]].mean().values.tolist()
        )
        similar_stop_id = similar_stops["stop_id"].iloc[0]
        similar_stop_name = stop["stop_name"]
        return similar_stop_id, similar_stop_name, similar_stop_centroid

    @lru_cache(maxsize=None)
    def get_stops_id_delimited(self, delimiter):
        stops_df = self.dataframes.get("stops")[
            ["stop_id", "stop_name", "stop_lon", "stop_lat", "parent_station"]
        ].copy()
        stops_df["stop_id_prefix"] = stops_df["stop_id"].map(
            lambda stop_id: stop_id.rsplit(delimiter, 1)[0]
        )
        stops_df["delimited"] = stops_df["stop_id"] != stops_df["stop_id_prefix"]
        grouped_by_prefix = (
            stops_df[["stop_id_prefix", "stop_lon", "stop_lat"]]
            .groupby("stop_id_prefix")
            .mean()
            .reset_index()
        )
        grouped_by_prefix.columns = [
            "stop_id_prefix",
            "similar_stops_centroid_lon",
            "similar_stops_centroid_lat",
        ]
        stops_df_with_centroid = pd.merge(
            stops_df, grouped_by_prefix, on="stop_id_prefix", how="left"
        )
        return stops_df_with_centroid

    @staticmethod
    def __get_route_name_from_tupple(route):
        if not pd.isna(route.route_short_name):
            return route.route_short_name
        elif not pd.isna(route.route_long_name):
            return route.route_long_name
        else:
            ValueError(f'{route} have neither "route_long_name" or "route_short_time".')

    def __get_shape_ids_on_routes(self):
        trips_with_shape_df = self.dataframes["trips"][["route_id", "shape_id"]].dropna(
            subset=["shape_id"]
        )
        group = trips_with_shape_df.groupby("route_id")["shape_id"].unique()
        group.apply(lambda x: x.sort())
        return group

    def __get_shapes_coordinates(self):
        shapes_df = self.dataframes["shapes"].copy()
        shapes_df.sort_values("shape_pt_sequence")
        shapes_df["pt"] = shapes_df[["shape_pt_lon", "shape_pt_lat"]].values.tolist()
        return shapes_df.groupby("shape_id")["pt"].apply(tuple)

    def get_trips_on_a_date(self, yyyymmdd: str):
        """
        get trips are on service on a date.

        Args:
            yyyymmdd (str): [description]

        Returns:
            [type]: [description]
        """
        # sunday, monday, tuesday...
        day_of_week = (
            datetime.date(int(yyyymmdd[0:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]))
            .strftime("%A")
            .lower()
        )

        # filter services by day
        calendar_df = self.dataframes["calendar"].copy()
        calendar_df = calendar_df.astype({"start_date": int, "end_date": int})
        calendar_df = calendar_df[calendar_df[day_of_week] == "1"]
        calendar_df = calendar_df.query(
            f"start_date <= {int(yyyymmdd)} and {int(yyyymmdd)} <= end_date",
            engine="python",
        )

        services_on_a_day = calendar_df[["service_id"]]

        calendar_dates_df = self.dataframes.get("calendar_dates")
        if calendar_dates_df is not None:
            filtered = calendar_dates_df[calendar_dates_df["date"] == yyyymmdd][
                ["service_id", "exception_type"]
            ]
            to_be_removed_services = filtered[filtered["exception_type"] == "2"]
            to_be_appended_services = filtered[filtered["exception_type"] == "1"][
                ["service_id"]
            ]

            services_on_a_day = pd.merge(
                services_on_a_day, to_be_removed_services, on="service_id", how="left"
            )
            services_on_a_day = services_on_a_day[
                services_on_a_day["exception_type"] != "2"
            ]
            services_on_a_day = pd.concat([services_on_a_day, to_be_appended_services])

        services_on_a_day["service_flag"] = 1

        # filter trips
        trips_df = self.dataframes["trips"].copy()
        trip_service = pd.merge(trips_df, services_on_a_day, on="service_id")
        trip_service = trip_service[trip_service["service_flag"] == 1]

        return trip_service[["trip_id", "service_flag"]]

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
        features = []

        if self.dataframes.get("shapes") is None or no_shapes:
            # trip-route-merge:A
            trips_routes = pd.merge(
                self.dataframes["trips"][["trip_id", "route_id"]],
                self.dataframes["routes"][
                    ["route_id", "route_long_name", "route_short_name"]
                ],
                on="route_id",
            )

            # stop_times-stops-merge:B
            stop_times_stop = pd.merge(
                self.dataframes["stop_times"][["stop_id", "trip_id", "stop_sequence"]],
                self.dataframes.get("stops")[["stop_id", "stop_lon", "stop_lat"]],
                on="stop_id",
            )

            # A-B-merge
            merged = pd.merge(stop_times_stop, trips_routes, on="trip_id")
            merged["route_concat_name"] = merged["route_long_name"].fillna("") + merged[
                "route_short_name"
            ].fillna("")

            # parse routes
            for route_id in merged["route_id"].unique():
                route = merged[merged["route_id"] == route_id]
                trip_id = route["trip_id"].unique()[0]
                route = route[route["trip_id"] == trip_id].sort_values("stop_sequence")
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": route[
                                ["stop_lon", "stop_lat"]
                            ].values.tolist(),
                        },
                        "properties": {
                            "route_id": str(route_id),
                            "route_name": route.route_concat_name.values.tolist()[0],
                        },
                    }
                )
        else:
            # parse shape.txt to GeoJSON-Features
            shape_coords = self.__get_shapes_coordinates()
            shape_ids_on_routes = self.__get_shape_ids_on_routes()
            # list-up already loaded shape_ids
            loaded_shape_ids = set()
            for route in self.dataframes.get("routes").itertuples():
                if shape_ids_on_routes.get(route.route_id) is None:
                    continue

                # get coords by route_id
                coordinates = []
                for shape_id in shape_ids_on_routes[route.route_id]:
                    coordinates.append(shape_coords.at[shape_id])
                    loaded_shape_ids.add(shape_id)  # update loaded shape_ids

                route_name = self.__get_route_name_from_tupple(route)
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "MultiLineString",
                            "coordinates": coordinates,
                        },
                        "properties": {
                            "route_id": str(route.route_id),
                            "route_name": route_name,
                        },
                    }
                )

            # load shapes unloaded yet
            for shape_id in list(
                filter(lambda id: id not in loaded_shape_ids, shape_coords.index)
            ):
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "MultiLineString",
                            "coordinates": [shape_coords.at[shape_id]],
                        },
                        "properties": {
                            "route_id": None,
                            "route_name": str(shape_id),
                        },
                    }
                )

        return features


if __name__ == "__main__":
    import argparse
    import shutil

    parser = argparse.ArgumentParser()
    parser.add_argument("--zip")
    parser.add_argument("--src_dir")
    parser.add_argument("--output_dir")
    parser.add_argument("--no_shapes", action="store_true")
    parser.add_argument("--ignore_no_route", action="store_true")
    parser.add_argument("--frequency", action="store_true")
    parser.add_argument("--yyyymmdd")
    parser.add_argument("--as_unify_stops", action="store_true")
    parser.add_argument("--delimiter")
    parser.add_argument("--begin_time")
    parser.add_argument("--end_time")
    args = parser.parse_args()

    if args.zip is None and args.src_dir is None:
        raise RuntimeError("gtfs-jp-parser needs zipfile or src_dir.")

    if args.yyyymmdd:
        if len(args.yyyymmdd) != 8:
            raise RuntimeError(
                f"yyyymmdd must be 8 characters string, for example 20210401, your is {args.yyyymmdd} ({len(args.yyyymmdd)} characters)"
            )

    if args.begin_time:
        if len(args.begin_time) != 6:
            raise RuntimeError(
                f'begin_time must be "hhmmss", your is {args.begin_time}'
            )
        if not args.end_time:
            raise RuntimeError("end_time is not set.")

    if args.end_time:
        if len(args.end_time) != 6:
            raise RuntimeError(f'end_time must be "hhmmss", your is {args.end_time}')
        if not args.begin_time:
            raise RuntimeError("begin_time is not set.")

    if args.zip:
        print("extracting zipfile...")
        temp_dir = os.path.join(tempfile.gettempdir(), "gtfs-jp-parser")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.mkdir(temp_dir)
        with zipfile.ZipFile(args.zip) as z:
            z.extractall(temp_dir)
        output_dir = temp_dir
    else:
        output_dir = args.src_dir
    gtfs_parser = GTFSParser(
        output_dir,
        as_frequency=args.frequency,
        as_unify_stops=args.as_unify_stops,
        delimiter=args.delimiter,
    )

    print("GTFS loaded.")

    if args.output_dir:
        output_dir = args.output_dir

    if args.frequency:
        stops_features = gtfs_parser.read_interpolated_stops()
        stops_geojson = {"type": "FeatureCollection", "features": stops_features}
        routes_features = gtfs_parser.read_route_frequency(
            yyyymmdd=args.yyyymmdd, begin_time=args.begin_time, end_time=args.end_time
        )
        routes_geojson = {"type": "FeatureCollection", "features": routes_features}
        gtfs_parser.dataframes["stops"][
            ["stop_id", "stop_name", "similar_stop_id", "similar_stop_name"]
        ].to_csv(os.path.join(output_dir, "result.csv"), index=False, encoding="cp932")
    else:
        routes_features = gtfs_parser.read_routes(no_shapes=args.no_shapes)
        routes_geojson = {"type": "FeatureCollection", "features": routes_features}
        stops_features = gtfs_parser.read_stops(ignore_no_route=args.ignore_no_route)
        stops_geojson = {"type": "FeatureCollection", "features": stops_features}

    print("writing geojsons...")
    with open(
        os.path.join(output_dir, "routes.geojson"), mode="w", encoding="utf-8"
    ) as f:
        json.dump(routes_geojson, f, ensure_ascii=False)
    with open(
        os.path.join(output_dir, "stops.geojson"), mode="w", encoding="utf-8"
    ) as f:
        json.dump(stops_geojson, f, ensure_ascii=False)
