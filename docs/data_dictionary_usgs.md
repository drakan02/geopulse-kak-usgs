# Data Dictionary – USGS Earthquake Catalog

> Tạo tự động bởi `clean_catalog.py`. Cập nhật khi schema thay đổi.

## File sản phẩm

`data/clean/clean_usgs_JP_M4_20230101_20260331.parquet`

## Schema cột

| Cột | Kiểu | Đơn vị | Mô tả |
|---|---|---|---|
| `event_id` | `object` | – | ID sự kiện USGS (ví dụ: `us7000lz5b`) |
| `time_utc` | `datetime64[us, UTC]` | – | Thời điểm sự kiện (UTC) |
| `updated_utc` | `datetime64[us, UTC]` | – | Lần cập nhật cuối (UTC); dùng để dedup |
| `latitude` | `float32` | °N | Vĩ độ tâm chấn |
| `longitude` | `float32` | °E | Kinh độ tâm chấn |
| `depth_km` | `float32` | km | Độ sâu |
| `mag` | `float32` | – | Độ lớn (thang đo xem `mag_type`) |
| `mag_type` | `category` | – | Loại thang đo: mb, mww, mwr, mwb |
| `place` | `object` | – | Mô tả vị trí từ USGS (văn bản tự do) |
| `event_type` | `category` | – | Luôn = `earthquake` (đã lọc khi tải) |
| `status` | `category` | – | `reviewed` = đã xem xét thủ công |
| `region` | `category` | – | Phân vùng gần đúng từ `place` (xem ghi chú) |
| `nst` | `float64` | – | Số trạm dùng để định vị |
| `gap_deg` | `float64` | ° | Góc azimuth lớn nhất giữa 2 trạm liền kề |
| `dmin_deg` | `float64` | ° | Khoảng cách tới trạm gần nhất |
| `rms` | `float64` | s | Root-mean-square residual |
| `net` | `object` | – | Mạng lưới trạm chính |
| `horizontal_error_km` | `float64` | km | Sai số ngang |
| `depth_error_km` | `float64` | km | Sai số độ sâu |
| `mag_error` | `float64` | – | Sai số magnitude |
| `mag_nst` | `float64` | – | Số trạm dùng tính magnitude |
| `location_source` | `object` | – | Nguồn định vị |
| `mag_source` | `object` | – | Nguồn tính magnitude |

## Bảng mã region

> ⚠️ **Ghi chú:** `region` là phân loại **gần đúng** dựa trên khớp chuỗi trong trường `place`
> (văn bản tự do của USGS). Có thể sai với một số sự kiện biên giới địa lý.
> Không dùng cho phân tích địa lý chính xác.

| Mã | Điều kiện |
|---|---|
| `Japan` | place chứa: japan, ryukyu, izu, bonin, okinawa, noto, aomori, hokkaido, honshu |
| `Kuril-Russia` | place chứa: kuril, kamchatka, russia, sakhalin |
| `Taiwan` | place chứa: taiwan |
| `other` | Không khớp điều kiện nào |

## Ghi chú magType

Catalog trộn nhiều thang đo magnitude:

| magType | % | Ý nghĩa |
|---|---|---|
| `mb` | 85.9% | Body-wave magnitude (sóng P). Thường thấp hơn Mw với trận lớn |
| `mww` | 10.4% | Moment magnitude (W-phase). Thang Mw, dùng cho sự kiện lớn |
| `mwr` | 3.7% | Moment magnitude (regional surface wave) |
| `mwb` | 0.02% | Moment magnitude (body-wave waveform) |

> ⚠️ **mb ≠ Mw**: không so sánh tuyệt đối. Cột `max_mag` và `mean_mag` trong
> daily summary **trộn nhiều thang đo**. Xem kèm `dominant_magtype` để diễn giải đúng.

## Phạm vi dữ liệu

| Thuộc tính | Giá trị |
|---|---|
| Khoảng | 2023-01-01T00:00:00Z → 2026-03-31 (sự kiện cuối: 2026-03-30) |
| Query interval | 2023-01-01T00:00:00Z → 2026-04-01T00:00:00Z (half-open) |
| Bbox | lat 24.0–46.0, lon 122.0–150.0 |
| Mag ≥ | 4.0 |
| eventtype | earthquake |
| Nguồn | USGS FDSN: `https://earthquake.usgs.gov/fdsnws/event/1/query` |
| Ngày tải | 2026-10-04 |

## Lỗi endtime đã sửa

**Trước (Giai đoạn 1):** `endtime='YYYY-MM-DD'` được USGS API hiểu là `T00:00:00Z` (đầu ngày).
→ 12 ngày cuối quý bị bỏ qua, thiếu **37 sự kiện**.

**Sau (Giai đoạn 2):** dùng half-open `[Q_start, Q_next_start)` với ISO datetime đầy đủ.
→ Tổng sau dedup = 4,184 khớp với count API = 4,184.

## File daily summary

`data/clean/clean_usgs_JP_M4_daily_20230101_20260331.parquet`

### Schema cột daily summary

| Cột | Kiểu | Đơn vị | Mô tả | Ngày trống |
|---|---|---|---|---|
| `date` | `datetime64[us, UTC]` | – | Ngày UTC (00:00:00Z) | – |
| `n_events` | `int32` | – | Số sự kiện trong ngày | `0` |
| `n_events_japan` | `int32` | – | Sự kiện thuộc region=Japan | `0` |
| `n_events_m5plus` | `int32` | – | Sự kiện M ≥ 5.0 | `0` |
| `max_mag` | `float32` | – | Magnitude lớn nhất trong ngày | `NULL` |
| `dominant_magtype` | `object` | – | magType phổ biến nhất (mode) | `NULL` |
| `mean_depth_km` | `float32` | km | Độ sâu trung bình | `NULL` |

> ⚠️ `max_mag` và `dominant_magtype` trộn nhiều thang đo (mb, mww, mwr…). 
> Không so sánh tuyệt đối giữa các ngày có `dominant_magtype` khác nhau.
> Ngày có dư chấn sau trận lớn **không bị xoá**; n_events đột biến là thực tế địa chấn.

### Thông số lưới

| Thuộc tính | Giá trị |
|---|---|
| Số ngày (lưới đầy đủ) | 1,186 |
| sum(n_events) | 4,184 (= tổng sự kiện file clean) |
| sum(n_events_japan) | 3,836 |
| sum(n_events_m5plus) | 426 (sự kiện M≥5.0) |
| Ngày 0 sự kiện | 86 |
| Ngày nhiều nhất | 64 sự kiện |
| Ngày tải | 2026-10-04 |

## Cột thô USGS (ít dùng trực tiếp)

Các cột sau được giữ nguyên từ CSV gốc USGS để phục vụ phân tích chuyên sâu.
Phần lớn không dùng trong dashboard Power BI thông thường:

| Cột | Ghi chú |
|---|---|
| `nst` | Số trạm định vị – chỉ số tin cậy vị trí |
| `gap_deg` | Góc azimuth trạm – chỉ số tin cậy vị trí |
| `dmin_deg` | Khoảng cách tới trạm gần nhất |
| `rms` | Residual định vị – chỉ số tin cậy vị trí |
| `net` | Mạng lưới báo cáo sự kiện (us, pt, …) |
| `horizontal_error_km` | Sai số ngang định vị |
| `depth_error_km` | Sai số độ sâu |
| `mag_error` | Sai số magnitude |
| `mag_nst` | Số trạm tính magnitude |
| `location_source` | Mạng lưới cung cấp định vị |
| `mag_source` | Mạng lưới cung cấp magnitude |
| `event_type` | Luôn = `earthquake` (đã lọc khi tải; cột hằng số) |
| `updated_utc` | Timestamp cập nhật cuối – dùng để dedup, không cần cho analysis |

## File daily summary

`data/clean/clean_usgs_JP_M4_daily_20230101_20260331.parquet`

### Schema cột daily summary

| Cột | Kiểu | Đơn vị | Mô tả | Ngày trống |
|---|---|---|---|---|
| `date` | `datetime64[us, UTC]` | – | Ngày UTC (00:00:00Z) | – |
| `n_events` | `int32` | – | Số sự kiện trong ngày | `0` |
| `n_events_japan` | `int32` | – | Sự kiện thuộc region=Japan | `0` |
| `n_events_m5plus` | `int32` | – | Sự kiện M ≥ 5.0 | `0` |
| `max_mag` | `float32` | – | Magnitude lớn nhất trong ngày | `NULL` |
| `dominant_magtype` | `object` | – | magType phổ biến nhất (mode) | `NULL` |
| `mean_depth_km` | `float32` | km | Độ sâu trung bình | `NULL` |

> ⚠️ `max_mag` và `dominant_magtype` trộn nhiều thang đo (mb, mww, mwr…). 
> Không so sánh tuyệt đối giữa các ngày có `dominant_magtype` khác nhau.
> Ngày có dư chấn sau trận lớn **không bị xoá**; n_events đột biến là thực tế địa chấn.

### Thông số lưới

| Thuộc tính | Giá trị |
|---|---|
| Số ngày (lưới đầy đủ) | 1,186 |
| sum(n_events) | 4,184 (= tổng sự kiện file clean) |
| sum(n_events_japan) | 3,836 |
| sum(n_events_m5plus) | 426 (sự kiện M≥5.0) |
| Ngày 0 sự kiện | 86 |
| Ngày nhiều nhất | 64 sự kiện |
| Ngày tải | 2026-10-05 |

## Cột thô USGS (ít dùng trực tiếp)

Các cột sau được giữ nguyên từ CSV gốc USGS để phục vụ phân tích chuyên sâu.
Phần lớn không dùng trong dashboard Power BI thông thường:

| Cột | Ghi chú |
|---|---|
| `nst` | Số trạm định vị – chỉ số tin cậy vị trí |
| `gap_deg` | Góc azimuth trạm – chỉ số tin cậy vị trí |
| `dmin_deg` | Khoảng cách tới trạm gần nhất |
| `rms` | Residual định vị – chỉ số tin cậy vị trí |
| `net` | Mạng lưới báo cáo sự kiện (us, pt, …) |
| `horizontal_error_km` | Sai số ngang định vị |
| `depth_error_km` | Sai số độ sâu |
| `mag_error` | Sai số magnitude |
| `mag_nst` | Số trạm tính magnitude |
| `location_source` | Mạng lưới cung cấp định vị |
| `mag_source` | Mạng lưới cung cấp magnitude |
| `event_type` | Luôn = `earthquake` (đã lọc khi tải; cột hằng số) |
| `updated_utc` | Timestamp cập nhật cuối – dùng để dedup, không cần cho analysis |

---
*Cập nhật: 2026-10-05*
