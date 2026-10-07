# Báo cáo Chất lượng – USGS Earthquake Catalog

> Trạm: KAK region (Japan & lân cận) | Khoảng: 2023-01-01 → 2026-03-31
> Tạo bởi `clean_catalog.py` ngày 2026-10-07.

---

## 1. Lỗi endtime đã phát hiện và sửa

| | Giai đoạn 1 (sai) | Giai đoạn 2 (đã sửa) |
|---|---|---|
| Format endtime | `YYYY-MM-DD` | `YYYY-MM-DDTHH:MM:SSZ` |
| Cách diễn giải | T00:00:00Z (đầu ngày) | Half-open: đầu quý kế |
| Sự kiện bị bỏ | **37** (12 ngày cuối quý) | 0 |
| Tổng sự kiện | 4,146 | **4,184** |

## 2. Tổng quan sau Giai đoạn 2

| Thuộc tính | Giá trị |
|---|---|
| Tổng sự kiện (sau dedup) | **4,184** |
| Count API (1 query liên tục) | **4,184** |
| Trùng event_id đã xoá | 0 |
| Khớp count vs file | ✅ KHỚP |
| Khoảng thực tế | 2023-01-01 21:55:08 → 2026-03-31 15:38:47 |
| Sự kiện 2026-03-31 | 1 |

## 3. Chất lượng dữ liệu

| Kiểm tra | Kết quả |
|---|---|
| Thiếu event_id | 0 |
| Thiếu time_utc | 0 |
| Thiếu mag | 0 |
| Thiếu depth_km | 0 |
| Thiếu place | 0 |
| Ngoài bbox | 0 (đã kiểm tra) |
| Độ sâu âm | 0 |
| Mag < 4.0 | 0 |

## 4. Phân phối magnitude

| Dải | Số sự kiện |
|---|---|
| 4.0–4.5 | 2,206 |
| 4.5–5.0 | 1,552 |
| 5.0–5.5 | 305 |
| 5.5–6.0 | 86 |
| 6.0–6.5 | 24 |
| 6.5–7.0 | 8 |
| ≥ 7.0 | 3 |
| **Tổng** | **4,184** |

> M tối đa: 7.6 | Mean: 4.51 | Median: 4.40

## 5. magType

| magType | Số SĐ | % |
|---|---|---|
| `mb` | 3,595 | 85.92% |
| `mww` | 435 | 10.40% |
| `mwr` | 153 | 3.66% |
| `mwb` | 1 | 0.02% |


> ⚠️ mb (85.9%) và Mw (mww/mwr/mwb) không so sánh tuyệt đối về năng lượng.

## 6. Phân vùng (region – gần đúng)

| Vùng | Số SĐ | % |
|---|---|---|
| Japan | 3,836 | 91.68% |
| Kuril-Russia | 302 | 7.22% |
| Taiwan | 38 | 0.91% |
| other | 8 | 0.19% |


> Region được suy từ trường `place` (văn bản tự do). Có thể sai ở biên giới địa lý.

## 7. Tháng đột biến (ngưỡng IQR)

| Tháng | Số SĐ | Sự kiện lớn nhất |
|---|---|---|
| 2023-10 | 275 | M6.1 mww – Izu Islands |
| 2024-01 | 204 | **M7.5 mww – 2024 Noto Peninsula Earthquake** |
| 2025-12 | 195 | **M7.6 mww – 2025 Aomori Prefecture Earthquake** |

> Các tháng đột biến không bị xoá. Người dùng cần nhận biết khi phân tích phân phối.

## 8. Hạn chế

1. **Catalog cập nhật thực tế:** USGS có thể điều chỉnh magnitude sau khi sự kiện xảy ra. Catalog phản ánh trạng thái tại ngày tải (2026-10-07).
2. **Ngưỡng M4.0:** Đây là lựa chọn của nhóm, không phải toàn bộ động đất. Có thể thiếu các sự kiện nhỏ hơn.
3. **Dư chấn:** Chuỗi dư chấn sau trận lớn làm lệch phân phối theo thời gian (2024-01, 2025-12).
4. **8.32% ngoài Nhật Bản:** Bbox hiện tại bao phủ cả Kamchatka/Kuril (7.21%) và Taiwan (0.92%). Cột `region` giúp lọc nếu cần.
5. **magType trộn lẫn:** Không so sánh mb và Mw tuyệt đối. Xem `dominant_magtype` trong daily summary.

## 9. Daily Summary (Giai đoạn 3)

| Thuộc tính | Giá trị |
|---|---|
| File | `clean_usgs_JP_M4_daily_20230101_20260331.parquet` |
| Số ngày (lưới đầy đủ) | 1,186 |
| Assert n_events | sum = 4,184 ✅ |
| Assert n_events_japan | sum = 3,836 ✅ |
| Assert n_events_m5plus | sum = 426 ✅ |
| Ngày 0 sự kiện | 86 (max_mag/dominant_magtype/mean_depth_km = NULL) ✅ |
| Ngày nhiều nhất | 64 sự kiện |
| Tạo lúc | 2026-10-07 |

### Top 5 ngày nhiều sự kiện nhất

| Ngày | n_events | max_mag | dominant_magtype |
|---|---|---|---|
| 2024-01-01 | 64 | 7.5 | mb |
| 2025-11-09 | 50 | 6.8 | mb |
| 2023-10-05 | 42 | 6.1 | mb |
| 2023-10-06 | 33 | 6.1 | mb |
| 2023-10-03 | 32 | 6.0 | mb |

> Các ngày đột biến do dư chấn **không bị xoá**. Người dùng Power BI nên
> nhận biết các ngày này khi diễn giải xu hướng.

---
*Cập nhật: 2026-10-07*
