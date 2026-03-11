import { DuckDBConnection, DuckDBInstance } from '@duckdb/node-api';
import { TEMP_DIR, downloadAndExtract } from './download.js';
import { escapeUrl } from './escapeUrl.js';
import { existsSync } from 'fs';
import * as path from 'path';
import { createCache } from './cache.js';

type AggregateOptions = {
	maxDistance?: number;
	delimiter?: string;
};

const zipCache = createCache();

/** 正規表現のメタ文字をエスケープ */
function escapeRegex(s: string): string {
	return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** 停留所グルーピングのCTEを生成（getAggregatedStops / getAggregatedSegments 共通） */
function stopGroupingCte(options?: AggregateOptions): string {
	const delimiter = escapeRegex(options?.delimiter ?? '_');
	const maxDistance = Number(options?.maxDistance ?? 0.003);

	return `
    parent_station_groups AS (
      SELECT
        parent_station AS similar_stop_id,
        stop_id
      FROM stops_geo
      WHERE parent_station IS NOT NULL
        AND parent_station != ''
        AND EXISTS (SELECT 1 FROM stops_geo s2 WHERE s2.stop_id = stops_geo.parent_station)
        AND (location_type = 0 OR location_type IS NULL)
    ),

    solo_stops AS (
      SELECT *
      FROM stops_geo
      WHERE NOT EXISTS (
        SELECT 1 FROM parent_station_groups p WHERE p.stop_id = stops_geo.stop_id
      )
      AND (location_type = 0 OR location_type IS NULL)
    ),

    id_prefix_groups AS (
      SELECT
        REGEXP_EXTRACT(stop_id, '^([^${delimiter}]+)') AS similar_stop_id,
        stop_id
      FROM solo_stops
      WHERE REGEXP_EXTRACT(stop_id, '^([^${delimiter}]+)') != stop_id
    ),

    remaining_stops AS (
      SELECT *
      FROM solo_stops
      WHERE NOT EXISTS (
        SELECT 1 FROM id_prefix_groups ip WHERE ip.stop_id = solo_stops.stop_id
      )
    ),

    proximity_groups AS (
      SELECT
        a.stop_id AS stop_id,
        MIN(b.stop_id) AS similar_stop_id
      FROM remaining_stops a
      JOIN remaining_stops b ON a.stop_name = b.stop_name
      WHERE (POWER(a.stop_lon - b.stop_lon, 2) + POWER(a.stop_lat - b.stop_lat, 2)) <= POWER(${maxDistance}, 2)
      GROUP BY a.stop_id
    ),

    all_stop_relations AS (
      SELECT stop_id, similar_stop_id FROM parent_station_groups
      UNION ALL
      SELECT stop_id, similar_stop_id FROM id_prefix_groups
      UNION ALL
      SELECT stop_id, similar_stop_id FROM proximity_groups
    ),

    similar_stop_attributes AS (
      SELECT
        r.similar_stop_id,
        MIN(s.stop_name) AS similar_stop_name,
        AVG(s.stop_lon) AS stop_lon,
        AVG(s.stop_lat) AS stop_lat,
        COUNT(*) AS stop_count,
        ST_Point(AVG(s.stop_lon), AVG(s.stop_lat)) AS geom
      FROM all_stop_relations r
      JOIN stops_geo s ON r.stop_id = s.stop_id
      GROUP BY r.similar_stop_id
    )`;
}

type InitResult = {
	conn: DuckDBConnection;
	hasShapes: boolean;
};

async function initConnection(url: string): Promise<InitResult> {
	await downloadAndExtract(url, zipCache);

	const dir = `${TEMP_DIR}/${escapeUrl(url)}`;
	const instance = await DuckDBInstance.create(`${dir}/gtfs.duckdb`);
	const conn = await instance.connect();

	// Lambda環境ではHOMEが空のためDuckDBがホームディレクトリを見つけられない
	await conn.run(`SET home_directory='${dir}';`);

	const hasShapes = existsSync(path.resolve(dir, 'shapes.txt'));
	const shapesSql = hasShapes
		? `CREATE TABLE IF NOT EXISTS shapes AS
       SELECT * FROM read_csv('${dir}/shapes.txt');`
		: `CREATE TABLE IF NOT EXISTS shapes (
       shape_id VARCHAR, shape_pt_sequence INT,
       shape_pt_lon DOUBLE, shape_pt_lat DOUBLE);`;

	await conn.run(`
    INSTALL spatial;
    LOAD spatial;

    CREATE TABLE IF NOT EXISTS stops_geo AS
    SELECT *, ST_Point(stop_lon, stop_lat) AS geom
    FROM read_csv('${dir}/stops.txt', types={
      'stop_lon':'DOUBLE', 'stop_lat':'DOUBLE',
      'stop_id':'VARCHAR', 'stop_name':'VARCHAR',
      'location_type':'INT'
    });

    ALTER TABLE stops_geo ADD COLUMN IF NOT EXISTS parent_station VARCHAR;
    ALTER TABLE stops_geo ALTER COLUMN parent_station SET DATA TYPE VARCHAR;

    CREATE TABLE IF NOT EXISTS stop_times AS
      SELECT * FROM read_csv('${dir}/stop_times.txt',
        types={'arrival_time':'VARCHAR', 'departure_time':'VARCHAR'});

    CREATE TABLE IF NOT EXISTS trips AS
      SELECT * FROM read_csv('${dir}/trips.txt');

    CREATE TABLE IF NOT EXISTS routes AS
      SELECT * FROM read_csv('${dir}/routes.txt');

    ${shapesSql}
  `);

	return { conn, hasShapes };
}

const clients = new Map<string, DuckDbGtfsClient>();

class DuckDbGtfsClient {
	private init: Promise<InitResult>;

	constructor(url: string) {
		this.init = initConnection(url);
	}

	async getStops() {
		const { conn } = await this.init;
		const result = await conn.run(`
      SELECT
        json_object('type', 'FeatureCollection',
          'features', json_group_array(
            json_object(
              'type', 'Feature',
              'geometry', ST_AsGeoJSON(geom)::JSON,
              'properties', json_object(
                'stop_id', stop_id,
                'stop_name', stop_name
              )
            )
          )
        ) AS geojson
      FROM stops_geo;
    `);
		return (await result.getRows())[0]![0]! as string;
	}

	async getRoutes() {
		const { conn, hasShapes } = await this.init;

		if (!hasShapes) {
			const result = await conn.run(`
        WITH trip_lines AS (
          SELECT
            st.trip_id,
            ST_MakeLine(LIST(sg.geom ORDER BY st.stop_sequence)) AS geom
          FROM stop_times st
          JOIN stops_geo sg ON st.stop_id = sg.stop_id
          GROUP BY st.trip_id
        )
        SELECT
          json_object('type', 'FeatureCollection',
            'features', json_group_array(
              json_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(geom)::JSON,
                'properties', json_object('trip_id', trip_id)
              )
            )
          ) AS geojson
        FROM trip_lines;
      `);
			return (await result.getRows())[0]![0]! as string;
		}

		const result = await conn.run(`
      WITH shape_geom AS (
        SELECT
          shape_id,
          ST_MakeLine(LIST(ST_Point(shape_pt_lon, shape_pt_lat) ORDER BY shape_pt_sequence)) AS geom
        FROM shapes
        GROUP BY shape_id
      )
      SELECT
        json_object('type', 'FeatureCollection',
          'features', json_group_array(
            json_object(
              'type', 'Feature',
              'geometry', ST_AsGeoJSON(geom)::JSON,
              'properties', json_object('shape_id', shape_id)
            )
          )
        ) AS geojson
      FROM shape_geom;
    `);
		return (await result.getRows())[0]![0]! as string;
	}

	async getAggregatedStops(options?: AggregateOptions) {
		const { conn } = await this.init;
		const result = await conn.run(`
      WITH ${stopGroupingCte(options)},

      stop_trip_counts AS (
        SELECT stop_id, COUNT(*) AS trip_count
        FROM stop_times
        GROUP BY stop_id
      ),

      similar_stop_trip_counts AS (
        SELECT
          r.similar_stop_id,
          SUM(stc.trip_count) AS total_trip_count
        FROM all_stop_relations r
        JOIN stop_trip_counts stc ON r.stop_id = stc.stop_id
        GROUP BY r.similar_stop_id
      ),

      aggregated AS (
        SELECT
          a.similar_stop_id,
          a.similar_stop_name,
          a.stop_count,
          COALESCE(stc.total_trip_count, 0) AS trip_count,
          a.geom,
          LIST(r.stop_id) AS grouped_stop_ids
        FROM similar_stop_attributes a
        JOIN all_stop_relations r ON a.similar_stop_id = r.similar_stop_id
        LEFT JOIN similar_stop_trip_counts stc ON a.similar_stop_id = stc.similar_stop_id
        GROUP BY a.similar_stop_id, a.similar_stop_name, a.stop_count, stc.total_trip_count, a.geom
      )

      SELECT
        json_object('type', 'FeatureCollection',
          'features', json_group_array(
            json_object(
              'type', 'Feature',
              'geometry', ST_AsGeoJSON(geom)::JSON,
              'properties', json_object(
                'similar_stop_id', similar_stop_id,
                'similar_stop_name', similar_stop_name,
                'stop_count', stop_count,
                'trip_count', trip_count,
                'grouped_stop_ids', grouped_stop_ids
              )
            )
          )
        ) AS geojson
      FROM aggregated;
    `);
		return (await result.getRows())[0]![0]! as string;
	}

	async getAggregatedSegments(options?: AggregateOptions) {
		const { conn } = await this.init;
		const result = await conn.run(`
      WITH ${stopGroupingCte(options)},

      stop_times_with_similar AS (
        SELECT
          st.trip_id,
          st.stop_sequence,
          r.similar_stop_id
        FROM stop_times st
        JOIN all_stop_relations r ON st.stop_id = r.stop_id
      ),

      next_stops AS (
        SELECT
          trip_id,
          similar_stop_id AS from_similar_stop,
          LEAD(similar_stop_id) OVER (
            PARTITION BY trip_id ORDER BY stop_sequence
          ) AS to_similar_stop
        FROM stop_times_with_similar
      ),

      similar_edges AS (
        SELECT
          from_similar_stop,
          to_similar_stop,
          COUNT(*) AS trip_count
        FROM next_stops
        WHERE to_similar_stop IS NOT NULL
          AND from_similar_stop != to_similar_stop
        GROUP BY from_similar_stop, to_similar_stop
      ),

      trip_route_info AS (
        SELECT t.trip_id, r.route_id, r.route_short_name, r.route_long_name
        FROM trips t
        JOIN routes r ON t.route_id = r.route_id
      ),

      segment_routes AS (
        SELECT
          ns.from_similar_stop,
          ns.to_similar_stop,
          tri.route_id,
          MIN(tri.route_short_name) AS route_short_name,
          MIN(tri.route_long_name) AS route_long_name,
          COUNT(*) AS route_trip_count
        FROM next_stops ns
        JOIN trip_route_info tri ON ns.trip_id = tri.trip_id
        WHERE ns.to_similar_stop IS NOT NULL
          AND ns.from_similar_stop != ns.to_similar_stop
        GROUP BY ns.from_similar_stop, ns.to_similar_stop, tri.route_id
      ),

      segment_route_list AS (
        SELECT
          from_similar_stop,
          to_similar_stop,
          LIST(route_short_name) AS route_short_names,
          LIST(route_long_name) AS route_long_names,
          LIST(route_trip_count) AS route_trip_counts
        FROM segment_routes
        GROUP BY from_similar_stop, to_similar_stop
      ),

      similar_geometries AS (
        SELECT
          e.from_similar_stop,
          e.to_similar_stop,
          e.trip_count,
          srl.route_short_names,
          srl.route_long_names,
          srl.route_trip_counts,
          sf.similar_stop_name AS from_stop_name,
          st.similar_stop_name AS to_stop_name,
          ST_MakeLine([sf.geom, st.geom]) AS geom
        FROM similar_edges e
        JOIN similar_stop_attributes sf ON sf.similar_stop_id = e.from_similar_stop
        JOIN similar_stop_attributes st ON st.similar_stop_id = e.to_similar_stop
        LEFT JOIN segment_route_list srl
          ON e.from_similar_stop = srl.from_similar_stop
          AND e.to_similar_stop = srl.to_similar_stop
      )

      SELECT
        json_object('type', 'FeatureCollection',
          'features', json_group_array(
            json_object(
              'type', 'Feature',
              'geometry', ST_AsGeoJSON(geom)::JSON,
              'properties', json_object(
                'from_stop_id', from_similar_stop,
                'from_stop_name', from_stop_name,
                'to_stop_id', to_similar_stop,
                'to_stop_name', to_stop_name,
                'trip_count', trip_count,
                'route_short_names', route_short_names,
                'route_long_names', route_long_names,
                'route_trip_counts', route_trip_counts
              )
            )
          )
        ) AS geojson
      FROM similar_geometries;
    `);
		return (await result.getRows())[0]![0]! as string;
	}
}

async function getClient(url: string): Promise<DuckDbGtfsClient> {
	if (clients.has(url)) {
		return clients.get(url)!;
	}
	const client = new DuckDbGtfsClient(url);
	clients.set(url, client);
	return client;
}

export { getClient };
