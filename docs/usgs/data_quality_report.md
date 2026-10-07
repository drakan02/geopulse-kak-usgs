# Báo cáo Chất lượng Dữ liệu – USGS Earthquake Catalog

> Vùng quan sát: Nhật Bản và phụ cận (Vĩ độ 24.0°N–46.0°N, Kinh độ 122.0°E–150.0°E)  
> Ngưỡng độ lớn: Magnitude M >= 4.0  
> Khoảng thời gian: 2023-01-01 đến 2026-03-31  
> Thời điểm tạo báo cáo: 2026-10-07T15:42:23Z UTC  

---

## 1. Tóm tắt Thực thi & Hạn chế Dữ liệu

1. Trạng thái Cập nhật USGS Catalog: USGS có thể hiệu chỉnh lại độ lớn (Magnitude) và tọa độ tâm chấn sau khi thu thập thêm dữ liệu trạm. Báo cáo này phản ánh trạng thái dữ liệu tại thời điểm tải về.
2. Ngưỡng lọc Độ lớn M >= 4.0: Dữ liệu chỉ bao gồm các sự kiện có M >= 4.0 theo cấu hình mục tiêu nghiên cứu; các trận động đất nhỏ hơn M < 4.0 không nằm trong phạm vi catalog này.
3. Tác động của Chuỗi Dư chấn: Các trận động đất lớn gây ra chuỗi dư chấn kéo dài làm mật độ sự kiện tăng đột biến theo thời gian (đặc biệt là trận động đất bán đảo Noto tháng 01/2024 M7.5 và Aomori tháng 12/2025 M7.6).
4. Khung Tọa độ Bbox Khu vực: Hộp tọa độ bao phủ vùng biển Nhật Bản có chứa khoảng 8.32% sự kiện nằm ở các khu vực giáp ranh (Kuril/Nga 7.22%, Đài Loan 0.91%). Cột `region` hỗ trợ lọc chính xác theo yêu cầu phân tích.

---

## 2. Tổng quan Dữ liệu & Thống kê Mô tả

### 2.1 Thuộc tính Dữ liệu Chính

| Thuộc tính | Giá trị định lượng |
|---|---|
| Tổng số sự kiện sạch (sau khử trùng lặp) | 4,184 sự kiện |
| Tổng số sự kiện theo truy vấn USGS Count API | 4,184 sự kiện |
| Số bản ghi trùng lặp `event_id` đã xử lý | 0 bản ghi |
| Mốc thời gian sự kiện đầu tiên | 2023-01-01 21:55:08 UTC |
| Mốc thời gian sự kiện cuối cùng | 2026-03-31 15:38:47 UTC |
| Trạng thái khớp số lượng API vs File | KHỚP HOÀN TOÀN (chênh lệch = 0) |

### 2.2 Thống kê Mô tả Chi tiết (Độ lớn Magnitude & Độ sâu Depth)

| Chỉ số thống kê | Độ lớn Magnitude (M) | Độ sâu Depth (km) |
|---|---|---|
| Số lượng (Count) | 4,184 | 4,184 |
| Trung bình (Mean) | 4.51 | 65.64 km |
| Độ lệch chuẩn (Std Dev) | 0.38 | 100.39 km |
| Nhỏ nhất (Min) | 4.00 | 2.29 km |
| Phân vị 25% | 4.30 | 10.00 km |
| Trung vị (50% Median) | 4.40 | 35.00 km |
| Phân vị 75% | 4.60 | 64.14 km |
| Lớn nhất (Max) | 7.60 | 644.88 km |

---

## 3. Khắc phục Lỗi Truy vấn USGS API (Lỗi Endtime)

| Tiêu chí | Giai đoạn 1 (Truy vấn định dạng cũ) | Giai đoạn 2 (Truy vấn Half-Open đã sửa) | Kết quả kiểm chứng |
|---|---|---|---|
| Định dạng tham số `endtime` | `YYYY-MM-DD` | `YYYY-MM-DDTHH:MM:SSZ` | Khắc phục triệt để lỗi mất dữ liệu ngày cuối quý |
| Diễn giải từ phía API | T00:00:00Z (Đầu ngày) | Nửa mở `[Q_start, Q_next_start)` | Thu thập chính xác toàn bộ 24 giờ ngày cuối |
| Số ngày bị thiếu dữ liệu | 12 ngày cuối quý bị bỏ qua | 0 ngày bị thiếu | Phục hồi dữ liệu 12 ngày biên |
| Số sự kiện bị bỏ sót | 37 sự kiện bị bỏ sót | 0 sự kiện bị bỏ sót | Thu hồi đầy đủ 37 sự kiện bị thiếu |
| Tổng số sự kiện thu thập | 4,146 sự kiện | 4,184 sự kiện | Đạt 100% khớp với USGS API count |

---

## 4. Phân phối Độ lớn Magnitude & Thang đo magType

### 4.1 Phân phối Dải Magnitude (M)

| Dải Magnitude | Số lượng sự kiện | Tỷ lệ phần trăm (%) |
|---|---|---|
| 4.0 – 4.5 | 2,206 | 52.72% |
| 4.5 – 5.0 | 1,552 | 37.09% |
| 5.0 – 5.5 | 305 | 7.29% |
| 5.5 – 6.0 | 86 | 2.06% |
| 6.0 – 6.5 | 24 | 0.57% |
| 6.5 – 7.0 | 8 | 0.19% |
| >= 7.0 | 3 | 0.07% |
| Tổng số | 4,184 | 100.00% |

### 4.2 Thang đo magType

| Thang đo `magType` | Số lượng sự kiện | Tỷ lệ phần trăm (%) | Ý nghĩa kỹ thuật |
|---|---|---|---|
| `mb` | 3,595 | 85.92% | Thang đo mb theo chuẩn USGS |
| `mww` | 435 | 10.40% | Thang đo mww theo chuẩn USGS |
| `mwr` | 153 | 3.66% | Thang đo mwr theo chuẩn USGS |
| `mwb` | 1 | 0.02% | Thang đo mwb theo chuẩn USGS |


---

## 5. Phân vùng Địa lý (Region Breakdown)

| Mã vùng (Region) | Số lượng sự kiện | Tỷ lệ phần trăm (%) | Mô tả phạm vi |
|---|---|---|---|
| Japan | 3,836 | 91.68% | Vùng Japan |
| Kuril-Russia | 302 | 7.22% | Vùng Kuril-Russia |
| Taiwan | 38 | 0.91% | Vùng Taiwan |
| other | 8 | 0.19% | Vùng other |


---

## 6. Phân tích Dữ liệu Chuỗi Ngày & Sự kiện Đột biến (Top Anomaly Days)

Các tháng có mật độ sự kiện tăng đột biến do chuỗi dư chấn sau động đất lớn:
- Tháng 10/2023: 275 sự kiện (Sự kiện lớn nhất: M6.1 mww – Quần đảo Izu)
- Tháng 01/2024: 204 sự kiện (Sự kiện lớn nhất: M7.5 mww – Động đất Bán đảo Noto 2024)
- Tháng 12/2025: 195 sự kiện (Sự kiện lớn nhất: M7.6 mww – Động đất Tỉnh Aomori 2025)

Top 5 Ngày có số lượng động đất cao nhất trong chuỗi thời gian:
1. 2024-01-01: 64 sự kiện (Max M7.5 mb – Trận động đất Bán đảo Noto 2024)
2. 2025-11-09: 50 sự kiện (Max M6.8 mb)
3. 2023-10-05: 42 sự kiện (Max M6.1 mb – Chuỗi động đất Quần đảo Izu)
4. 2023-10-06: 33 sự kiện (Max M6.1 mb – Chuỗi động đất Quần đảo Izu)
5. 2023-10-03: 32 sự kiện (Max M6.0 mb – Chuỗi động đất Quần đảo Izu)

---

## 7. Khuyến nghị Sử dụng cho Phân tích Hạ nguồn

- Phân tích Xu hướng Địa chấn: Các ngày và tháng có dư chấn tăng đột biến được bảo toàn nguyên vẹn nhằm phản ánh đúng thực tế di chuyển vỏ trái đất.
- Lọc Theo Vùng Địa lý: Sử dụng cột `region == 'Japan'` để tập trung phân tích riêng lãnh thổ Nhật Bản (loại bỏ 8.32% sự kiện vùng lân cận Kuril/Đài Loan nếu cần).
- Tích hợp Mô hình Địa từ: Kết hợp danh mục động đất này với chuỗi từ trường KAK để kiểm chứng mối tương quan giữa sự biến thiên địa từ và các trận động đất M >= 4.0.

---
*Báo cáo được tạo tự động bởi mô-đun làm sạch danh mục động đất USGS (src/usgs/clean_catalog.py).*

## 9. Daily Summary (Giai đoạn 3)

| Thuộc tính | Giá trị |
|---|---|
| File | `clean_usgs_JP_M4_daily_20230101_20260331.parquet` |
| Số ngày (lưới đầy đủ) | 1,186 |
| Assert n_events | sum = 4,184 (Đạt kiểm chứng) |
| Assert n_events_japan | sum = 3,836 (Đạt kiểm chứng) |
| Assert n_events_m5plus | sum = 426 (Đạt kiểm chứng) |
| Ngày 0 sự kiện | 86 (max_mag/dominant_magtype/mean_depth_km = NULL; Đạt kiểm chứng) |
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
