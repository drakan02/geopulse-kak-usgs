# docs/scope.md

---

## 1. Phạm vi dataset cuối cùng

| Thuộc tính | Giá trị |
| --- | --- |
| **Trạm** | KAK (Kakioka, Nhật Bản) |
| **Mã IAGA** | KAK |
| **Toạ độ** | 36.232°N, 140.186°E, cao độ 36 m |
| **Khoảng thời gian** | 2023-01-01T00:00:00Z → 2026-03-31T23:59:00Z |
| **Tần số** | 1 phút (1,440 điểm/ngày) |
| **Loại dữ liệu** | **Quasi-definitive (Q)** – một loại duy nhất |
| **Thành phần** | X, Y, Z, F (nT) – hệ toạ độ XYZF |
| **Nguồn** | BGS HAPI: `kak/quasi-def/PT1M/xyzf` |
| **URL** | `https://imag-data.bgs.ac.uk/GIN_V1/hapi` |
| **Sentinel** | 99999.0 (xác nhận từ HAPI info endpoint) |
| **Điểm lý thuyết** | 39 tháng × ~44,000 phút ≈ 1,699,920 điểm |

### Ghi chú tháng 2026-04 — Đã xác nhận không kéo dài

- KAK stopDate trên HAPI = 2026-04-30T23:59:00Z.
- Tháng 4/2026 đã kiểm tra: **38,879/43,199 = 90.00% valid** (đúng ngưỡng, không vượt).
- **Quyết định: CẮT TẠI 2026-03-31.** Lý do:
  - 4,320 điểm fill (10% tháng) sẽ tạo gap phân tán trong chuỗi.
  - Các gap này vượt `INTERP_MAX_GAP = 5 phút`, không thể nội suy tuyến tính.
  - Nhóm ưu tiên tính đồng nhất 100% valid trên toàn chuỗi hơn việc thêm 1 tháng bất hoàn chỉnh.
- Ghi chú vào `data_dictionary.md` và `data_quality_report.md`.



## 2. Dữ liệu địa chấn USGS (đã cập nhật)

| Thuộc tính | Giá trị |
|---|---|
| **Nguồn** | USGS FDSN Event Web Service |
| **URL** | `https://earthquake.usgs.gov/fdsnws/event/1/query` |
| **Khoảng thời gian** | 2023-01-01T00:00:00Z → 2026-03-31 |
| **Query interval** | 2023-01-01T00:00:00Z → 2026-04-01T00:00:00Z (half-open) |
| **Vùng địa lý** | lat 24–46°N, lon 122–150°E (Nhật Bản và lân cận) |
| **Magnitude tối thiểu** | M ≥ 4.0 |
| **eventtype** | earthquake |
| **Tổng sự kiện** | 4,184 (sau dedup) |
| **Tag** | JP |
| **File** | `data/clean/clean_usgs_JP_M4_20230101_20260331.parquet` |

### Lý do dùng half-open intervals

Giai đoạn 1 dùng `endtime='YYYY-MM-DD'` → USGS API hiểu là `T00:00:00Z` (đầu ngày),
bỏ sót 12 ngày cuối quý, thiếu **37 sự kiện**. Giai đoạn 2 sửa thành
`[Q_start, Q_next_start)` (half-open) với ISO datetime đầy đủ. Lỗi đã ghi vào
`docs/usgs_quality_report.md`.

### Hạn chế bbox

Hộp toạ độ (lat 24–46, lon 122–150) bao gồm ~8.32% sự kiện ngoài Nhật Bản
(chủ yếu Kamchatka/Kuril 7.2%, Taiwan 0.9%). Cột `region` trong dataset phân loại
gần đúng từ trường `place`. Bbox không thay đổi — xem thêm `usgs_quality_report.md`.

## 3. Lý do chọn KAK

### Vì sao không dùng PHU?

Kết quả kiểm tra thực tế (đếm giá trị valid, 2026-10-05):

| Dataset | Khoảng | Tình trạng |
| --- | --- | --- |
| PHU quasi-def | 2023-01 → 2025-12 | **100% fill** – toàn bộ 36 tháng là 99999.0 |
| PHU quasi-def | 2026-01 → 2026-06 | 89–99% valid (chỉ 6 tháng có dữ liệu thật) |
| PHU reported | 2023-01 → 2026-06 | 33/42 tháng ≥90%, **2024-10 = 0%**, nhiều tháng 71–84% |
| PHU definitive | 2017-01 → 2018-04 | Chuỗi tốt nhất, nhưng dữ liệu cũ (2017–2018) |

→ **PHU không có chuỗi liên tục ≥90% valid trong giai đoạn 2023–2026.**

### Vì sao chọn KAK?

| Dataset | Khoảng | Tình trạng |
| --- | --- | --- |
| KAK quasi-def | 2023-01 → 2026-03 | **100% valid mọi tháng** (39/39 tháng) |

- Quasi-definitive đồng nhất toàn chuỗi, không trộn loại.
- Không có tháng 0% hay thiếu nghiêm trọng.
- Đủ dài (39 tháng ~3,3 năm) cho phân tích time-series, noise, mô hình, dự báo.

### Vì sao không dùng LZH?

- LZH stopDate = 2019-04-22 → toàn bộ 2023–2026 ngoài phạm vi. Không có dữ liệu.

## 4. Hạn chế (ghi vào data_quality_report.md)

1. **Trạm ngoài khu vực nghiên cứu:** KAK ở Nhật Bản (~36°N, 140°E), không phải trạm Việt Nam. Các đặc trưng từ trường (cường độ, biến thiên) khác với trạm ở Đông Nam Á.
2. **Một trạm duy nhất:** Không thể phát hiện lỗi cục bộ bằng cách so sánh chéo.
3. **Quasi-definitive, không phải Definitive:** QD đã qua hiệu chỉnh baseline sơ bộ nhưng chưa được phê duyệt cuối cùng. Sai số baseline có thể còn tồn tại.
4. **Chuỗi cắt tại 2026-03-31:** Tháng 4/2026 valid 90.00% (borderline). Có thể kéo dài sau khi xác nhận.
5. **Không dùng PHU vì:** Quasi-def PHU chỉ có dữ liệu thật từ 2026-01 (2023–2025 = 100% fill trên HAPI). Reported PHU có tháng 0% (2024-10) và nhiều tháng <90%.

## 5. Schema và nguyên tắc (không thay đổi)

- **Bảng mã `quality_flag`** (0–5), quy trình 5 bước → **giữ nguyên**.
- **Tên cột:** `time_utc`, `station`, `x_nt`, `y_nt`, `z_nt`, `f_nt`, `quality_flag` → **giữ nguyên**.
- **Cột `station`** giữ mã trạm (`KAK`) để sau này thêm trạm khác không phải làm lại.
- **Tên file:** `clean_intermagnet_{STATION}_{freq}_{start}_{end}.parquet` → **giữ nguyên**.

## 6. Lịch sử phạm vi

| Phiên bản | Ngày | Nội dung |
| --- | --- | --- |
| v1 | 2026-10-04 | PHU+DLT, Definitive, 2014–2018 (API GINServices) |
| v2 | 2026-10-05 | PHU, Quasi-def, 2023–2026-06 (đổi sang HAPI) |
| **v3** | **2026-10-05** | **KAK, Quasi-def, 2023-01–2026-03-31 (kết quả kiểm tra valid thực tế)** |

---
*Cập nhật lần cuối: 2026-10-05. Mọi thay đổi phạm vi phải được cả nhóm xác nhận và ghi vào đây.*

### Bảng daily summary

File: `data/clean/clean_usgs_JP_M4_daily_20230101_20260331.parquet`  
Lưới 1,186 ngày, 86 ngày không có sự kiện.  
Kiểm chứng: sum(n_events)=4,184, sum(n_events_japan)=3,836, sum(n_events_m5plus)=426.
