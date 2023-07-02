import pandas as pd

def read_stops(gtfs:dict, ignore_no_route=False) -> list:
    """
    read stops by stops table

    Args:
        ignore_no_route (bool, optional): stops unconnected to routes are skipped. Defaults to False.

    Returns:
        list: [description]
    """

    # get unique list of route_id related to each stop
    stop_times_trip_df = pd.merge(
        gtfs["stop_times"],
        gtfs["trips"],
        on="trip_id",
    )
    route_ids_on_stops = stop_times_trip_df.groupby("stop_id")["route_id"].unique()
    route_ids_on_stops.apply(lambda x: x.sort())

    # parse stops to GeoJSON-Features
    features = []
    for stop in gtfs["stops"][
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


def read_routes(gtfs:dict, ignore_shapes=False) -> list:
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

    if gtfs.get("shapes") is None or ignore_shapes:
        # trip-route-merge:A
        trips_routes = pd.merge(
            gtfs["trips"][["trip_id", "route_id"]],
            gtfs["routes"][
                ["route_id", "route_long_name", "route_short_name"]
            ],
            on="route_id",
        )

        # stop_times-stops-merge:B
        stop_times_stop = pd.merge(
            gtfs["stop_times"][["stop_id", "trip_id", "stop_sequence"]],
            gtfs.get("stops")[["stop_id", "stop_lon", "stop_lat"]],
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
        # get_shapeids_on route
        trips_with_shape_df = gtfs["trips"][["route_id", "shape_id"]].dropna(
            subset=["shape_id"]
        )
        shape_ids_on_routes = trips_with_shape_df.groupby("route_id")["shape_id"].unique()
        shape_ids_on_routes.apply(lambda x: x.sort())

        #get shape coordinate
        shapes_df = gtfs["shapes"].copy()
        shapes_df.sort_values("shape_pt_sequence")
        shapes_df["pt"] = shapes_df[["shape_pt_lon", "shape_pt_lat"]].values.tolist()
        shape_coords = shapes_df.groupby("shape_id")["pt"].apply(tuple)

        # list-up already loaded shape_ids
        loaded_shape_ids = set()
        for route in gtfs.get("routes").itertuples():
            if shape_ids_on_routes.get(route.route_id) is None:
                continue

            # get coords by route_id
            coordinates = []
            for shape_id in shape_ids_on_routes[route.route_id]:
                coordinates.append(shape_coords.at[shape_id])
                loaded_shape_ids.add(shape_id)  # update loaded shape_ids

            #get_route_name_from_tupple
            if not pd.isna(route.route_short_name):
                route_name = route.route_short_name
            elif not pd.isna(route.route_long_name):
                route_name = route.route_long_name
            else:
                ValueError(f'{route} have neither "route_long_name" or "route_short_time".')

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
