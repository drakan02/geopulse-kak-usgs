# Từ điển Dữ liệu – USGS Earthquake Catalog

> Thời điểm tạo báo cáo: 2026-10-07T15:42:23Z UTC  
> Nguồn dữ liệu: USGS FDSN Event Web Service (`https://earthquake.usgs.gov/fdsnws/event/1/query`)  
> Vùng địa lý: Lat 24.0°N–46.0°N, Lon 122.0°E–150.0°E (Nhật Bản và phụ cận)  
> Khoảng thời gian: 2023-01-01 đến 2026-03-31  

---

## 1. Thông số Sản phẩm File

| Tên sản phẩm | Tên file / Đường dẫn | Định dạng & Số lượng bản ghi | Mô tả nội dung |
|---|---|---|---|
| Danh mục Sự kiện Sạch | `data/clean/clean_usgs_JP_M4_20230101_20260331.parquet` | Parquet Snappy (4,184 sự kiện, 23 cột) | Danh mục chi tiết các trận động đất M >= 4.0 |
| Tổng hợp Theo Ngày | `data/clean/clean_usgs_JP_M4_daily_20230101_20260331.parquet` | Parquet Snappy (1,186 ngày, 7 cột) | Lưới thời gian liên tục tổng hợp chỉ số địa chấn ngày |

---

## 2. Schema Cột Dữ liệu (Danh mục Sự kiện)

| Cột | Kiểu dữ liệu | Đơn vị | Mô tả | Khoảng giá trị / Định dạng | Ghi chú |
|---|---|---|---|---|---|
| `event_id` | `object` | - | Mã định danh sự kiện USGS | Mã chuỗi (ví dụ: `us7000lz5b`) | Khóa chính duy nhất |
| `time_utc` | `datetime64[us, UTC]` | - | Thời điểm phát sinh động đất | ISO 8601 UTC | Thời gian sự kiện xảy ra |
| `updated_utc` | `datetime64[us, UTC]` | - | Mốc thời gian cập nhật gần nhất | ISO 8601 UTC | Dùng để khử trùng lặp (deduplication) |
| `latitude` | `float32` | °N | Vĩ độ tâm chấn | 24.0000 đến 46.0000 | Tọa độ địa lý Bán cầu Bắc |
| `longitude` | `float32` | °E | Kinh độ tâm chấn | 122.0000 đến 150.0000 | Tọa độ địa lý Bán cầu Đông |
| `depth_km` | `float32` | km | Độ sâu tâm chấn | >= 0.0 km | Độ sâu chấn điểm |
| `mag` | `float32` | - | Độ lớn động đất (Magnitude) | >= 4.0 | Ngưỡng thu thập M >= 4.0 |
| `mag_type` | `category` | - | Thang đo độ lớn | `mb`, `mww`, `mwr`, `mwb` | Loại thang đo magnitude |
| `place` | `object` | - | Mô tả vị trí địa lý tự do | Văn bản từ USGS | Tên khu vực bằng tiếng Anh |
| `event_type` | `category` | - | Phân loại sự kiện | `earthquake` | Đã lọc chỉ lấy động đất |
| `status` | `category` | - | Trạng thái kiểm duyệt | `reviewed`, `automatic` | Trạng thái đánh giá của chuyên gia |
| `region` | `category` | - | Vùng phân loại tự động | `Japan`, `Kuril-Russia`, `Taiwan`, `other` | Phân vùng từ trường `place` |
| `nst` | `float64` | - | Số lượng trạm quan sát | Số nguyên >= 0 | Số trạm tham gia định vị |
| `gap_deg` | `float64` | ° | Góc khuyết azimuth giữa các trạm | 0.0 đến 360.0° | Chỉ số tin cậy vị trí |
| `dmin_deg` | `float64` | ° | Khoảng cách tới trạm gần nhất | Khoảng cách góc tính bằng độ | Độ gần trạm định vị |
| `rms` | `float64` | s | Sai số bình phương trung bình residual | Khoảng thời gian tính bằng giây | Chỉ số độ chính xác thời gian đi sóng |
| `net` | `object` | - | Mã mạng lưới trạm chính | `us`, `pt`, v.v. | Cơ quan cung cấp dữ liệu gốc |
| `horizontal_error_km` | `float64` | km | Sai số định vị theo phương ngang | >= 0.0 km | Độ chính xác tọa độ mặt đất |
| `depth_error_km` | `float64` | km | Sai số định vị theo độ sâu | >= 0.0 km | Độ chính xác độ sâu |
| `mag_error` | `float64` | - | Sai số tính toán độ lớn | >= 0.0 | Độ tin cậy giá trị magnitude |
| `mag_nst` | `float64` | - | Số trạm tham gia tính magnitude | Số nguyên >= 0 | Số trạm tính độ lớn |
| `location_source` | `object` | - | Nguồn xác định vị trí | Mã mạng lưới | Cơ quan định vị |
| `mag_source` | `object` | - | Nguồn xác định magnitude | Mã mạng lưới | Cơ quan tính độ lớn |

---

## 3. Schema Cột Bảng Tổng hợp Theo Ngày (Daily Summary)

| Cột | Kiểu dữ liệu | Đơn vị | Mô tả | Xử lý ngày không có sự kiện |
|---|---|---|---|---|
| `date` | `datetime64[us, UTC]` | - | Mốc ngày UTC (00:00:00Z) | Khóa ngày liên tục |
| `n_events` | `int32` | - | Tổng số sự kiện trong ngày | Gán = `0` |
| `n_events_japan` | `int32` | - | Số sự kiện thuộc vùng `Japan` | Gán = `0` |
| `n_events_m5plus` | `int32` | - | Số sự kiện có M >= 5.0 | Gán = `0` |
| `max_mag` | `float32` | - | Độ lớn lớn nhất trong ngày | Gán = `NaN` (`NULL`) |
| `dominant_magtype` | `object` | - | Thang đo độ lớn phổ biến nhất trong ngày | Gán = `NaN` (`NULL`) |
| `mean_depth_km` | `float32` | km | Độ sâu trung bình các sự kiện trong ngày | Gán = `NaN` (`NULL`) |

---

## 4. Phân loại Vùng Địa lý (Region Mapping Rules)

Phân loại vùng địa lý dựa trên thuật toán khớp chuỗi ký tự trong trường văn bản `place`:

| Mã vùng (Region) | Điều kiện từ khóa khớp trong trường `place` | Phạm vi địa lý tương ứng |
|---|---|---|
| `Japan` | Chứa một trong các từ: `japan`, `ryukyu`, `izu`, `bonin`, `okinawa`, `noto`, `aomori`, `hokkaido`, `honshu` | Lãnh thổ và vùng biển Nhật Bản |
| `Kuril-Russia` | Chứa một trong các từ: `kuril`, `kamchatka`, `russia`, `sakhalin` | Quần đảo Kuril, Bán đảo Kamchatka, Sakhalin (Nga) |
| `Taiwan` | Chứa từ: `taiwan` | Đài Loan và vùng biển phụ cận |
| `other` | Không chứa các từ khóa trên nhưng nằm trong Bbox | Các khu vực lân cận khác trên biển |

---

## 5. Đặc tả Thang đo Magnitude (magType)

| Thang đo | Tỷ lệ trong dữ liệu | Tên đầy đủ & Ý nghĩa khoa học | Ghi chú vận hành |
|---|---|---|---|
| `mb` | 85.92% | Body-Wave Magnitude (Độ lớn sóng thể P) | Thang đo phổ biến nhất của USGS; có hiện tượng bão hòa ở các trận động đất rất lớn (M > 7.0) |
| `mww` | 10.40% | Moment Magnitude W-phase | Thang Moment Mw tiêu chuẩn; chính xác nhất cho các trận động đất lớn và cực lớn |
| `mwr` | 3.66% | Regional Surface Wave Moment Magnitude | Thang Moment Mw tính từ sóng bề mặt khu vực |
| `mwb` | 0.02% | Body-Wave Waveform Moment Magnitude | Thang Moment Mw tính từ dạng sóng thể |

Ghi chú Kỹ thuật: Các thang đo độ lớn khác nhau về bản chất năng lượng (mb vs Mw). Các cột tổng hợp `max_mag` và `mean_mag` đại diện cho giá trị số học tổng hợp; cần tham chiếu kèm cột `dominant_magtype`.

---

## 6. Sửa Lỗi Kỹ thuật Truy vấn USGS API (Half-Open Interval)

| Tham số đối chiếu | Giai đoạn 1 (Truy vấn theo định dạng cũ) | Giai đoạn 2 (Đã sửa lỗi Half-Open) | Kết quả khắc phục |
|---|---|---|---|
| Định dạng tham số `endtime` | `YYYY-MM-DD` | `YYYY-MM-DDTHH:MM:SSZ` | Tránh việc USGS API mặc định hiểu về 00:00:00Z |
| Loại khoảng thời gian | Khoảng đóng `[start, end]` | Khoảng nửa mở `[Q_start, Q_next_start)` | Đảm bảo không trùng và không bỏ sót điểm biên quý |
| Số sự kiện bỏ sót | Bỏ sót 37 sự kiện (ở 12 ngày cuối quý) | 0 sự kiện bỏ sót | Phục hồi hoàn toàn 100% dữ liệu gốc |
| Tổng số sự kiện thu thập | 4,146 sự kiện | 4,184 sự kiện | Khớp hoàn toàn 100% với hàm Count API (4,184) |

---
*Tài liệu được tạo tự động bởi mô-đun làm sạch danh mục động đất USGS (src/usgs/clean_catalog.py).*

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

> Ghi chú: `max_mag` và `dominant_magtype` trộn nhiều thang đo (mb, mww, mwr…). 
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
| Ngày tải | 2026-10-07 |

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
*Cập nhật: 2026-10-07*
