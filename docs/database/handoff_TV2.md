# Handoff TV2 


## 1. Tổng quan bàn giao

Ba bảng dữ liệu đã làm sạch, sẵn sàng nạp vào PostgreSQL hoặc dùng trực tiếp:

| Bảng | File | Dòng | Kích thước |
|---|---|---|---|
| **fact_kak_1min** | `clean_intermagnet_KAK_1min_20230101_20260331.parquet` | 1,707,840 | 20.9 MB |
| **fact_usgs_event** | `clean_usgs_JP_M4_20230101_20260331.parquet` | 4,184 | 0.27 MB |
| **fact_usgs_daily** | `clean_usgs_JP_M4_daily_20230101_20260331.parquet` | 1,186 | 23.2 KB |

Tất cả file trong thư mục `data/clean/`.

---

## 2. Bảng 1 – KAK 1 phút (fact_kak_1min)

**Nguồn:** INTERMAGNET HAPI / BGS (`kak/quasi-def/PT1M/xyzf`)  
**Trạm:** KAK (Kakioka, Nhật Bản, 36.23°N 140.19°E)  
**Khoảng:** 2023-01-01T00:00Z → 2026-03-31T23:59Z  
**SHA-256:** `b1c73b49cab713ebeb5a8de3366f761fe07ddb6d8cca6ded4440acb6dbdbc11f`

> ⚠️ **LƯU Ý QUAN TRỌNG VỀ LƯỚI THỜI GIAN:**
> Phải **GIỮ ĐỦ 1,707,840 DÒNG**, **KHÔNG ĐƯỢC LỌC/XOÁ DÒNG** (chuỗi thời gian địa từ yêu cầu lưới thời gian 1 phút đều đặn). 

### Schema

| Cột | Kiểu | Đơn vị | Mô tả |
|---|---|---|---|
| `time_utc` | datetime64[us, UTC] | – | Dấu thời gian UTC đầu phút |
| `station` | category | – | Mã IAGA 3 ký tự (`KAK`) |
| `x_nt` | float32 | nT | Thành phần X (Bắc) |
| `y_nt` | float32 | nT | Thành phần Y (Đông) |
| `z_nt` | float32 | nT | Thành phần Z (Thẳng đứng xuống) |
| `f_nt` | float32 | nT | Cường độ toàn phần F |
| `flag_x` | int8 | – | Cờ chất lượng riêng x_nt |
| `flag_y` | int8 | – | Cờ chất lượng riêng y_nt |
| `flag_z` | int8 | – | Cờ chất lượng riêng z_nt |
| `flag_f` | int8 | – | Cờ chất lượng riêng f_nt |
| `quality_flag` | int8 | – | Tổng hợp = max(flag_x, flag_y, flag_z, flag_f) |

### Bảng mã quality_flag (đồng bộ SOP-01)

| Mã | Tên | Điều kiện | Trạng thái trong dataset KAK |
|---|---|---|---|
| `0` | OK | Giá trị gốc hợp lệ | 1,690,346 điểm (98.98%) – ✅ Sử dụng trực tiếp |
| `1` | INTERP | Giá trị nội suy (gap ≤ 5 phút) | **0 điểm** (không có gap ngắn) |
| `2` | MISSING | Thiếu dữ liệu / Fill 99999 | **0 điểm** (không có missing/sentinel) |
| `3` | SPIKE | \|diff\| > 5σ | 15,082 điểm (0.88%) – **GIỮ NGUYÊN DÒNG** |
| `4` | OUT_OF_RANGE | Ngoài khoảng vật lý | **0 điểm** |
| `5` | FLATLINE | ≥ 10 điểm cùng giá trị | 2,412 điểm (0.14%) – **GIỮ NGUYÊN DÒNG** |

> **Thứ tự ưu tiên cờ:** flatline (5) > out-of-range (4) > spike (3) > missing/sentinel (2) > interp (1) > OK (0)  
> `quality_flag = max(flag_x, flag_y, flag_z, flag_f)`

### ⚠️ Cảnh báo quan trọng

- **Giữ nguyên 100% số dòng dữ liệu (1,707,840 dòng):** Không xóa bất kỳ dòng nào để đảm bảo tính liên tục của lưới thời gian 1 phút.
- **Spike (cờ 3) KHÔNG bị xoá.** Một phần có thể là biến thiên địa từ thật trong bão từ địa vật lý. Cần phân tích trước khi quyết định xử lý.
- **Flatline (cờ 5)** tập trung ở z_nt (2,048 điểm). Chưa xác định nguyên nhân, cần kiểm tra trước khi dùng.
- Chuỗi **hoàn toàn không có gap** (0 NaN sau reindex trong dữ liệu gốc KAK quasi-def).

---

## 3. Bảng 2 – USGS Earthquake Events (fact_usgs_event)

**Nguồn:** USGS FDSN Event Web Service  
**Vùng:** lat 24–46°N, lon 122–150°E (Nhật Bản & lân cận)  
**Khoảng:** 2023-01-01T00:00Z → 2026-03-31 (query đến 2026-04-01T00:00Z)  
**SHA-256:** `a02c8d5b326c585c3e0655626b0f3955cab9987ea69773b0452759274d28c712`

### Schema (Đầy đủ 23 cột đối chiếu 1:1 với file Parquet)

| Cột | Kiểu Parquet | Kiểu SQL gợi ý | Đơn vị | Mô tả & Giá trị |
|---|---|---|---|---|
| `event_id` | str | TEXT / VARCHAR(50) | – | ID USGS duy nhất (PK) |
| `time_utc` | datetime64[us, UTC] | TIMESTAMPTZ | – | Thời điểm sự kiện (UTC) |
| `updated_utc` | datetime64[us, UTC] | TIMESTAMPTZ | – | Thời điểm cập nhật cuối |
| `latitude` | float32 | REAL | °N | Vĩ độ (min=24.00, max=45.92) |
| `longitude` | float32 | REAL | °E | Kinh độ (min=122.01, max=149.93) |
| `depth_km` | float32 | REAL | km | Độ sâu (min=2.29, max=644.88) |
| `mag` | float32 | REAL | – | Độ lớn (min=4.0, max=7.6) |
| `mag_type` | category | VARCHAR(10) | – | Thang đo (mb/mww/mwr/mwb) |
| `place` | str | TEXT | – | Mô tả vị trí từ USGS |
| `event_type` | category | VARCHAR(20) | – | Loại sự kiện (luôn = `earthquake`) |
| `status` | category | VARCHAR(20) | – | Trạng thái (luôn = `reviewed`) |
| `region` | category | VARCHAR(20) | – | Phân vùng gần đúng từ place |
| `nst` | int64 | INTEGER | – | Số trạm định vị (min=8, max=619) |
| `gap_deg` | int64 | INTEGER | ° | Góc azimuth trạm (min=9, max=249) |
| `dmin_deg` | float64 | REAL | ° | Khoảng cách trạm gần nhất (min=0.065, max=44.036) |
| `rms` | float64 | REAL | s | RMS residual (min=0.19, max=1.44) |
| `net` | str | VARCHAR(10) | – | Mạng lưới báo cáo (ví dụ: `us`) |
| `horizontal_error_km` | float64 | REAL | km | Sai số ngang (min=1.03, max=19.8) |
| `depth_error_km` | float64 | REAL | km | Sai số độ sâu (min=0.814, max=25.32) |
| `mag_error` | float64 | REAL | – | Sai số magnitude (min=0.019, max=0.37) |
| `mag_nst` | int64 | INTEGER | – | Số trạm tính magnitude (min=2, max=884) |
| `location_source` | str | VARCHAR(10) | – | Nguồn định vị |
| `mag_source` | str | VARCHAR(10) | – | Nguồn magnitude |

### Bảng mã region (gần đúng)

| Mã | Số SĐ | % | Điều kiện từ place |
|---|---|---|---|
| `Japan` | 3,836 | 91.68% | japan / ryukyu / izu / bonin / noto / aomori / … |
| `Kuril-Russia` | 302 | 7.22% | kuril / kamchatka / russia / sakhalin |
| `Taiwan` | 38 | 0.91% | taiwan |
| `other` | 8 | 0.19% | không khớp |

### ⚠️ Cảnh báo quan trọng

- **magType trộn:** mb (85.9%), mww (10.4%), mwr (3.7%), mwb (0.02%). **mb ≠ Mw** về năng lượng — không so sánh tuyệt đối `max_mag` giữa các ngày có `dominant_magtype` khác nhau.
- **region là phân loại gần đúng** từ văn bản tự do. Không dùng cho phân tích địa lý chính xác.
- **8.32% ngoài Nhật Bản** (Kamchatka 7.2%, Taiwan 0.9%). Dùng cột `region` để lọc.
- **Catalog USGS có thể cập nhật** magnitude sau khi sự kiện xảy ra. File phản ánh trạng thái ngày tải (2026-10-05).
- **Dư chấn không bị xoá:** 2024-01-01 (64 SĐ sau Noto M7.5), 2025-11-09 (50 SĐ), 2025-12-08 (23 SĐ, Aomori M7.6).

---

## 4. Bảng 3 – USGS Daily Summary (fact_usgs_daily)

**SHA-256:** `2b2ef30842604d5817887dc969532c9f4687b39dd5db6ecee860d4d4bc149e22`

### Schema

| Cột | Kiểu | Đơn vị | Mô tả | Ngày trống |
|---|---|---|---|---|
| `date` | datetime64[us, UTC] | – | Ngày UTC (00:00Z) | – |
| `n_events` | int32 | – | Số sự kiện M≥4.0 | `0` |
| `n_events_japan` | int32 | – | Sự kiện region=Japan | `0` |
| `n_events_m5plus` | int32 | – | Sự kiện M≥5.0 | `0` |
| `max_mag` | float32 | – | Magnitude lớn nhất | `NULL` |
| `dominant_magtype` | object | – | magType phổ biến nhất (mode) | `NULL` |
| `mean_depth_km` | float32 | km | Độ sâu trung bình | `NULL` |

### Kiểm chứng (assert đã chạy)

| Assert | Kết quả |
|---|---|
| Số ngày lưới = 1,186 | ✅ |
| Ngày liên tục, không gap | ✅ |
| sum(n_events) = 4,184 | ✅ |
| sum(n_events_japan) = 3,836 | ✅ |
| sum(n_events_m5plus) = 426 | ✅ |
| 86 ngày trống: max_mag / dominant_magtype / mean_depth_km = NULL | ✅ |

### Thống kê nhanh

| | Giá trị |
|---|---|
| Ngày có sự kiện | 1,100 / 1,186 |
| Ngày 0 sự kiện | 86 |
| Ngày nhiều nhất | 64 SĐ (2024-01-01, Noto M7.5) |
| Ngày M7.6 (Aomori) | 2025-12-08, n=23, xếp hạng #9 |

---

## 5. Gợi ý PostgreSQL DDL

```sql
-- ══════════════════════════════════════════════════════════════
-- Bảng 1: KAK 1 phút
-- ══════════════════════════════════════════════════════════════
CREATE TABLE fact_kak_1min (
    time_utc        TIMESTAMPTZ NOT NULL,
    station         CHAR(3)     NOT NULL DEFAULT 'KAK',
    x_nt            REAL,
    y_nt            REAL,
    z_nt            REAL,
    f_nt            REAL,
    flag_x          SMALLINT    NOT NULL DEFAULT 0,
    flag_y          SMALLINT    NOT NULL DEFAULT 0,
    flag_z          SMALLINT    NOT NULL DEFAULT 0,
    flag_f          SMALLINT    NOT NULL DEFAULT 0,
    quality_flag    SMALLINT    NOT NULL DEFAULT 0,
    PRIMARY KEY (time_utc, station)
) PARTITION BY RANGE (time_utc);

-- Partition theo năm
CREATE TABLE fact_kak_1min_2023 PARTITION OF fact_kak_1min
    FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
CREATE TABLE fact_kak_1min_2024 PARTITION OF fact_kak_1min
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE fact_kak_1min_2025 PARTITION OF fact_kak_1min
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE fact_kak_1min_2026 PARTITION OF fact_kak_1min
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

-- Index hỗ trợ query theo cờ khác 0 (Lưu ý: PRIMARY KEY đã tự động tạo index trên (time_utc, station))
CREATE INDEX ON fact_kak_1min (quality_flag) WHERE quality_flag > 0;

-- View tiện dùng: Đặt giá trị NULL chỉ ở các cờ 1, 2, 4 nhưng GIỮ NGUYÊN MỌI DÒNG (bảo toàn lưới 1 phút)
CREATE OR REPLACE VIEW vw_kak_cleaned_signal AS
SELECT
    time_utc,
    station,
    CASE WHEN flag_x IN (1, 2, 4) THEN NULL ELSE x_nt END AS x_nt,
    CASE WHEN flag_y IN (1, 2, 4) THEN NULL ELSE y_nt END AS y_nt,
    CASE WHEN flag_z IN (1, 2, 4) THEN NULL ELSE z_nt END AS z_nt,
    CASE WHEN flag_f IN (1, 2, 4) THEN NULL ELSE f_nt END AS f_nt,
    flag_x,
    flag_y,
    flag_z,
    flag_f,
    quality_flag
FROM fact_kak_1min;


-- ══════════════════════════════════════════════════════════════
-- Bảng 2: USGS events (Đầy đủ 23 cột khớp Parquet)
-- ══════════════════════════════════════════════════════════════
CREATE TABLE fact_usgs_event (
    event_id            TEXT        PRIMARY KEY,
    time_utc            TIMESTAMPTZ NOT NULL,
    updated_utc         TIMESTAMPTZ,
    latitude            REAL        NOT NULL,
    longitude           REAL        NOT NULL,
    depth_km            REAL,
    mag                 REAL        NOT NULL,
    mag_type            VARCHAR(10),
    place               TEXT,
    event_type          VARCHAR(20),
    status              VARCHAR(20),
    region              VARCHAR(20),     -- Japan / Kuril-Russia / Taiwan / other
    nst                 INTEGER,         -- Phù hợp dữ liệu min=8, max=619
    gap_deg             INTEGER,         -- Phù hợp dữ liệu min=9, max=249
    dmin_deg            REAL,            -- Min=0.065, max=44.036
    rms                 REAL,
    net                 VARCHAR(10),
    horizontal_error_km REAL,
    depth_error_km      REAL,
    mag_error           REAL,
    mag_nst             INTEGER,
    location_source     VARCHAR(10),
    mag_source          VARCHAR(10)
);

CREATE INDEX ON fact_usgs_event (time_utc);
CREATE INDEX ON fact_usgs_event (mag);
CREATE INDEX ON fact_usgs_event (region);

-- ══════════════════════════════════════════════════════════════
-- Bảng 3: USGS daily summary
-- ══════════════════════════════════════════════════════════════
CREATE TABLE fact_usgs_daily (
    date                DATE        PRIMARY KEY,
    n_events            INTEGER     NOT NULL DEFAULT 0,
    n_events_japan      INTEGER     NOT NULL DEFAULT 0,
    n_events_m5plus     INTEGER     NOT NULL DEFAULT 0,
    max_mag             REAL,                -- NULL nếu không có sự kiện
    dominant_magtype    VARCHAR(10),         -- NULL nếu không có sự kiện
    mean_depth_km       REAL                 -- NULL nếu không có sự kiện
);

-- ══════════════════════════════════════════════════════════════
-- Bảng dimension tham khảo (đồng bộ SOP-01)
-- ══════════════════════════════════════════════════════════════
CREATE TABLE dim_quality_flag (
    code        SMALLINT PRIMARY KEY,
    name        VARCHAR(20),
    description TEXT,
    is_usable   BOOLEAN
);
INSERT INTO dim_quality_flag VALUES
    (0, 'OK',          'Giá trị gốc hợp lệ',                                TRUE),
    (1, 'INTERP',      'Giá trị nội suy tuyến tính (gap ngắn <= 5 phút)',     TRUE),
    (2, 'MISSING',     'Thiếu dữ liệu / Sentinel (NaN hoặc fill 99999.0)',   FALSE),
    (3, 'SPIKE',       'Biến thiên đột ngột (|diff| > 5σ); có thể là bão từ', TRUE),
    (4, 'OUT_OF_RANGE','Ngoài khoảng vật lý hợp lệ',                          FALSE),
    (5, 'FLATLINE',    'Chuỗi hằng số bất thường; chưa xác định nguyên nhân', FALSE);

CREATE TABLE dim_region (
    region      VARCHAR(20) PRIMARY KEY,
    description TEXT,
    note        TEXT
);
INSERT INTO dim_region VALUES
    ('Japan',        'Nhật Bản (bao gồm Ryukyu, Izu, Bonin)', 'Phân loại gần đúng từ place'),
    ('Kuril-Russia', 'Quần đảo Kuril / Kamchatka (Nga)',       'Phân loại gần đúng từ place'),
    ('Taiwan',       'Đài Loan',                               'Phân loại gần đúng từ place'),
    ('other',        'Vùng khác',                              'Phân loại gần đúng từ place');
```

---

## 6. Cách đọc file Parquet (Python)

```python
import pandas as pd

# 1. KAK 1 phút: Giữ NGUYÊN 1,707,840 dòng (KHÔNG dùng drop/lọc dòng để đảm bảo lưới thời gian đều 1 phút)
kak = pd.read_parquet("data/clean/clean_intermagnet_KAK_1min_20230101_20260331.parquet")

# Ví dụ khi cần thay thế các điểm lỗi (cờ 1, 2, 4) bằng NaN mà vẫn giữ đủ 1,707,840 dòng:
# mask_bad = kak["quality_flag"].isin([1, 2, 4])
# kak.loc[mask_bad, ["x_nt", "y_nt", "z_nt", "f_nt"]] = None

# 2. USGS events (4,184 sự kiện)
usgs = pd.read_parquet("data/clean/clean_usgs_JP_M4_20230101_20260331.parquet")
usgs_japan = usgs[usgs["region"] == "Japan"]

# 3. Daily summary (1,186 ngày)
daily = pd.read_parquet("data/clean/clean_usgs_JP_M4_daily_20230101_20260331.parquet")
```

---

## 7. Phương án chia sẻ file Parquet

**Quyết định chia sẻ:** Toàn bộ 3 file Parquet làm sạch được lưu trực tiếp trong thư mục `data/clean/` và commit lên kho chứa Git (tổng dung lượng ~21.2 MB, nằm dưới ngưỡng giới hạn 100 MB của GitHub).

Chỉ cần thực hiện `git pull` để nhận toàn bộ file dữ liệu sạch mà không cần cài đặt thêm công cụ lưu trữ bên ngoài.

---

## 8. Lưu ý cho Database

1. **Cột region** là phân loại gần đúng — không dùng làm khoá nghiệp vụ chính xác.
2. **Spike KAK (cờ 3)** có thể là biến thiên địa từ thật — **không xoá** khi nạp DB.
3. **Flatline KAK (cờ 5)** tập trung ở z_nt — chưa xác định nguyên nhân, cần kiểm tra trước khi dùng trong mô hình.
4. **Ngày đột biến USGS** (2024-01-01: 64 SĐ) là dữ liệu thật do chuỗi dư chấn — không lọc.
5. **dominant_magtype và max_mag** trong daily summary trộn mb + Mw — ghi chú này vào tooltip Power BI.
6. Khi nạp vào PostgreSQL, giữ nguyên kiểu `TIMESTAMPTZ` và **không chuyển về giờ địa phương**.

---
