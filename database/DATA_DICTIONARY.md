# Từ điển dữ liệu CV2

Đối chiếu với `sql/001_schema.sql`. PK là khóa chính; FK là khóa ngoại.
Các cột cùng tham gia khóa ghép phải đọc cùng nhau; không duy nhất riêng lẻ.
TIMESTAMPTZ lưu thời điểm; dùng session UTC và khoảng truy vấn [start,end).
REAL bảo toàn độ chính xác float32 của các cột tương ứng ở CV1; các cột
float64 USGS được giữ ở double precision. NULL là thiếu, không phải số 0.

## raw.schema_version

Phiên bản cấu trúc, bảng kỹ thuật.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `version` | `integer` | Không | PK | Phiên bản cấu trúc database. |
| `installed_at` | `timestamptz` | Không | — | Thời điểm UTC cài phiên bản cấu trúc. |

**Khóa chính:** `version`.

## raw.file_archive

Lưu nguyên file và dấu vết nguồn; chặn UPDATE/DELETE bằng trigger.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `file_id` | `bigint` | Không | PK | Mã định danh file lưu trữ. |
| `source_kind` | `text` | Không | — | Loại nguồn: kak_clean, usgs_clean, usgs_daily_clean, kak_raw hoặc usgs_raw. |
| `source_stage` | `text` | Không | — | original_raw hoặc clean_handoff; phân biệt dữ liệu thô và dữ liệu CV1 đã làm sạch. |
| `filename` | `text` | Không | — | Tên file nguồn. |
| `sha256` | `char(64)` | Không | — | SHA256 nội dung file; duy nhất theo cặp source_kind/sha256. |
| `byte_size` | `bigint` | Không | — | Kích thước file tính bằng byte. |
| `row_count` | `bigint` | Có | — | Số dòng nguồn nếu đã xác định. |
| `content` | `bytea` | Không | — | Nguyên byte của file nguồn. |
| `archived_at` | `timestamptz` | Không | — | Thời điểm UTC lưu file. |

**Khóa chính:** `file_id`.

## raw.import_batch

Lịch sử nhập: một file tối đa một batch trong v1.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `batch_id` | `bigint` | Không | PK | Mã đợt nhập để truy về file nguồn. |
| `file_id` | `bigint` | Không | FK, UK | Mã định danh file lưu trữ. |
| `target_table` | `text` | Không | — | Tên bảng đích của đợt nhập. |
| `imported_rows` | `bigint` | Không | — | Số dòng đã nhập. |
| `imported_at` | `timestamptz` | Không | — | Thời điểm UTC nhập dữ liệu. |

**Khóa chính:** `batch_id`.

## clean.station

Danh mục trạm quan trắc.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `station_code` | `text` | Không | PK | Mã trạm; snapshot hiện tại là KAK. |
| `station_name` | `text` | Không | — | Tên trạm; KAK là Kakioka. |
| `country` | `text` | Không | — | Quốc gia của trạm. |
| `latitude` | `double precision` | Không | — | Vĩ độ, độ thập phân; [-90,90]. |
| `longitude` | `double precision` | Không | — | Kinh độ, độ thập phân; [-180,180]. |
| `elevation_m` | `real` | Có | — | Độ cao trạm, m. |
| `data_type` | `text` | Không | — | Loại dữ liệu quan trắc; hiện quasi-definitive. |
| `source_dataset` | `text` | Không | — | Định danh dataset nguồn. |

**Khóa chính:** `station_code`.

## clean.channel

Danh mục kênh theo trạm.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `station_code` | `text` | Không | PK, FK | Mã trạm; snapshot hiện tại là KAK. |
| `channel_code` | `text` | Không | PK | Kênh X (Bắc), Y (Đông), Z (thẳng đứng xuống), F (độ lớn toàn phần). |
| `description` | `text` | Không | — | Diễn giải đối tượng. |
| `unit` | `text` | Không | — | Đơn vị số đo; hiện nT. |
| `sample_interval` | `interval` | Không | — | Khoảng lấy mẫu dương; hiện 1 phút. |

**Khóa chính:** `station_code`, `channel_code`.

## clean.quality_flag

Danh mục mã chất lượng CV1, từ 0 đến 5.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `flag` | `smallint` | Không | PK | Mã chất lượng nguyên từ 0 đến 5. |
| `label` | `text` | Không | UK | Tên ngắn của cờ chất lượng. |
| `description` | `text` | Không | — | Diễn giải đối tượng. |

**Khóa chính:** `flag`.

## clean.measurement

Một số đo của một kênh tại một thời điểm.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `time_utc` | `timestamptz` | Không | PK | Thời điểm UTC của số đo/sự kiện/điểm sau lọc. |
| `station_code` | `text` | Không | PK, FK | Mã trạm; snapshot hiện tại là KAK. |
| `channel_code` | `text` | Không | PK, FK | Kênh X (Bắc), Y (Đông), Z (thẳng đứng xuống), F (độ lớn toàn phần). |
| `value` | `real` | Có | — | Giá trị số đo của kênh, nT; missing là NULL. |
| `quality_flag` | `smallint` | Không | FK | Cờ chất lượng riêng kênh/điểm, tham chiếu clean.quality_flag. |
| `source_quality_flag` | `smallint` | Không | FK | Cờ tổng hợp của dòng CV1: max bốn cờ kênh; giữ để truy nguyên. |
| `batch_id` | `bigint` | Không | FK | Mã đợt nhập để truy về file nguồn. |

**Khóa chính:** `time_utc`, `station_code`, `channel_code`.

## clean.earthquake_event

Catalog sự kiện USGS, giữ đủ 23 cột CV1 và thêm batch_id.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `event_id` | `text` | Không | PK | ID sự kiện USGS duy nhất. |
| `time_utc` | `timestamptz` | Không | — | Thời điểm UTC của số đo/sự kiện/điểm sau lọc. |
| `updated_utc` | `timestamptz` | Có | — | Thời điểm UTC cập nhật sự kiện tại nguồn. |
| `latitude` | `real` | Không | — | Vĩ độ, độ thập phân; [-90,90]. |
| `longitude` | `real` | Không | — | Kinh độ, độ thập phân; [-180,180]. |
| `depth_km` | `real` | Có | — | Độ sâu sự kiện, km. |
| `mag` | `real` | Không | — | Độ lớn; đọc cùng mag_type, không mặc định mọi loại là Mw. |
| `mag_type` | `text` | Có | — | Loại độ lớn do USGS cung cấp (mb, mww, mwr, mwb...). |
| `place` | `text` | Có | — | Mô tả địa điểm từ USGS. |
| `event_type` | `text` | Có | — | Loại sự kiện từ nguồn. |
| `status` | `text` | Có | — | Trạng thái xem xét sự kiện từ nguồn. |
| `region` | `text` | Có | — | Phân vùng gần đúng từ place, không phải ranh giới GIS chính xác. |
| `nst` | `bigint` | Có | — | Số trạm dùng trong định vị sự kiện. |
| `gap_deg` | `bigint` | Có | — | Khoảng trống phương vị lớn nhất giữa các trạm, độ. |
| `dmin_deg` | `double precision` | Có | — | Khoảng cách góc tới trạm gần nhất, độ. |
| `rms` | `double precision` | Có | — | RMS phần dư thời gian truyền sóng, giây. |
| `net` | `text` | Có | — | Mã mạng báo cáo. |
| `horizontal_error_km` | `double precision` | Có | — | Sai số vị trí ngang, km. |
| `depth_error_km` | `double precision` | Có | — | Sai số độ sâu, km. |
| `mag_error` | `double precision` | Có | — | Sai số ước tính độ lớn. |
| `mag_nst` | `bigint` | Có | — | Số trạm dùng tính độ lớn. |
| `location_source` | `text` | Có | — | Mã nguồn xác định vị trí. |
| `mag_source` | `text` | Có | — | Mã nguồn xác định độ lớn. |
| `batch_id` | `bigint` | Không | FK | Mã đợt nhập để truy về file nguồn. |

**Khóa chính:** `event_id`.

## clean.earthquake_daily

Thống kê ngày nhận từ CV1, giữ 7 cột và thêm batch_id.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `date` | `date` | Không | PK | Ngày UTC; khóa của bảng tổng hợp động đất ngày. |
| `n_events` | `integer` | Không | — | Số sự kiện của tập catalog đã chọn trong ngày. |
| `n_events_japan` | `integer` | Không | — | Số sự kiện có region=Japan trong ngày. |
| `n_events_m5plus` | `integer` | Không | — | Số sự kiện có mag >= 5 trong ngày. |
| `max_mag` | `real` | Có | — | Độ lớn lớn nhất trong ngày; NULL khi không có sự kiện. |
| `dominant_magtype` | `text` | Có | — | Loại độ lớn phổ biến trong ngày; NULL khi không có sự kiện. |
| `mean_depth_km` | `real` | Có | — | Độ sâu trung bình trong ngày, km; NULL khi không có sự kiện. |
| `batch_id` | `bigint` | Không | FK | Mã đợt nhập để truy về file nguồn. |

**Khóa chính:** `date`.

## analytics.model_run

Metadata một lần chạy lọc hoặc dự báo trên một trạm/kênh.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `run_id` | `uuid` | Không | PK | UUID của một lần chạy thực tế; một run cho một trạm/kênh. |
| `station_code` | `text` | Không | FK | Mã trạm; snapshot hiện tại là KAK. |
| `channel_code` | `text` | Không | FK | Kênh X (Bắc), Y (Đông), Z (thẳng đứng xuống), F (độ lớn toàn phần). |
| `run_kind` | `text` | Không | — | Loại chạy: filter hoặc forecast; bảng kết quả cố định theo loại. |
| `method` | `text` | Không | — | Tên phương pháp lọc hoặc mô hình dự báo. |
| `input_series` | `text` | Không | — | Mô tả/định danh nguồn chuỗi đầu vào; hiện là text, không phải FK tới một run khác. |
| `parameters` | `jsonb` | Không | — | Đối tượng JSON lưu tham số phương pháp; mặc định {}. |
| `metrics` | `jsonb` | Không | — | Đối tượng JSON lưu đánh giá thực tế (ví dụ MAE/RMSE); mặc định {}. |
| `train_start` | `timestamptz` | Có | — | Đầu khoảng huấn luyện UTC, có thể NULL. |
| `train_end` | `timestamptz` | Có | — | Cuối khoảng huấn luyện UTC; không trước train_start. |
| `created_at` | `timestamptz` | Không | — | Thời điểm UTC tạo bản ghi lần chạy; khác thời điểm được dự báo. |

**Khóa chính:** `run_id`.

## analytics.filtered_series

Chuỗi đầu ra lọc, không ghi đè Clean.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `time_utc` | `timestamptz` | Không | PK | Thời điểm UTC của số đo/sự kiện/điểm sau lọc. |
| `run_id` | `uuid` | Không | PK, FK | UUID của một lần chạy thực tế; một run cho một trạm/kênh. |
| `station_code` | `text` | Không | FK | Mã trạm; snapshot hiện tại là KAK. |
| `channel_code` | `text` | Không | FK | Kênh X (Bắc), Y (Đông), Z (thẳng đứng xuống), F (độ lớn toàn phần). |
| `run_kind` | `text` | Không | FK | Loại chạy: filter hoặc forecast; bảng kết quả cố định theo loại. |
| `filtered_value` | `real` | Có | — | Giá trị sau lọc, nT. |
| `quality_flag` | `smallint` | Không | FK | Cờ chất lượng riêng kênh/điểm, tham chiếu clean.quality_flag. |

**Khóa chính:** `time_utc`, `run_id`.

## analytics.forecast_result

Chuỗi dự báo và các cận tùy chọn.

| Cột | Kiểu SQL | NULL được phép | Khóa | Ý nghĩa |
|---|---|---|---|---|
| `target_time` | `timestamptz` | Không | PK | Thời điểm UTC mà giá trị dự báo hướng tới. |
| `run_id` | `uuid` | Không | PK, FK | UUID của một lần chạy thực tế; một run cho một trạm/kênh. |
| `station_code` | `text` | Không | FK | Mã trạm; snapshot hiện tại là KAK. |
| `channel_code` | `text` | Không | FK | Kênh X (Bắc), Y (Đông), Z (thẳng đứng xuống), F (độ lớn toàn phần). |
| `run_kind` | `text` | Không | FK | Loại chạy: filter hoặc forecast; bảng kết quả cố định theo loại. |
| `predicted_value` | `real` | Không | — | Giá trị dự báo của kênh, nT. |
| `lower_bound` | `real` | Có | — | Cận dưới khoảng dự báo nếu phương pháp cung cấp, nT. |
| `upper_bound` | `real` | Có | — | Cận trên khoảng dự báo nếu phương pháp cung cấp, nT. |

**Khóa chính:** `target_time`, `run_id`.

## Quy tắc và liên kết quan trọng

- file_archive UNIQUE theo cặp `(source_kind,sha256)`; import_batch.file_id UNIQUE.
- channel FK station_code → station; measurement FK ghép trạm/kênh → channel.
- measurement có hai FK tới quality_flag; source_quality_flag >= quality_flag.
- Cờ missing=2 buộc value=NULL. Cấm NaN/Infinity; không tự xóa spike/flatline.
- Các bản ghi Clean tham chiếu import_batch để truy về file nguồn.
- model_run FK ghép trạm/kênh → channel. Mỗi run là filter hoặc forecast.
- Kết quả FK ghép `(run_id,station_code,channel_code,run_kind)` → model_run,
  ngăn gán nhầm kênh hoặc loại chạy. filtered_series có thêm FK quality_flag.
- lower_bound <= upper_bound khi cả hai có giá trị; không áp đặt mức tin cậy thống kê.
- Ngày không có động đất giữ số đếm=0 và thống kê mag/depth=NULL.
- earthquake_event không có FK tới KAK; daily không có FK theo từng event.

## Continuous aggregate giờ/ngày

`analytics.measurement_hourly` và `measurement_daily` có cùng các cột:

| Cột | Kiểu kết quả | Ý nghĩa |
|---|---|---|
| bucket_utc | timestamptz | Đầu khoảng giờ/ngày UTC |
| station_code, channel_code | text | Trạm và kênh |
| n_total | bigint | Tất cả số đo trong khoảng, kể cả có cờ |
| n_ok | bigint | Số đo có quality_flag=0 |
| mean_value | double precision | Trung bình value của các điểm cờ 0 |
| min_value, max_value | real | Min/max của các điểm cờ 0 |
| stddev_value | double precision | Độ lệch chuẩn mẫu của các điểm cờ 0 |

Các giá trị thống kê có thể NULL khi không đủ dữ liệu hợp lệ. Refresh tường minh
sau import; chưa có policy tự refresh, retention hoặc compression.

## Các view phục vụ đọc

| View | Nội dung |
|---|---|
| clean.kak_1min | 11 cột dạng rộng giống CV1; một dòng/phút/trạm |
| analytics.vw_signal | Thời gian, trạm, kênh, đơn vị, giá trị gốc, cờ và các cách chọn giá trị |
| analytics.vw_earthquake_events | Toàn bộ cột earthquake_event |
| analytics.vw_earthquake_daily | Toàn bộ cột earthquake_daily |
| analytics.vw_daily_context | Tổng hợp số đo theo ngày ghép thống kê động đất theo ngày UTC |
| analytics.vw_filtered_comparison | Giá trị gốc và sau lọc, run, method, các cờ |
| analytics.vw_forecast | Dự báo, cận, thông tin phương pháp/đánh giá và giá trị thực tế nếu có |

Trong vw_signal: original_value giữ số đo; strict_value chỉ giữ cờ 0;
cv1_display_value giữ cờ 0/3/5 theo chính sách hiển thị CV1, không chứng nhận
chất lượng. Kết hợp theo ngày không chứng minh quan hệ nhân quả.
