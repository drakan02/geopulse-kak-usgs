-- CV2 schema v1. UTC throughout. This file is applied once by cli.py init.
CREATE SCHEMA raw;
CREATE SCHEMA clean;
CREATE SCHEMA analytics;
CREATE TABLE raw.schema_version (
    version integer PRIMARY KEY,
    installed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE raw.file_archive (
    file_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_kind text NOT NULL CHECK (source_kind IN ('kak_clean', 'usgs_clean', 'usgs_daily_clean', 'kak_raw', 'usgs_raw')),
    source_stage text NOT NULL CHECK (source_stage IN ('original_raw', 'clean_handoff')),
    filename text NOT NULL,
    sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    row_count bigint CHECK (row_count >= 0),
    content bytea NOT NULL,
    archived_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (source_kind, sha256),
    CHECK (octet_length(content) = byte_size),
    CHECK ((source_stage = 'original_raw') = (source_kind IN ('kak_raw', 'usgs_raw')))
);
CREATE FUNCTION raw.prevent_archive_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'raw.file_archive is immutable; archive a new version instead';
END;
$$;
CREATE TRIGGER file_archive_immutable BEFORE UPDATE OR DELETE ON raw.file_archive
FOR EACH ROW EXECUTE FUNCTION raw.prevent_archive_mutation();
CREATE TABLE raw.import_batch (
    batch_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id bigint NOT NULL UNIQUE REFERENCES raw.file_archive(file_id),
    target_table text NOT NULL,
    imported_rows bigint NOT NULL CHECK (imported_rows >= 0),
    imported_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE clean.station (
    station_code text PRIMARY KEY,
    station_name text NOT NULL,
    country text NOT NULL,
    latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    elevation_m real,
    data_type text NOT NULL,
    source_dataset text NOT NULL
);
CREATE TABLE clean.channel (
    station_code text NOT NULL REFERENCES clean.station(station_code),
    channel_code text NOT NULL,
    description text NOT NULL,
    unit text NOT NULL,
    sample_interval interval NOT NULL CHECK (sample_interval > interval '0'),
    PRIMARY KEY (station_code, channel_code)
);
CREATE TABLE clean.quality_flag (
    flag smallint PRIMARY KEY CHECK (flag BETWEEN 0 AND 5),
    label text NOT NULL UNIQUE,
    description text NOT NULL
);
CREATE TABLE clean.measurement (
    time_utc timestamptz NOT NULL,
    station_code text NOT NULL,
    channel_code text NOT NULL,
    value real,
    quality_flag smallint NOT NULL REFERENCES clean.quality_flag(flag),
    source_quality_flag smallint NOT NULL REFERENCES clean.quality_flag(flag),
    batch_id bigint NOT NULL REFERENCES raw.import_batch(batch_id),
    PRIMARY KEY (station_code, channel_code, time_utc),
    FOREIGN KEY (station_code, channel_code) REFERENCES clean.channel(station_code, channel_code),
    CHECK (source_quality_flag >= quality_flag),
    CHECK (quality_flag <> 2 OR value IS NULL),
    CHECK (value NOT IN ('NaN'::real, 'Infinity'::real, '-Infinity'::real))
);
CREATE INDEX measurement_station_time_idx ON clean.measurement (station_code, time_utc DESC);
CREATE INDEX measurement_flagged_idx ON clean.measurement (station_code, channel_code, time_utc DESC)
WHERE quality_flag <> 0;
CREATE TABLE clean.earthquake_event (
    event_id text PRIMARY KEY,
    time_utc timestamptz NOT NULL,
    updated_utc timestamptz,
    latitude real NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude real NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    depth_km real,
    mag real NOT NULL,
    mag_type text,
    place text,
    event_type text,
    status text,
    region text,
    nst bigint,
    gap_deg bigint,
    dmin_deg double precision,
    rms double precision,
    net text,
    horizontal_error_km double precision,
    depth_error_km double precision,
    mag_error double precision,
    mag_nst bigint,
    location_source text,
    mag_source text,
    batch_id bigint NOT NULL REFERENCES raw.import_batch(batch_id)
);
CREATE INDEX earthquake_time_idx ON clean.earthquake_event (time_utc DESC);
CREATE INDEX earthquake_region_time_idx ON clean.earthquake_event (region, time_utc DESC);
CREATE TABLE clean.earthquake_daily (
    date date PRIMARY KEY,
    n_events integer NOT NULL CHECK (n_events >= 0),
    n_events_japan integer NOT NULL CHECK (n_events_japan BETWEEN 0 AND n_events),
    n_events_m5plus integer NOT NULL CHECK (n_events_m5plus BETWEEN 0 AND n_events),
    max_mag real,
    dominant_magtype text,
    mean_depth_km real,
    batch_id bigint NOT NULL REFERENCES raw.import_batch(batch_id),
    CHECK (n_events <> 0 OR (max_mag IS NULL AND dominant_magtype IS NULL AND mean_depth_km IS NULL))
);
CREATE TABLE analytics.model_run (
    run_id uuid PRIMARY KEY,
    station_code text NOT NULL,
    channel_code text NOT NULL,
    run_kind text NOT NULL CHECK (run_kind IN ('filter', 'forecast')),
    method text NOT NULL,
    input_series text NOT NULL,
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    train_start timestamptz,
    train_end timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (station_code, channel_code) REFERENCES clean.channel(station_code, channel_code),
    UNIQUE (run_id, station_code, channel_code, run_kind),
    CHECK (train_start IS NULL OR train_end IS NULL OR train_start <= train_end)
);
CREATE TABLE analytics.filtered_series (
    time_utc timestamptz NOT NULL,
    run_id uuid NOT NULL,
    station_code text NOT NULL,
    channel_code text NOT NULL,
    run_kind text NOT NULL DEFAULT 'filter' CHECK (run_kind = 'filter'),
    filtered_value real,
    quality_flag smallint NOT NULL REFERENCES clean.quality_flag(flag),
    PRIMARY KEY (run_id, time_utc),
    FOREIGN KEY (run_id, station_code, channel_code, run_kind)
        REFERENCES analytics.model_run(run_id, station_code, channel_code, run_kind)
);
CREATE INDEX filtered_series_station_time_idx ON analytics.filtered_series (station_code, channel_code, time_utc DESC);
CREATE TABLE analytics.forecast_result (
    target_time timestamptz NOT NULL,
    run_id uuid NOT NULL,
    station_code text NOT NULL,
    channel_code text NOT NULL,
    run_kind text NOT NULL DEFAULT 'forecast' CHECK (run_kind = 'forecast'),
    predicted_value real NOT NULL,
    lower_bound real,
    upper_bound real,
    PRIMARY KEY (run_id, target_time),
    FOREIGN KEY (run_id, station_code, channel_code, run_kind)
        REFERENCES analytics.model_run(run_id, station_code, channel_code, run_kind),
    CHECK (lower_bound IS NULL OR upper_bound IS NULL OR lower_bound <= upper_bound)
);
CREATE INDEX forecast_station_time_idx ON analytics.forecast_result (station_code, channel_code, target_time DESC);
INSERT INTO clean.station VALUES ('KAK', 'Kakioka', 'Japan', 36.232, 140.186, 36,
    'quasi-definitive', 'kak/quasi-def/PT1M/xyzf');
INSERT INTO clean.channel VALUES
    ('KAK', 'X', 'North component', 'nT', interval '1 minute'),
    ('KAK', 'Y', 'East component', 'nT', interval '1 minute'),
    ('KAK', 'Z', 'Vertical component, positive down', 'nT', interval '1 minute'),
    ('KAK', 'F', 'Total field intensity', 'nT', interval '1 minute');
INSERT INTO clean.quality_flag VALUES
    (0, 'OK', 'Original value without a QC flag'),
    (1, 'INTERPOLATED', 'Value interpolated by CV1'),
    (2, 'MISSING', 'Missing value or sentinel converted to NULL'),
    (3, 'SPIKE', 'Abrupt variation; original value is preserved'),
    (4, 'OUT_OF_RANGE', 'Outside physical bounds; original value is preserved'),
    (5, 'FLATLINE', 'Constant run; original value is preserved');
-- A compatibility view reconstructs all 11 CV1 columns without dropping timestamps.
CREATE VIEW clean.kak_1min AS
SELECT time_utc, station_code AS station,
    max(value) FILTER (WHERE channel_code = 'X') AS x_nt,
    max(value) FILTER (WHERE channel_code = 'Y') AS y_nt,
    max(value) FILTER (WHERE channel_code = 'Z') AS z_nt,
    max(value) FILTER (WHERE channel_code = 'F') AS f_nt,
    max(quality_flag) FILTER (WHERE channel_code = 'X') AS flag_x,
    max(quality_flag) FILTER (WHERE channel_code = 'Y') AS flag_y,
    max(quality_flag) FILTER (WHERE channel_code = 'Z') AS flag_z,
    max(quality_flag) FILTER (WHERE channel_code = 'F') AS flag_f,
    max(source_quality_flag) AS quality_flag
FROM clean.measurement GROUP BY time_utc, station_code;
CREATE VIEW analytics.vw_signal AS
SELECT m.time_utc, m.station_code, s.station_name, m.channel_code, c.unit,
    m.value AS original_value, m.quality_flag, m.source_quality_flag,
    q.label AS quality_label,
    CASE WHEN m.quality_flag = 0 THEN m.value END AS strict_value,
    CASE WHEN m.quality_flag IN (0, 3, 5) THEN m.value END AS cv1_display_value
FROM clean.measurement m
JOIN clean.station s USING (station_code)
JOIN clean.channel c USING (station_code, channel_code)
JOIN clean.quality_flag q ON q.flag = m.quality_flag;
CREATE VIEW analytics.vw_earthquake_events AS SELECT * FROM clean.earthquake_event;
CREATE VIEW analytics.vw_earthquake_daily AS SELECT * FROM clean.earthquake_daily;
CREATE VIEW analytics.vw_filtered_comparison AS
SELECT f.time_utc, f.station_code, f.channel_code, f.run_id, r.method,
    m.value AS original_value, m.quality_flag AS original_quality_flag,
    f.filtered_value, f.quality_flag AS filtered_quality_flag
FROM analytics.filtered_series f
JOIN analytics.model_run r USING (run_id)
LEFT JOIN clean.measurement m ON m.time_utc = f.time_utc
    AND m.station_code = f.station_code AND m.channel_code = f.channel_code;
CREATE VIEW analytics.vw_forecast AS
SELECT f.*, r.method, r.metrics, m.value AS actual_value
FROM analytics.forecast_result f
JOIN analytics.model_run r USING (run_id)
LEFT JOIN clean.measurement m ON m.time_utc = f.target_time
    AND m.station_code = f.station_code AND m.channel_code = f.channel_code;
INSERT INTO raw.schema_version(version) VALUES (1);
