-- ============================================================
-- Gợi ý cấu trúc bảng PostgreSQL cho 
-- Dựa trên schema thực tế: KAK quasi-def 1min, 2023-2026
-- Chưa tạo database – chỉ là gợi ý thiết kế
-- ============================================================

-- ── Bảng dim_station (dimension) ────────────────────────────
-- Lưu thông tin trạm một lần, tránh lặp trong fact table
CREATE TABLE IF NOT EXISTS dim_station (
    station_code   CHAR(3)        PRIMARY KEY,   -- Mã IAGA (KAK, PHU, ...)
    station_name   VARCHAR(100)   NOT NULL,
    country        VARCHAR(100),
    geodetic_lat   NUMERIC(8, 4),                -- Vĩ độ (độ thập phân)
    geodetic_lon   NUMERIC(9, 4),                -- Kinh độ
    elevation_m    NUMERIC(8, 2),                -- Cao độ (mét)
    data_type      VARCHAR(30)    NOT NULL,       -- 'quasi-definitive', 'definitive', ...
    hapi_dataset   VARCHAR(100),                 -- 'kak/quasi-def/PT1M/xyzf'
    notes          TEXT
);

-- Dữ liệu mẫu
INSERT INTO dim_station VALUES (
    'KAK', 'Kakioka', 'Japan',
    36.2320, 140.1860, 36.00,
    'quasi-definitive', 'kak/quasi-def/PT1M/xyzf',
    'Dữ liệu 2023-01-01 → 2026-03-31. Tháng 4/2026 chỉ 90% valid → không đưa vào.'
);


-- ── Bảng dim_quality_flag (dimension) ───────────────────────
CREATE TABLE IF NOT EXISTS dim_quality_flag (
    flag_code    SMALLINT    PRIMARY KEY,
    flag_name    VARCHAR(20) NOT NULL,
    description  TEXT        NOT NULL,
    is_usable    BOOLEAN     NOT NULL   -- TRUE nếu có thể dùng trong phân tích
);

INSERT INTO dim_quality_flag VALUES
    (0, 'OK',           'Giá trị gốc hợp lệ',                                TRUE),
    (1, 'INTERP',       'Giá trị nội suy tuyến tính (gap ngắn <= 5 phút)',     TRUE),
    (2, 'MISSING',      'Thiếu dữ liệu / Sentinel (NaN hoặc fill 99999.0)',   FALSE),
    (3, 'SPIKE',        'Biến thiên đột ngột (|diff| > 5σ); có thể là bão từ', TRUE),
    (4, 'OUT_OF_RANGE', 'Ngoài khoảng vật lý hợp lệ',                          FALSE),
    (5, 'FLATLINE',     'Chuỗi hằng số bất thường; chưa xác định nguyên nhân', FALSE);


-- ── Bảng fact_measurement (fact) ────────────────────────────
-- Lưu dữ liệu đo lường 1 phút
-- Partition by month giúp truy vấn chuỗi dài hiệu quả
CREATE TABLE IF NOT EXISTS fact_measurement (
    -- Khoá chính tự nhiên
    time_utc        TIMESTAMPTZ     NOT NULL,
    station_code    CHAR(3)         NOT NULL REFERENCES dim_station(station_code),

    -- Giá trị đo lường (nT)
    -- NULL = giá trị fill hoặc thiếu; xem flag tương ứng
    x_nt            REAL,
    y_nt            REAL,
    z_nt            REAL,
    f_nt            REAL,

    -- Cờ chất lượng từng thành phần (int2 = smallint để khớp int8 pandas)
    flag_x          SMALLINT        NOT NULL DEFAULT 0 CHECK (flag_x BETWEEN 0 AND 5),
    flag_y          SMALLINT        NOT NULL DEFAULT 0 CHECK (flag_y BETWEEN 0 AND 5),
    flag_z          SMALLINT        NOT NULL DEFAULT 0 CHECK (flag_z BETWEEN 0 AND 5),
    flag_f          SMALLINT        NOT NULL DEFAULT 0 CHECK (flag_f BETWEEN 0 AND 5),

    -- Cờ tổng hợp = GREATEST(flag_x, flag_y, flag_z, flag_f)
    quality_flag    SMALLINT        NOT NULL DEFAULT 0 CHECK (quality_flag BETWEEN 0 AND 5),

    PRIMARY KEY (time_utc, station_code)
)
PARTITION BY RANGE (time_utc);   -- Partition theo tháng / năm

-- Ví dụ tạo partition năm 2023
-- CREATE TABLE fact_measurement_2023
--     PARTITION OF fact_measurement
--     FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');


-- ── Index gợi ý ──────────────────────────────────────────────
-- Index chính cho truy vấn time-series
CREATE INDEX IF NOT EXISTS idx_fact_time_station
    ON fact_measurement (station_code, time_utc);

-- Index lọc theo quality_flag (Power BI thường lọc flag=0)
CREATE INDEX IF NOT EXISTS idx_fact_quality
    ON fact_measurement (quality_flag, time_utc);


-- ── View tiện dụng cho Power BI ─────────────────────────────
-- Đặt giá trị NULL ở cờ 1, 2, 4 nhưng GIỮ NGUYÊN MỌI DÒNG (bảo toàn lưới 1 phút)
CREATE OR REPLACE VIEW vw_measurement_analysis AS
SELECT
    f.time_utc,
    f.station_code,
    s.station_name,
    s.geodetic_lat,
    s.geodetic_lon,
    CASE WHEN f.flag_x IN (1, 2, 4) THEN NULL ELSE f.x_nt END AS x_nt,
    CASE WHEN f.flag_y IN (1, 2, 4) THEN NULL ELSE f.y_nt END AS y_nt,
    CASE WHEN f.flag_z IN (1, 2, 4) THEN NULL ELSE f.z_nt END AS z_nt,
    CASE WHEN f.flag_f IN (1, 2, 4) THEN NULL ELSE f.f_nt END AS f_nt,
    f.flag_x,
    f.flag_y,
    f.flag_z,
    f.flag_f,
    f.quality_flag,
    q.flag_name     AS quality_label,
    q.is_usable     AS is_usable
FROM fact_measurement       f
JOIN dim_station             s ON s.station_code = f.station_code
JOIN dim_quality_flag        q ON q.flag_code    = f.quality_flag;


-- ── Ghi chú nạp dữ liệu ─────────────────────────────────────
/*
Để nạp từ Parquet:
  1. Dùng pandas + SQLAlchemy:
       df.to_sql("fact_measurement", engine, if_exists="append",
                 index=False, chunksize=50_000, method="multi")
  2. Hoặc COPY từ CSV (nhanh hơn cho batch lớn):
       COPY fact_measurement FROM 'path/to/clean.csv' CSV HEADER;
  3. Với Power BI Direct Query: kết nối PostgreSQL, dùng vw_measurement_analysis.

Kiểm tra sau nạp:
  SELECT COUNT(*), MIN(time_utc), MAX(time_utc),
         COUNT(*) FILTER (WHERE quality_flag = 0) AS n_ok
  FROM fact_measurement WHERE station_code = 'KAK';
  -- Kỳ vọng: 1,707,840 dòng, 1,690,346 OK
*/
