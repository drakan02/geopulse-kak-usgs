"""CV2 database tools. Credentials come from PG* environment variables only."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time

import psycopg
from psycopg import sql
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = Path('/data/clean') if Path('/data').exists() else HERE.parent / 'data' / 'clean'
DEFAULT_REPORTS = Path('/reports') if Path('/reports').exists() else HERE / 'reports'
FILES = {
    'kak_clean': 'clean_intermagnet_KAK_1min_20230101_20260331.parquet',
    'usgs_clean': 'clean_usgs_JP_M4_20230101_20260331.parquet',
    'usgs_daily_clean': 'clean_usgs_JP_M4_daily_20230101_20260331.parquet',
}
KAK_COLS = ['time_utc', 'station', 'x_nt', 'y_nt', 'z_nt', 'f_nt',
            'flag_x', 'flag_y', 'flag_z', 'flag_f', 'quality_flag']
EVENT_COLS = ['event_id', 'time_utc', 'updated_utc', 'latitude', 'longitude',
              'depth_km', 'mag', 'mag_type', 'place', 'event_type', 'status', 'region',
              'nst', 'gap_deg', 'dmin_deg', 'rms', 'net', 'horizontal_error_km',
              'depth_error_km', 'mag_error', 'mag_nst', 'location_source', 'mag_source']
DAILY_COLS = ['date', 'n_events', 'n_events_japan', 'n_events_m5plus',
              'max_mag', 'dominant_magtype', 'mean_depth_km']
START = datetime(2023, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 4, 1, tzinfo=timezone.utc)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save_report(name, data, report_dir):
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f'{name}.json'
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    print(f'Report: {path}')


def file_paths(data_dir):
    paths = {kind: data_dir / name for kind, name in FILES.items()}
    for path in paths.values():
        require(path.is_file(), f'Missing input: {path}')
    return paths


def inspect_data(data_dir):
    """Read every input row, including flags and event/day reconciliation."""
    paths = file_paths(data_dir)
    result = {'checked_at': datetime.now(timezone.utc), 'files': {}, 'checks': []}
    for kind, path in paths.items():
        f = pq.ParquetFile(path)
        expected_cols = KAK_COLS if kind == 'kak_clean' else EVENT_COLS if kind == 'usgs_clean' else DAILY_COLS
        require(set(f.schema_arrow.names) == set(expected_cols), f'{path.name}: column mismatch')
        result['files'][kind] = {'filename': path.name, 'rows': f.metadata.num_rows,
            'sha256': sha256(path), 'bytes': path.stat().st_size,
            'columns': {field.name: str(field.type) for field in f.schema_arrow}}
    require(result['files']['kak_clean']['rows'] == 1707840, 'Expected 1,707,840 KAK timestamps')
    previous = None
    flags = Counter()
    channel_flags = {c: Counter() for c in 'XYZF'}
    for batch in pq.ParquetFile(paths['kak_clean']).iter_batches(batch_size=50000):
        t = pa.Table.from_batches([batch])
        stamps = t['time_utc']
        require(stamps.null_count == 0 and stamps.type.tz == 'UTC', 'KAK time must be non-null UTC')
        ints = stamps.cast(pa.int64()).combine_chunks()
        deltas = pc.pairwise_diff(ints)
        require(pc.all(pc.equal(deltas, 60_000_000)).as_py() is not False, 'KAK grid is not one minute')
        first, last = stamps[0].as_py(), stamps[-1].as_py()
        require(first == START if previous is None else first - previous == timedelta(minutes=1), 'KAK batch/grid boundary')
        previous = last
        require(set(t['station'].to_pylist()) == {'KAK'}, 'Unexpected station in this CV1 snapshot')
        require(t['quality_flag'].null_count == 0, 'Combined KAK quality flag must not be NULL')
        max_flag = pc.max_element_wise(*[t[f'flag_{c.lower()}'] for c in 'XYZF'])
        require(pc.all(pc.equal(max_flag, t['quality_flag'])).as_py(), 'Combined KAK flags do not match')
        for c in 'XYZF':
            fcol = t[f'flag_{c.lower()}']
            vals = t[f'{c.lower()}_nt']
            require(fcol.null_count == 0 and pc.all(pc.is_in(fcol, value_set=pa.array(range(6), type=pa.int8()))).as_py(), 'Invalid flag')
            bad = pc.or_(pc.is_nan(vals), pc.is_in(vals, value_set=pa.array([float('inf'), -float('inf')], type=pa.float32())))
            require(pc.any(bad).as_py() is not True, 'Use NULL, not NaN/infinity, for missing values')
            require(pc.any(pc.and_(pc.equal(fcol, 2), pc.is_valid(vals))).as_py() is not True, 'Flag 2 must be NULL')
            channel_flags[c].update(fcol.to_pylist())
        flags.update(t['quality_flag'].to_pylist())
    require(previous == END - timedelta(minutes=1), 'KAK end timestamp mismatch')
    events = pq.read_table(paths['usgs_clean']).to_pylist()
    ids = set()
    by_day = defaultdict(list)
    for event in events:
        require(event['event_id'] and event['event_id'] not in ids, 'Missing/duplicate earthquake ID')
        ids.add(event['event_id'])
        require(event['time_utc'] is not None and START <= event['time_utc'] < END, 'Event time outside scope')
        require(event['mag'] is not None and event['mag'] >= 4, 'Magnitude outside scope')
        require(24 <= event['latitude'] <= 46 and 122 <= event['longitude'] <= 150, 'Event outside bbox')
        by_day[event['time_utc'].date()].append(event)
    days = pq.read_table(paths['usgs_daily_clean']).to_pylist()
    require(len(days) == 1186, 'Expected 1,186 daily records')
    for index, row in enumerate(days):
        require(row['date'] == START + timedelta(days=index), 'Daily UTC grid mismatch')
        day_events = by_day[row['date'].date()]
        require(row['n_events'] == len(day_events), 'Daily event count mismatch')
        require(row['n_events_japan'] == sum(e['region'] == 'Japan' for e in day_events), 'Daily Japan count mismatch')
        require(row['n_events_m5plus'] == sum(e['mag'] >= 5 for e in day_events), 'Daily M5 count mismatch')
        if day_events:
            require(row['max_mag'] == max(e['mag'] for e in day_events), 'Daily max magnitude mismatch')
            depths = [e['depth_km'] for e in day_events if e['depth_km'] is not None]
            require(math.isclose(row['mean_depth_km'], statistics.mean(depths), rel_tol=2e-6, abs_tol=2e-5), 'Daily mean depth mismatch')
            modes = Counter(e['mag_type'] for e in day_events if e['mag_type'] is not None)
            require(modes[row['dominant_magtype']] == max(modes.values()), 'Daily dominant mag type mismatch')
        else:
            require(all(row[c] is None for c in ['max_mag', 'dominant_magtype', 'mean_depth_km']), 'Empty day must contain NULL statistics')
    result['kak_row_flags'] = dict(flags)
    result['kak_channel_flags'] = {c: dict(counts) for c, counts in channel_flags.items()}
    result['expected_measurements'] = 4 * result['files']['kak_clean']['rows']
    result['daily_totals'] = {c: sum(r[c] for r in days) for c in ['n_events', 'n_events_japan', 'n_events_m5plus']}
    require(len(events) == 4184 and result['daily_totals'] == {'n_events': 4184, 'n_events_japan': 3836, 'n_events_m5plus': 426}, 'CV1 snapshot totals changed')
    result['checks'] = ['all input rows checked', 'UTC and continuous grids', 'flags preserved',
                        'unique event IDs', 'event/day counts, magnitude and depth reconciled']
    return result


def connect():
    # libpq reads PGHOST, PGPORT, PGUSER, PGPASSWORD and PGDATABASE.
    return psycopg.connect(connect_timeout=10, options='-c timezone=UTC', autocommit=True)


def init_database(conn):
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(718642021)')
        present = conn.execute("SELECT to_regclass('raw.schema_version')").fetchone()[0]
        if present is None:
            conn.execute((HERE / 'sql/001_schema.sql').read_text(encoding='utf-8'), prepare=False)
        else:
            require(conn.execute('SELECT max(version) FROM raw.schema_version').fetchone()[0] == 1, 'Unsupported schema version')
    # Extension and continuous aggregate setup may be safely rerun.
    conn.execute((HERE / 'sql/002_timescale.sql').read_text(encoding='utf-8'), prepare=False)
    password = os.environ.get('PG_READER_PASSWORD')
    if password:
        with conn.transaction():
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname='geopulse_reader'").fetchone()
            verb = 'ALTER' if exists else 'CREATE'
            conn.execute(sql.SQL(verb + ' ROLE geopulse_reader LOGIN PASSWORD {}').format(sql.Literal(password)))
            conn.execute('GRANT USAGE ON SCHEMA clean, analytics TO geopulse_reader')
            conn.execute('GRANT SELECT ON ALL TABLES IN SCHEMA clean, analytics TO geopulse_reader')
            conn.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA clean, analytics GRANT SELECT ON TABLES TO geopulse_reader')
    print('Database schema v1 and TimescaleDB are ready.')


def copy_rows(conn, table, columns, rows):
    statement = sql.SQL('COPY {} ({}) FROM STDIN').format(
        sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, columns)))
    with conn.cursor().copy(statement) as copy:
        for row in rows:
            copy.write_row(row)


def iter_rows(path, columns, daily=False):
    for batch in pq.ParquetFile(path).iter_batches(batch_size=50000, columns=columns):
        # Column arrays are decoded from Arrow dictionaries before COPY.
        arrays = [batch.column(i).to_pylist() for i in range(batch.num_columns)]
        for row in zip(*arrays):
            if daily:
                row = (row[0].date(), *row[1:])
            yield row


def archive_file(conn, path, kind, stage, row_count=None):
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    existing = conn.execute('SELECT file_id FROM raw.file_archive WHERE source_kind=%s AND sha256=%s', (kind, digest)).fetchone()
    if existing:
        return existing[0]
    return conn.execute('''INSERT INTO raw.file_archive
        (source_kind, source_stage, filename, sha256, byte_size, row_count, content)
        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING file_id''',
        (kind, stage, path.name, digest, len(content), row_count, content)).fetchone()[0]


def stage_parquet(conn, path, kind):
    """Create a typed temporary staging table; persistent CV1 files are unchanged."""
    if kind == 'kak_clean':
        conn.execute('''CREATE TEMP TABLE stg_kak (
            time_utc timestamptz, station text, x_nt real, y_nt real, z_nt real, f_nt real,
            flag_x smallint, flag_y smallint, flag_z smallint, flag_f smallint, quality_flag smallint
        ) ON COMMIT DROP''')
        copy_rows(conn, 'stg_kak', KAK_COLS, iter_rows(path, KAK_COLS))
        return 'stg_kak'
    target = 'earthquake_event' if kind == 'usgs_clean' else 'earthquake_daily'
    columns = EVENT_COLS if kind == 'usgs_clean' else DAILY_COLS
    name = 'stg_' + target
    conn.execute(sql.SQL('CREATE TEMP TABLE {} (LIKE clean.{}) ON COMMIT DROP').format(sql.Identifier(name), sql.Identifier(target)))
    conn.execute(sql.SQL('ALTER TABLE {} DROP COLUMN batch_id').format(sql.Identifier(name)))
    copy_rows(conn, name, columns, iter_rows(path, columns, daily=kind == 'usgs_daily_clean'))
    return name


def import_clean(conn, data_dir, inspection):
    paths = file_paths(data_dir)
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(718642021)')
        for kind, path in paths.items():
            file_info = inspection['files'][kind]
            require(sha256(path) == file_info['sha256'], 'File changed after preflight')
            file_id = archive_file(conn, path, kind, 'clean_handoff', file_info['rows'])
            if conn.execute('SELECT 1 FROM raw.import_batch WHERE file_id=%s', (file_id,)).fetchone():
                print(f'Skip already imported snapshot: {path.name}')
                continue
            target = 'clean.measurement' if kind == 'kak_clean' else 'clean.earthquake_event' if kind == 'usgs_clean' else 'clean.earthquake_daily'
            expected_rows = file_info['rows'] * (4 if kind == 'kak_clean' else 1)
            batch_id = conn.execute('''INSERT INTO raw.import_batch (file_id,target_table,imported_rows)
                VALUES (%s,%s,%s) RETURNING batch_id''', (file_id, target, expected_rows)).fetchone()[0]
            start = time.perf_counter()
            name = stage_parquet(conn, path, kind)
            if kind == 'kak_clean':
                cursor = conn.execute('''INSERT INTO clean.measurement
                    (time_utc,station_code,channel_code,value,quality_flag,source_quality_flag,batch_id)
                    SELECT s.time_utc,s.station,c.channel,c.value,c.flag,s.quality_flag,%s
                    FROM stg_kak s CROSS JOIN LATERAL (VALUES
                        ('X',s.x_nt,s.flag_x),('Y',s.y_nt,s.flag_y),
                        ('Z',s.z_nt,s.flag_z),('F',s.f_nt,s.flag_f)) c(channel,value,flag)''', (batch_id,))
            else:
                columns = EVENT_COLS if kind == 'usgs_clean' else DAILY_COLS
                identifiers = sql.SQL(',').join(map(sql.Identifier, columns))
                cursor = conn.execute(sql.SQL('INSERT INTO {} ({},batch_id) SELECT {},%s FROM {}').format(
                    sql.Identifier(*target.split('.')), identifiers, identifiers, sql.Identifier(name)), (batch_id,))
            require(cursor.rowcount == expected_rows, 'Inserted row count mismatch')
            print(f'Imported {cursor.rowcount:,} rows from {path.name} in {time.perf_counter()-start:.2f}s')
        for target in ['clean.measurement', 'clean.earthquake_event', 'clean.earthquake_daily']:
            conn.execute(sql.SQL('ANALYZE {}').format(sql.Identifier(*target.split('.'))))


def refresh(conn):
    bounds = conn.execute('SELECT min(time_utc), max(time_utc) FROM clean.measurement').fetchone()
    require(bounds[0] is not None, 'Import measurements before refreshing aggregates')
    begin = bounds[0].replace(hour=0, minute=0, second=0, microsecond=0)
    end = bounds[1].replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    for view in ['analytics.measurement_hourly', 'analytics.measurement_daily']:
        conn.execute('CALL refresh_continuous_aggregate(%s::regclass,%s::timestamptz,%s::timestamptz)', (view, begin, end))
        print(f'Refreshed {view}: {begin.isoformat()} to {end.isoformat()}')


def verify(conn, data_dir, inspection, full=False):
    output = {'verified_at': datetime.now(timezone.utc), 'checks': [], 'counts': {}, 'full_roundtrip': full}
    expected = {'clean.measurement': inspection['expected_measurements'],
                'clean.earthquake_event': inspection['files']['usgs_clean']['rows'],
                'clean.earthquake_daily': inspection['files']['usgs_daily_clean']['rows']}
    for target, count in expected.items():
        actual = conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(*target.split('.')))).fetchone()[0]
        require(actual == count, f'{target}: expected {count}, got {actual}')
        output['counts'][target] = actual
    bounds = conn.execute('SELECT min(time_utc),max(time_utc) FROM clean.measurement').fetchone()
    require(bounds == (START, END - timedelta(minutes=1)), 'Database timestamp bounds differ')
    for channel in 'XYZF':
        distribution = dict(conn.execute('SELECT quality_flag,count(*) FROM clean.measurement WHERE channel_code=%s GROUP BY 1', (channel,)).fetchall())
        require(distribution == inspection['kak_channel_flags'][channel], f'{channel}: flag distribution mismatch')
    actual = conn.execute('SELECT sum(n_events),sum(n_events_japan),sum(n_events_m5plus) FROM clean.earthquake_daily').fetchone()
    require(actual == (4184,3836,426), 'Database daily totals differ')
    # Reconcile each day against the event catalog, preserving zero-event days.
    mismatch = conn.execute('''SELECT count(*) FROM clean.earthquake_daily d LEFT JOIN (
        SELECT (time_utc AT TIME ZONE 'UTC')::date AS date, count(*) AS n,
            count(*) FILTER (WHERE region='Japan') AS jp, count(*) FILTER (WHERE mag>=5) AS m5,
            max(mag) AS max_mag, avg(depth_km) AS mean_depth
        FROM clean.earthquake_event GROUP BY 1
    ) e USING(date) WHERE d.n_events<>coalesce(e.n,0) OR d.n_events_japan<>coalesce(e.jp,0)
       OR d.n_events_m5plus<>coalesce(e.m5,0) OR d.max_mag IS DISTINCT FROM e.max_mag
       OR abs(d.mean_depth_km-e.mean_depth)>greatest(0.00002,abs(e.mean_depth)*0.000002)''').fetchone()[0]
    require(mismatch == 0, 'Event/daily reconciliation failed in database')
    for view, rows in [('measurement_hourly',1186*24*4),('measurement_daily',1186*4)]:
        stats = conn.execute(sql.SQL('SELECT count(*),sum(n_total),sum(n_ok) FROM analytics.{}').format(sql.Identifier(view))).fetchone()
        require(stats == (rows,inspection['expected_measurements'],sum(v.get(0,0) for v in inspection['kak_channel_flags'].values())), f'{view}: aggregate conservation failed')
        output['counts']['analytics.'+view] = stats[0]
    # Compare every original value and all 11 columns, optionally, via typed staging.
    if full:
        with conn.transaction():
            paths = file_paths(data_dir)
            stage_parquet(conn, paths['kak_clean'], 'kak_clean')
            mismatch = conn.execute('''SELECT count(*) FROM stg_kak s CROSS JOIN LATERAL (VALUES
                ('X',s.x_nt,s.flag_x),('Y',s.y_nt,s.flag_y),('Z',s.z_nt,s.flag_z),('F',s.f_nt,s.flag_f)) c(channel,value,flag)
                LEFT JOIN clean.measurement m ON m.time_utc=s.time_utc AND m.station_code=s.station AND m.channel_code=c.channel
                WHERE m.time_utc IS NULL OR m.value IS DISTINCT FROM c.value
                   OR m.quality_flag IS DISTINCT FROM c.flag OR m.source_quality_flag IS DISTINCT FROM s.quality_flag''').fetchone()[0]
            require(mismatch == 0, 'KAK full roundtrip has mismatches')
            for kind, target, cols, key in [('usgs_clean','earthquake_event',EVENT_COLS,'event_id'),
                                           ('usgs_daily_clean','earthquake_daily',DAILY_COLS,'date')]:
                name = stage_parquet(conn, paths[kind], kind)
                conditions = sql.SQL(' OR ').join(sql.SQL('s.{} IS DISTINCT FROM d.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in cols)
                mismatch = conn.execute(sql.SQL('SELECT count(*) FROM {} s LEFT JOIN clean.{} d USING ({}) WHERE {}').format(
                    sql.Identifier(name),sql.Identifier(target),sql.Identifier(key),conditions)).fetchone()[0]
                require(mismatch == 0, f'{target}: full roundtrip mismatch')
        output['checks'].append('all Parquet values and flags roundtripped exactly')
    for kind, info in inspection['files'].items():
        archived = conn.execute('SELECT sha256,content FROM raw.file_archive WHERE source_kind=%s AND sha256=%s', (kind,info['sha256'])).fetchone()
        require(archived is not None and hashlib.sha256(archived[1]).hexdigest() == info['sha256'], 'Archive checksum mismatch')
    hypertables = [r[0] for r in conn.execute("SELECT hypertable_schema||'.'||hypertable_name FROM timescaledb_information.hypertables WHERE hypertable_schema IN ('clean','analytics') ORDER BY 1").fetchall()]
    require(all(t in hypertables for t in ['clean.measurement','analytics.filtered_series','analytics.forecast_result']), 'Missing Timescale hypertable')
    output['hypertables'] = hypertables
    output['original_raw_files'] = conn.execute("SELECT count(*) FROM raw.file_archive WHERE source_stage='original_raw'").fetchone()[0]
    output['checks'] += ['row counts and flags conserved', 'event/day reconciliation', 'continuous aggregates conserve counts', 'archive bytes and SHA256 preserved', 'Timescale hypertables exist']
    return output


def benchmark(conn, repeats):
    query = '''SELECT time_utc,value,quality_flag FROM clean.measurement
        WHERE station_code='KAK' AND channel_code='X'
        AND time_utc>='2024-01-01T00:00:00Z' AND time_utc<'2024-01-01T01:00:00Z' ORDER BY time_utc'''
    cases = {'planner_default': [], 'sequential_baseline': []}
    plans = {}
    for iteration in range(repeats + 1):
        for mode in (list(cases) if iteration % 2 == 0 else list(reversed(cases))):
            with conn.transaction():
                if mode == 'sequential_baseline':
                    conn.execute('SET LOCAL enable_indexscan=off; SET LOCAL enable_indexonlyscan=off; SET LOCAL enable_bitmapscan=off')
                doc = conn.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+query).fetchone()[0][0]
                if iteration:
                    cases[mode].append(doc['Execution Time'])
                plans[mode] = doc
    # Aggregate acceleration: both queries return the same hourly strict statistics.
    bounds = "station_code='KAK' AND channel_code='X' AND {column}>='2024-01-01T00:00:00Z' AND {column}<'2024-02-01T00:00:00Z'"
    raw_query = "SELECT time_bucket(interval '1 hour',time_utc) AS h,avg(value) FILTER (WHERE quality_flag=0) FROM clean.measurement WHERE " + bounds.format(column='time_utc') + ' GROUP BY 1 ORDER BY 1'
    agg_query = 'SELECT bucket_utc,mean_value FROM analytics.measurement_hourly WHERE ' + bounds.format(column='bucket_utc') + ' ORDER BY 1'
    raw_values, agg_values = conn.execute(raw_query).fetchall(), conn.execute(agg_query).fetchall()
    require(len(raw_values)==len(agg_values) and all(a[0]==b[0] and ((a[1] is None and b[1] is None) or (a[1] is not None and b[1] is not None and math.isclose(a[1],b[1],rel_tol=1e-10,abs_tol=1e-8))) for a,b in zip(raw_values,agg_values)), 'Aggregate benchmark results differ')
    for label, statement in [('raw_hourly_query',raw_query),('continuous_aggregate_query',agg_query)]:
        cases[label]=[]
        conn.execute('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+statement).fetchone()
        for _ in range(repeats):
            doc=conn.execute('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+statement).fetchone()[0][0]
            cases[label].append(doc['Execution Time'])
        plans[label]=doc
    return {'measured_at':datetime.now(timezone.utc),'server':conn.execute('SELECT version()').fetchone()[0],
        'timescaledb':conn.execute("SELECT extversion FROM pg_extension WHERE extname='timescaledb'").fetchone()[0],
        'repeats':repeats,'method':'warm cache, one warmup excluded; same hypertable/chunk pruning; planner switches are transaction-local; no index dropped',
        'results':{k:{'execution_ms':v,'median_ms':statistics.median(v)} for k,v in cases.items()},'plans':plans}


def archive_raw(conn, raw_dir):
    require(raw_dir.is_dir(), f'Missing raw directory: {raw_dir}')
    files = sorted(p for p in raw_dir.rglob('*') if p.is_file() and p.suffix.lower() in ('.csv','.json','.geojson','.txt'))
    require(files, 'No original raw files found; do not relabel clean Parquet files as raw')
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(718642021)')
        for path in files:
            parts = {p.lower() for p in path.relative_to(raw_dir).parts}
            kind = 'kak_raw' if 'intermagnet' in parts else 'usgs_raw' if 'usgs' in parts else None
            require(kind is not None, f'Put original raw files under intermagnet/ or usgs/: {path.name}')
            archive_file(conn,path,kind,'original_raw')
    print(f'Archived {len(files)} original files without modifying them.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--report-dir', type=Path, default=DEFAULT_REPORTS)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ['inspect','init','import','refresh','test']:
        sub.add_parser(command)
    verify_parser = sub.add_parser('verify')
    verify_parser.add_argument('--full', action='store_true', help='Compare every source value and flag against DB')
    benchmark_parser = sub.add_parser('benchmark')
    benchmark_parser.add_argument('--repeats', type=int, default=5)
    archive_parser = sub.add_parser('archive-raw')
    archive_parser.add_argument('--raw-dir', type=Path, default=Path('/data/raw'))
    args = parser.parse_args()
    started = time.perf_counter()
    if args.command == 'inspect':
        report = inspect_data(args.data_dir)
        save_report('input_inspection', report, args.report_dir)
        print(f'Inputs valid: {report["expected_measurements"]:,} measurements, 4,184 events, 1,186 days.')
        return
    if args.command == 'test':
        from integration_checks import main as test_contracts
        report = test_contracts()
        save_report('contract_checks',report,args.report_dir)
        return
    with connect() as conn:
        if args.command == 'init':
            init_database(conn)
        elif args.command == 'import':
            inspection = inspect_data(args.data_dir)
            init_database(conn)
            import_clean(conn,args.data_dir,inspection)
            refresh(conn)
            report = verify(conn,args.data_dir,inspection)
            save_report('verification',report,args.report_dir)
        elif args.command == 'refresh':
            refresh(conn)
        elif args.command == 'verify':
            report=verify(conn,args.data_dir,inspect_data(args.data_dir),args.full)
            save_report('verification_full' if args.full else 'verification',report,args.report_dir)
        elif args.command == 'benchmark':
            require(args.repeats>=1, 'Use at least one benchmark repetition')
            report=benchmark(conn,args.repeats)
            save_report('benchmark',report,args.report_dir)
            for mode,stats in report['results'].items():
                print(f'{mode}: median {stats["median_ms"]:.3f} ms')
        elif args.command == 'archive-raw':
            archive_raw(conn,args.raw_dir)
    print(f'Completed in {time.perf_counter()-started:.2f}s')


if __name__ == '__main__':
    try:
        main()
    except psycopg.Error as error:
        # Do not print connection strings or passwords from libpq exceptions.
        print(f'Database operation failed ({error.sqlstate or "connection"}). Check database status/PG* settings and schema constraints.', file=sys.stderr)
        if error.diag.message_primary and error.sqlstate:
            print(error.diag.message_primary, file=sys.stderr)
        sys.exit(1)
    except (ValueError, FileNotFoundError) as error:
        print(f'Check failed: {error}', file=sys.stderr)
        sys.exit(1)
