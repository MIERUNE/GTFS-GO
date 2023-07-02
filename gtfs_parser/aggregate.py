from functools import lru_cache
import datetime

import pandas as pd


def latlon_to_str(latlon):
    return "".join(list(map(lambda coord: str(round(coord, 4)), latlon)))


class Aggregator:
    def __init__(
        self,
        gtfs: dict,
        no_unify_stops=False,
        delimiter="",
        max_distance_degree=0.01,
        yyyymmdd="",
        begin_time="",
        end_time="",
    ):
        self.gtfs = gtfs
        self.similar_stops_df = None

        self.__aggregate_similar_stops(
            delimiter,
            max_distance_degree,
            no_unify_stops,
            yyyymmdd=yyyymmdd,
            begin_time=begin_time,
            end_time=end_time,
        )

    def __aggregate_similar_stops(
        self,
        delimiter: str,
        max_distance_degree: float,
        no_unify_stops: bool,
        yyyymmdd="",
        begin_time="",
        end_time="",
    ):
        """
        this method occurs side-effect to modify self.gtfs and self.similar_stops_df
        """
        # filter stop_times by whether serviced or not
        if yyyymmdd:
            trips_filtered_by_day = self.__get_trips_on_a_date(yyyymmdd)
            self.gtfs["stop_times"] = pd.merge(
                self.gtfs["stop_times"],
                trips_filtered_by_day,
                on="trip_id",
                how="left",
            )
            self.gtfs["stop_times"] = self.gtfs["stop_times"][
                self.gtfs["stop_times"]["service_flag"] == 1
            ]

        # time filter
        if begin_time and end_time:
            # departure_time is nullable and expressed in "hh:mm:ss" or "h:mm:ss" format.
            # Hour can be mor than 24.
            # Therefore, drop null records and convert times to integers.
            int_dep_times = (
                self.gtfs["stop_times"].departure_time.str.replace(":", "").astype(int)
            )
            self.gtfs["stop_times"] = self.gtfs["stop_times"][
                self.gtfs["stop_times"].departure_time != ""
            ][(int_dep_times >= int(begin_time)) & (int_dep_times < int(end_time))]

        if no_unify_stops:
            # no unifying stops
            self.gtfs["stops"]["similar_stop_id"] = self.gtfs["stops"]["stop_id"]
            self.gtfs["stops"]["similar_stop_name"] = self.gtfs["stops"]["stop_name"]
            self.gtfs["stops"]["similar_stops_centroid"] = self.gtfs["stops"][
                ["stop_lon", "stop_lat"]
            ].values.tolist()
            self.gtfs["stops"]["position_count"] = 1
            self.similar_stops_df = self.gtfs["stops"][
                [
                    "similar_stop_id",
                    "similar_stop_name",
                    "similar_stops_centroid",
                    "position_count",
                ]
            ].copy()
        else:
            parent_ids = self.gtfs["stops"]["parent_station"].unique()
            self.gtfs["stops"]["is_parent"] = self.gtfs["stops"]["stop_id"].map(
                lambda stop_id: 1 if stop_id in parent_ids else 0
            )

            self.gtfs["stops"][
                ["similar_stop_id", "similar_stop_name", "similar_stops_centroid"]
            ] = (
                self.gtfs["stops"]["stop_id"]
                .map(
                    lambda stop_id: self.__get_similar_stop_tuple(
                        stop_id, delimiter, max_distance_degree
                    )
                )
                .apply(pd.Series)
            )
            self.gtfs["stops"]["position_id"] = self.gtfs["stops"][
                "similar_stops_centroid"
            ].map(latlon_to_str)
            self.gtfs["stops"]["unique_id"] = (
                self.gtfs["stops"]["similar_stop_id"]
                + self.gtfs["stops"]["position_id"]
            )

            # sometimes stop_name accidently becomes pd.Series instead of str.
            self.gtfs["stops"]["similar_stop_name"] = self.gtfs["stops"][
                "similar_stop_name"
            ].map(lambda val: val if type(val) == str else val.stop_name)

            position_count = (
                self.gtfs["stop_times"]
                .merge(self.gtfs["stops"], on="stop_id", how="left")
                .groupby("position_id")
                .size()
                .to_frame()
                .reset_index()
            )
            position_count.columns = ["position_id", "position_count"]

            self.similar_stops_df = pd.merge(
                self.gtfs["stops"].drop_duplicates(subset="position_id")[
                    [
                        "position_id",
                        "similar_stop_id",
                        "similar_stop_name",
                        "similar_stops_centroid",
                    ]
                ],
                position_count,
                on="position_id",
                how="left",
            )

    @lru_cache(maxsize=None)
    def __get_similar_stop_tuple(
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
        stops_df = self.gtfs["stops"].sort_values("stop_id")
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
            stops_df_id_delimited = self.__get_stops_id_delimited(delimiter)
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
    def __get_stops_id_delimited(self, delimiter: str):
        stops_df = self.gtfs.get("stops")[
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
            [
                "similar_stop_id",
                "similar_stop_name",
                "similar_stops_centroid",
                "position_count",
            ]
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
                    "count": stop["position_count"],
                },
            }
            for stop in stop_dicts
        ]

    def read_route_frequency(self):
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
            self.gtfs.get("stop_times")[
                ["stop_id", "trip_id", "stop_sequence", "departure_time"]
            ]
            .sort_values(["trip_id", "stop_sequence"])
            .copy()
        )

        # join agency info)
        stop_times_df = pd.merge(
            stop_times_df,
            self.gtfs["trips"][["trip_id", "route_id"]],
            on="trip_id",
            how="left",
        )
        stop_times_df = pd.merge(
            stop_times_df,
            self.gtfs["routes"][["route_id", "agency_id"]],
            on="route_id",
            how="left",
        )
        stop_times_df = pd.merge(
            stop_times_df,
            self.gtfs["agency"][["agency_id", "agency_name"]],
            on="agency_id",
            how="left",
        )

        # get prev and next stops_id, stop_name, trip_id
        stop_times_df = pd.merge(
            stop_times_df,
            self.gtfs["stops"][
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

    def __get_trips_on_a_date(self, yyyymmdd: str):
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
        calendar_df = self.gtfs["calendar"].copy()
        calendar_df = calendar_df.astype({"start_date": int, "end_date": int})
        calendar_df = calendar_df[calendar_df[day_of_week] == "1"]
        calendar_df = calendar_df.query(
            f"start_date <= {int(yyyymmdd)} and {int(yyyymmdd)} <= end_date",
            engine="python",
        )

        services_on_a_day = calendar_df[["service_id"]]

        calendar_dates_df = self.gtfs.get("calendar_dates")
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
        trips_df = self.gtfs["trips"].copy()
        trip_service = pd.merge(trips_df, services_on_a_day, on="service_id")
        trip_service = trip_service[trip_service["service_flag"] == 1]

        return trip_service[["trip_id", "service_flag"]]
