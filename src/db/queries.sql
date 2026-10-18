
-- Thống kê theo giờ
SELECT
    bucket_utc,
    station_code,
    channel_code,
    n_total,
    n_ok,
    mean_value,
    min_value,
    max_value,
    stddev_value
FROM analytics.measurement_hourly
WHERE station_code = 'KAK'
  AND channel_code = 'X'
  AND bucket_utc >= '2024-01-01T00:00:00Z'
  AND bucket_utc < '2024-02-01T00:00:00Z'
ORDER BY bucket_utc;


-- Thống kê theo ngày
SELECT
    bucket_utc,
    station_code,
    channel_code,
    n_total,
    n_ok,
    mean_value,
    min_value,
    max_value,
    stddev_value
FROM analytics.measurement_daily
WHERE station_code = 'KAK'
  AND channel_code = 'X'
  AND bucket_utc >= '2024-01-01T00:00:00Z'
  AND bucket_utc < '2024-02-01T00:00:00Z'
ORDER BY bucket_utc;


-- Tạo thống kê theo tháng
CREATE MATERIALIZED VIEW IF NOT EXISTS
analytics.measurement_monthly
WITH (
    timescaledb.continuous,
    timescaledb.materialized_only = true
)
AS
SELECT
    time_bucket(
        INTERVAL '1 month',
        time_utc
    ) AS bucket_utc,

    station_code,
    channel_code,

    COUNT(*) AS n_total,

    COUNT(*) FILTER (
        WHERE quality_flag = 0
    ) AS n_ok,

    AVG(value) FILTER (
        WHERE quality_flag = 0
    ) AS mean_value,

    MIN(value) FILTER (
        WHERE quality_flag = 0
    ) AS min_value,

    MAX(value) FILTER (
        WHERE quality_flag = 0
    ) AS max_value,

    STDDEV_SAMP(value) FILTER (
        WHERE quality_flag = 0
    ) AS stddev_value

FROM clean.measurement

GROUP BY
    1,
    2,
    3

WITH NO DATA;


-- Cập nhật dữ liệu thống kê tháng
CALL refresh_continuous_aggregate(
    'analytics.measurement_monthly',
    NULL,
    NULL
);


-- Xem thống kê theo tháng
SELECT
    bucket_utc,
    station_code,
    channel_code,
    n_total,
    n_ok,
    mean_value,
    min_value,
    max_value,
    stddev_value
FROM analytics.measurement_monthly
WHERE station_code = 'KAK'
ORDER BY
    bucket_utc,
    channel_code;


-- Rolling trong 60 phút
SELECT
    time_utc,
    station_code,
    channel_code,
    original_value,
    quality_flag,

    AVG(strict_value) OVER (
        PARTITION BY station_code, channel_code
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_mean_60m,

    MIN(strict_value) OVER (
        PARTITION BY station_code, channel_code
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_min_60m,

    MAX(strict_value) OVER (
        PARTITION BY station_code, channel_code
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_max_60m,

    STDDEV_SAMP(strict_value) OVER (
        PARTITION BY station_code, channel_code
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_std_60m

FROM analytics.vw_signal

WHERE station_code = 'KAK'
  AND channel_code = 'X'
  AND time_utc >= '2024-01-01T00:00:00Z'
  AND time_utc < '2024-01-02T00:00:00Z'

ORDER BY time_utc;


-- Rolling trong 6 giờ
SELECT
    time_utc,
    original_value,

    AVG(strict_value) OVER (
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '5 hours 59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_mean_6h,

    MIN(strict_value) OVER (
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '5 hours 59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_min_6h,

    MAX(strict_value) OVER (
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '5 hours 59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_max_6h,

    STDDEV_SAMP(strict_value) OVER (
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '5 hours 59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_std_6h

FROM analytics.vw_signal

WHERE station_code = 'KAK'
  AND channel_code = 'X'
  AND time_utc >= '2024-01-01T00:00:00Z'
  AND time_utc < '2024-01-02T00:00:00Z'

ORDER BY time_utc;


-- Rolling trong 24 giờ
SELECT
    time_utc,
    original_value,

    AVG(strict_value) OVER (
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '23 hours 59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_mean_24h,

    MIN(strict_value) OVER (
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '23 hours 59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_min_24h,

    MAX(strict_value) OVER (
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '23 hours 59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_max_24h,

    STDDEV_SAMP(strict_value) OVER (
        ORDER BY time_utc
        RANGE BETWEEN
            INTERVAL '23 hours 59 minutes' PRECEDING
            AND CURRENT ROW
    ) AS rolling_std_24h

FROM analytics.vw_signal

WHERE station_code = 'KAK'
  AND channel_code = 'X'
  AND time_utc >= '2024-01-01T00:00:00Z'
  AND time_utc < '2024-01-03T00:00:00Z'

ORDER BY time_utc;


-- So sánh các kênh X Y Z F
SELECT
    time_utc,

    MAX(original_value)
        FILTER (WHERE channel_code = 'X')
        AS x_value,

    MAX(original_value)
        FILTER (WHERE channel_code = 'Y')
        AS y_value,

    MAX(original_value)
        FILTER (WHERE channel_code = 'Z')
        AS z_value,

    MAX(original_value)
        FILTER (WHERE channel_code = 'F')
        AS f_value

FROM analytics.vw_signal

WHERE station_code = 'KAK'
  AND time_utc >= '2024-01-01T00:00:00Z'
  AND time_utc < '2024-01-02T00:00:00Z'

GROUP BY time_utc

ORDER BY time_utc;


-- Xem các lần chạy bộ lọc
SELECT
    run_id,
    station_code,
    channel_code,
    method,
    parameters,
    metrics,
    train_start,
    train_end,
    created_at

FROM analytics.model_run

WHERE run_kind = 'filter'

ORDER BY created_at DESC;


-- So sánh dữ liệu gốc và dữ liệu lọc
SELECT
    time_utc,
    run_id,
    method,
    original_value,
    filtered_value,

    original_value
        - filtered_value
        AS residual,

    ABS(
        original_value
        - filtered_value
    ) AS absolute_difference

FROM analytics.vw_filtered_comparison

WHERE station_code = 'KAK'
  AND channel_code = 'X'

ORDER BY
    run_id,
    time_utc;


-- Xem chỉ số của từng bộ lọc
SELECT
    run_id,
    method,
    station_code,
    channel_code,

    (metrics ->> 'rmse_change')::double precision
        AS rmse_change,

    (metrics ->> 'mae_change')::double precision
        AS mae_change,

    (metrics ->> 'diff_std_before')::double precision
        AS diff_std_before,

    (metrics ->> 'diff_std_after')::double precision
        AS diff_std_after,

    (metrics ->> 'correlation')::double precision
        AS correlation,

    train_start,
    train_end

FROM analytics.model_run

WHERE run_kind = 'filter'

ORDER BY
    train_start,
    method;


-- So sánh độ mượt sau khi lọc
SELECT
    method,

    (metrics ->> 'diff_std_before')::double precision
        AS diff_std_before,

    (metrics ->> 'diff_std_after')::double precision
        AS diff_std_after,

    (
        (metrics ->> 'diff_std_after')::double precision
        /
        NULLIF(
            (metrics ->> 'diff_std_before')::double precision,
            0
        )
    ) AS smoothing_ratio,

    (metrics ->> 'correlation')::double precision
        AS correlation,

    train_start,
    train_end

FROM analytics.model_run

WHERE run_kind = 'filter'

ORDER BY
    train_start,
    method;


-- Đếm số điểm dữ liệu sau khi lọc
SELECT
    r.run_id,
    r.method,
    r.station_code,
    r.channel_code,

    COUNT(f.time_utc)
        AS n_filtered_points,

    MIN(f.time_utc)
        AS start_time,

    MAX(f.time_utc)
        AS end_time

FROM analytics.model_run r

JOIN analytics.filtered_series f
    ON f.run_id = r.run_id

WHERE r.run_kind = 'filter'

GROUP BY
    r.run_id,
    r.method,
    r.station_code,
    r.channel_code

ORDER BY
    start_time,
    r.method;
