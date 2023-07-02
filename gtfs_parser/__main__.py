import json
import os
import zipfile
import tempfile
import argparse
import shutil

from .gtfs import GTFS
from .parse import read_routes, read_stops
from .aggregate import Aggregator


def load_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode")
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--parse_ignoreshapes", action="store_true")
    parser.add_argument("--parse_ignorenoroute", action="store_true")
    parser.add_argument("--aggregate_yyyymmdd")
    parser.add_argument("--aggregate_nounifystops", action="store_true")
    parser.add_argument("--aggregate_delimiter")
    parser.add_argument("--aggregate_begintime")
    parser.add_argument("--aggregate_endtime")
    args = parser.parse_args()
    return args


def validate_args(args):
    if args.aggregate_yyyymmdd:
        if len(args.aggregate_yyyymmdd) != 8:
            raise RuntimeError(
                f"yyyymmdd must be 8 characters string, for example 20210401, \
                    your is {args.aggregate_yyyymmdd} ({len(args.aggregate_yyyymmdd)} characters)"
            )

    if args.aggregate_begintime:
        if len(args.aggregate_begintime) != 6:
            raise RuntimeError(
                f'begintime must be "hhmmss", your is {args.aggregate_begintime}'
            )
        if not args.aggregate_endtime:
            raise RuntimeError("endtime is not set.")

    if args.aggregate_endtime:
        if len(args.aggregate_endtime) != 6:
            raise RuntimeError(
                f'endtime must be "hhmmss", your is {args.aggregate_endtime}'
            )
        if not args.aggregate_begintime:
            raise RuntimeError("begintime is not set.")


if __name__ == "__main__":
    args = load_args()
    validate_args(args)

    if args.src.endswith(".zip"):  # TODO: wiser checking
        print("extracting zipfile...")
        temp_dir = os.path.join(tempfile.gettempdir(), "gtfs_parser")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.mkdir(temp_dir)
        with zipfile.ZipFile(args.zip) as z:
            z.extractall(temp_dir)
        output_dir = temp_dir
    else:
        output_dir = args.src

    gtfs = GTFS(output_dir)
    print("GTFS loaded.")

    os.makedirs(args.dst, exist_ok=True)

    if args.mode == "aggregate":
        aggregator = Aggregator(
            gtfs,
            no_unify_stops=args.aggregate_nounifystops,
            delimiter=args.aggregate_delimiter,
            yyyymmdd=args.aggregate_yyyymmdd,
            begin_time=args.aggregate_begintime,
            end_time=args.aggregate_endtime,
        )
        aggregated_routes_geojson = {
            "type": "FeatureCollection",
            "features": aggregator.read_route_frequency(),
        }
        aggregated_stops_geojson = {
            "type": "FeatureCollection",
            "features": aggregator.read_interpolated_stops(),
        }

        with open(
            os.path.join(args.dst, "aggregated_routes.geojson"),
            mode="w",
            encoding="utf-8",
        ) as f:
            json.dump(aggregated_routes_geojson, f, ensure_ascii=False)
        with open(
            os.path.join(args.dst, "aggregated_stops.geojson"),
            mode="w",
            encoding="utf-8",
        ) as f:
            json.dump(aggregated_stops_geojson, f, ensure_ascii=False)
    elif args.mode == "parse":
        routes_geojson = {
            "type": "FeatureCollection",
            "features": read_routes(gtfs, ignore_shapes=args.parse_ignoreshapes),
        }
        stops_geojson = {
            "type": "FeatureCollection",
            "features": read_stops(gtfs, ignore_no_route=args.parse_ignorenoroute),
        }

        with open(
            os.path.join(args.dst, "routes.geojson"), mode="w", encoding="utf-8"
        ) as f:
            json.dump(routes_geojson, f, ensure_ascii=False)
        with open(
            os.path.join(args.dst, "stops.geojson"), mode="w", encoding="utf-8"
        ) as f:
            json.dump(stops_geojson, f, ensure_ascii=False)
    else:
        raise RuntimeError("mode must be 'parse' or 'aggregate")
