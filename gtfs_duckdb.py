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

    # Macro to convert GTFS time string (may exceed 24:00:00) to TIMESTAMP
    conn.execute("""
        CREATE MACRO gtfs_datetime(d, t) AS
            d + INTERVAL (CAST(SPLIT_PART(t, ':', 1) AS INT)) HOUR
              + INTERVAL (CAST(SPLIT_PART(t, ':', 2) AS INT)) MINUTE
              + INTERVAL (CAST(SPLIT_PART(t, ':', 3) AS INT)) SECOND;
    """)

    d = folder.replace("\\", "/")

    conn.execute(f"""
        CREATE TABLE stops_geo AS
        SELECT *, ST_Point(stop_lon, stop_lat) AS geom
        FROM read_csv('{d}/stops.txt', types={{
            'stop_lon': 'DOUBLE',
            'stop_lat': 'DOUBLE',
            'stop_id': 'VARCHAR',
            'stop_name': 'VARCHAR'
        }});
    """)

    # Optional GTFS columns — add if not present in the CSV
    conn.execute("ALTER TABLE stops_geo ADD COLUMN IF NOT EXISTS location_type INT;")
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

    if os.path.exists(os.path.join(folder, "calendar.txt")):
        conn.execute(f"""
            CREATE TABLE calendar AS
            SELECT * FROM read_csv('{d}/calendar.txt',
                types={{'start_date': 'VARCHAR', 'end_date': 'VARCHAR'}});
        """)
    else:
        conn.execute("""
            CREATE TABLE calendar (
                service_id VARCHAR,
                monday INT, tuesday INT, wednesday INT,
                thursday INT, friday INT, saturday INT, sunday INT,
                start_date VARCHAR, end_date VARCHAR
            );
        """)

    if os.path.exists(os.path.join(folder, "calendar_dates.txt")):
        conn.execute(f"""
            CREATE TABLE calendar_dates AS
            SELECT * FROM read_csv('{d}/calendar_dates.txt',
                types={{'date': 'VARCHAR'}});
        """)
    else:
        conn.execute("""
            CREATE TABLE calendar_dates (
                service_id VARCHAR,
                date VARCHAR,
                exception_type INT
            );
        """)

    if feedback:
        feedback.pushInfo("GTFS data loaded into DuckDB.")

    return GtfsConnection(conn=conn, has_shapes=has_shapes)
