import glob
import os

import pandas as pd


def GTFS(gtfs_dir: list) -> dict:
    tables = {}
    table_files = glob.glob(os.path.join(gtfs_dir, "*.txt"))
    for table_file in table_files:
        datatype = os.path.basename(table_file).split(".")[0]
        with open(table_file, encoding="utf-8_sig") as f:
            df = pd.read_csv(f, dtype=str)
            if len(df) == 0:
                print(f"{datatype}.txt is empty, skipping...")
                continue
            tables[datatype] = df

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
