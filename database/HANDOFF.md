# Hợp đồng dữ liệu CV2 cho CV3 và CV4

## Các bảng và khóa

| Bảng | Khóa chính | Cột và vai trò |
|---|---|---|
| `clean.station` | station_code | KAK, tên trạm, tọa độ, nguồn |
| `clean.channel` | station_code, channel_code | X/Y/Z/F; nT; tần số 1 phút; FK station |
| `clean.measurement` | station_code, channel_code, time_utc | value REAL, quality_flag riêng kênh, source_quality_flag tổng dòng, batch_id |
| `clean.earthquake_event` | event_id | Giữ đủ 23 cột Parquet và thêm batch_id |
| `clean.earthquake_daily` | date | Giữ đủ 7 cột Parquet và thêm batch_id |
| `analytics.model_run` | run_id UUID | Một lần chạy trên một station/channel; kind filter/forecast, method, input_series, parameters, metrics, train_start/end |
| `analytics.filtered_series` | run_id, time_utc | Chuỗi kết quả lọc, FK ghép xác định đúng run/kênh/kind |
| `analytics.forecast_result` | run_id, target_time | Giá trị dự báo và khoảng tin cậy; FK ghép tới run |

Các số đo có đơn vị nT. Giá trị missing là SQL NULL, không phải 0.
`source_quality_flag` giữ cờ lớn nhất trong bốn kênh ở CV1; không dùng cờ của
một kênh để tự động loại cả các kênh khác. Catalog USGS giữ mag_type; không
coi mb và Mw là cùng thang đo.

## CV3 đọc và ghi gì

Đọc `analytics.vw_signal` bằng station_code/channel_code và khoảng UTC.
Luôn lấy cột thời gian đầy đủ; xử lý cờ bằng cột riêng, không xóa mốc thời gian.
Các query khởi đầu ở `sql/queries.sql`; hourly/daily có sẵn để làm dashboard.
Ghi chuỗi đã lọc vào `analytics.filtered_series`, sau khi tạo model_run kind filter.

```sql
BEGIN;
INSERT INTO analytics.model_run
    (run_id,station_code,channel_code,run_kind,method,input_series,parameters)
VALUES ('11111111-1111-4111-8111-111111111111','KAK','X','filter',
        'median','clean.measurement','{"window":5}');
-- Sau khi CV3 thực sự tính giá trị, dùng COPY/INSERT kết quả vào:
-- time_utc, run_id, station_code, channel_code, filtered_value, quality_flag
-- Không ghi đè clean.measurement. Dùng UUID mới cho lần chạy/phương pháp khác.
COMMIT;
```

UUID trên chỉ là ví dụ hợp đồng; chưa được chèn vào database. Code ứng dụng
tạo UUID mới (Python uuid.uuid4) cho mỗi run. `run_kind` của filtered_series có
default filter. So sánh qua `analytics.vw_filtered_comparison`.

## CV4 đọc và ghi gì

Đọc chuỗi Clean hoặc filtered_series của một run cụ thể. Tạo model_run kind
forecast, ghi train_start/end, parameters và metrics (RMSE/MAE...). Ghi kết quả
vào forecast_result; target_time là thời điểm được dự báo, created_at ở model_run
là thời điểm chạy mô hình. Không sử dụng created_at thay target_time.

```sql
BEGIN;
INSERT INTO analytics.model_run
    (run_id,station_code,channel_code,run_kind,method,input_series,train_start,train_end,parameters)
VALUES ('22222222-2222-4222-8222-222222222222','KAK','F','forecast',
        'naive','clean.measurement','2023-01-01T00:00:00Z','2025-12-31T23:59:00Z','{}');
-- CV4 nhập target_time, run_id, station_code, channel_code,
-- predicted_value, lower_bound, upper_bound sau khi chạy mô hình.
COMMIT;
```

Đây là ví dụ cấu trúc, không phải kết quả dự báo. V1 không tự tạo dữ liệu lọc,
metrics hay dự báo. Dashboard dùng `analytics.vw_forecast` để xem thực tế/dự báo.
Tài khoản geopulse_reader chỉ đọc; nhóm ghi dữ liệu cần được chủ DB cấp tài
khoản ghi phù hợp hoặc chạy script bằng tài khoản quản lý cục bộ.

## Checklist bàn giao

- Gửi ERD.md và các tên bảng/khóa ở trên cho CV3 trước.
- Chạy inspect → import → verify --full → benchmark; giữ báo cáo thực tế.
- Xác nhận 6.831.360 measurement = 1.707.840 phút × 4 kênh.
- Xác nhận 4.184 events, 1.186 ngày và 86 ngày không có sự kiện.
- Xin CV1 file original_raw để hoàn tất tầng Raw; clean_handoff không thay thế raw.
- Cung cấp địa chỉ kết nối và tài khoản riêng; không commit file mật khẩu.


## Tài liệu đi kèm

- [USAGE.md](USAGE.md): mỗi thành viên dựng instance/mật khẩu riêng và kết nối pgAdmin.
- [DATA_DICTIONARY.md](DATA_DICTIONARY.md): toàn bộ thuộc tính và quy tắc NULL/đơn vị.
- [ERD.md](ERD.md): khóa ghép và quan hệ; [CV2_REPORT.md](CV2_REPORT.md): kiểm chứng/giới hạn.
- [evidence/README.md](evidence/README.md): bằng chứng chạy thực tế được lưu cùng nhánh.

Tên fact_kak_1min/fact_usgs_event/fact_usgs_daily trong handoff CV1 là tên
logic nguồn. Tên thực thi CV2 tương ứng là clean.measurement (dạng dài),
clean.earthquake_event, clean.earthquake_daily; clean.kak_1min dựng lại dạng rộng.
Không chạy chồng DDL gợi ý CV1 lên schema CV2.
