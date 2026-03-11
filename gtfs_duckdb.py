from __future__ import annotations

import os
from dataclasses import dataclass

import duckdb


@dataclass
class GtfsConnection:
    conn: duckdb.DuckDBPyConnection
    has_shapes: bool


def init_gtfs_connection(folder: str, feedback=None) -> GtfsConnection:
    """Create DuckDB connection and load GTFS CSV files from a folder."""
    has_shapes = os.path.exists(os.path.join(folder, "shapes.txt"))

    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")

    d = folder.replace("\\", "/")

    conn.execute(f"""
        CREATE TABLE stops_geo AS
        SELECT *, ST_Point(stop_lon, stop_lat) AS geom
        FROM read_csv('{d}/stops.txt', types={{
            'stop_lon': 'DOUBLE',
            'stop_lat': 'DOUBLE',
            'stop_id': 'VARCHAR',
            'stop_name': 'VARCHAR',
            'location_type': 'INT'
        }});
    """)

    conn.execute(
        "ALTER TABLE stops_geo ADD COLUMN IF NOT EXISTS parent_station VARCHAR;"
    )

    conn.execute(f"""
        CREATE TABLE stop_times AS
        SELECT * FROM read_csv('{d}/stop_times.txt',
            types={{'arrival_time': 'VARCHAR', 'departure_time': 'VARCHAR'}});
    """)

    conn.execute(f"""
        CREATE TABLE trips AS
        SELECT * FROM read_csv('{d}/trips.txt');
    """)

    conn.execute(f"""
        CREATE TABLE routes AS
        SELECT * FROM read_csv('{d}/routes.txt');
    """)

    if has_shapes:
        conn.execute(f"""
            CREATE TABLE shapes AS
            SELECT * FROM read_csv('{d}/shapes.txt');
        """)
    else:
        conn.execute("""
            CREATE TABLE shapes (
                shape_id VARCHAR,
                shape_pt_sequence INT,
                shape_pt_lon DOUBLE,
                shape_pt_lat DOUBLE
            );
        """)

    if feedback:
        feedback.pushInfo("GTFS data loaded into DuckDB.")

    return GtfsConnection(conn=conn, has_shapes=has_shapes)
