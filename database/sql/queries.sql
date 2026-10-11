-- Queries for CV3. Replace literals with parameters in applications.
-- 1. Original and strict values for one channel; use half-open UTC intervals.
SELECT * FROM analytics.vw_signal
WHERE station_code = 'KAK' AND channel_code = 'X'
  AND time_utc >= '2024-01-01T00:00:00Z' AND time_utc < '2024-01-02T00:00:00Z'
ORDER BY time_utc;
-- 2. Hourly statistics from the continuous aggregate.
SELECT * FROM analytics.measurement_hourly
WHERE station_code = 'KAK' AND channel_code = 'X'
  AND bucket_utc >= '2024-01-01T00:00:00Z' AND bucket_utc < '2024-02-01T00:00:00Z'
ORDER BY bucket_utc;
-- 3. Monthly summary from daily buckets: weighted mean, not mean of means.
SELECT date_trunc('month', bucket_utc AT TIME ZONE 'UTC') AS month_utc,
    station_code, channel_code, sum(n_total) AS n_total, sum(n_ok) AS n_ok,
    sum(mean_value * n_ok) / nullif(sum(n_ok), 0) AS mean_value,
    min(min_value) AS min_value, max(max_value) AS max_value
FROM analytics.measurement_daily GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
-- 4. Rolling one-hour mean. Windows retain flagged timestamps as NULL.
SELECT time_utc, original_value, quality_flag,
    avg(strict_value) OVER (ORDER BY time_utc RANGE BETWEEN interval '59 minutes' PRECEDING AND CURRENT ROW) AS rolling_mean
FROM analytics.vw_signal
WHERE station_code = 'KAK' AND channel_code = 'X'
  AND time_utc >= '2024-01-01T00:00:00Z' AND time_utc < '2024-01-02T00:00:00Z'
ORDER BY time_utc;
-- 5. Daily geomagnetic context and earthquakes; a temporal join is not causation.
SELECT * FROM analytics.vw_daily_context
WHERE station_code = 'KAK' AND channel_code = 'F' ORDER BY bucket_utc;
