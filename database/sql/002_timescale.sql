CREATE EXTENSION IF NOT EXISTS timescaledb;
SELECT create_hypertable('clean.measurement', by_range('time_utc', interval '1 month'), if_not_exists => true);
SELECT create_hypertable('analytics.filtered_series', by_range('time_utc', interval '1 month'), if_not_exists => true);
SELECT create_hypertable('analytics.forecast_result', by_range('target_time', interval '1 month'), if_not_exists => true);
-- Each bucket includes all timestamps. Statistical values use only flag 0.
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.measurement_hourly
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket(interval '1 hour', time_utc) AS bucket_utc, station_code, channel_code,
    count(*) AS n_total,
    count(*) FILTER (WHERE quality_flag = 0) AS n_ok,
    avg(value) FILTER (WHERE quality_flag = 0) AS mean_value,
    min(value) FILTER (WHERE quality_flag = 0) AS min_value,
    max(value) FILTER (WHERE quality_flag = 0) AS max_value,
    stddev_samp(value) FILTER (WHERE quality_flag = 0) AS stddev_value
FROM clean.measurement GROUP BY 1, 2, 3 WITH NO DATA;
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.measurement_daily
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket(interval '1 day', time_utc) AS bucket_utc, station_code, channel_code,
    count(*) AS n_total,
    count(*) FILTER (WHERE quality_flag = 0) AS n_ok,
    avg(value) FILTER (WHERE quality_flag = 0) AS mean_value,
    min(value) FILTER (WHERE quality_flag = 0) AS min_value,
    max(value) FILTER (WHERE quality_flag = 0) AS max_value,
    stddev_samp(value) FILTER (WHERE quality_flag = 0) AS stddev_value
FROM clean.measurement GROUP BY 1, 2, 3 WITH NO DATA;
-- Refresh archived history explicitly after importing it. No wall-clock policy:
-- a policy relative to today would miss most of this fixed 2023-2026 dataset.
CREATE OR REPLACE VIEW analytics.vw_daily_context AS
SELECT d.*, e.n_events, e.n_events_japan, e.n_events_m5plus, e.max_mag,
    e.dominant_magtype, e.mean_depth_km
FROM analytics.measurement_daily d
LEFT JOIN clean.earthquake_daily e ON e.date = (d.bucket_utc AT TIME ZONE 'UTC')::date;
