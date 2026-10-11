# CV2 Database và Data Modelling

Bộ CV2 nhận ba file Parquet từ CV1, lưu dữ liệu trong PostgreSQL 17 + TimescaleDB,
tạo các bảng để CV3/CV4 ghi kết quả và cung cấp view cho Power BI.
Không chạy lại hoặc sửa pipeline làm sạch của CV1.

## Đọc tài liệu theo thứ tự

1. [USAGE.md](USAGE.md): dựng mới, mở lại, pgAdmin, Power BI, Docker và xử lý lỗi.
2. [ERD.md](ERD.md): sơ đồ đầy đủ, khóa và lực lượng quan hệ.
3. [DATA_DICTIONARY.md](DATA_DICTIONARY.md): toàn bộ cột, kiểu, NULL và ý nghĩa.
4. [CV2_REPORT.md](CV2_REPORT.md): thiết kế, kiểm chứng, benchmark và giới hạn.
5. [HANDOFF.md](HANDOFF.md): hợp đồng đọc/ghi cho CV3/CV4.
6. [evidence/README.md](evidence/README.md): bằng chứng thực nghiệm đã commit.

Windows native đã kiểm thử với dữ liệu thật. Docker là phương án thay thế có
cấu hình, chưa kiểm thử end-to-end. Mỗi máy tự tạo database và mật khẩu riêng.

## Kết quả bàn giao

- [ERD](ERD.md): các thực thể và quan hệ.
- [DDL gốc](sql/001_schema.sql): Raw/Clean/Analytics, khóa và ràng buộc.
- [DDL Timescale](sql/002_timescale.sql): hypertable và continuous aggregate.
- [Công cụ nhập và kiểm tra](cli.py): COPY theo batch, SHA256, nhập lặp an toàn.
- [Truy vấn cho CV3](sql/queries.sql): truy vấn chuỗi, aggregate, rolling mean và nối theo ngày.
- [Hợp đồng bàn giao](HANDOFF.md): bảng, view, cột và cách ghi kết quả.
- `reports/`: báo cáo kiểm tra dữ liệu, đối chiếu database và benchmark thực tế.

## Ba tầng dữ liệu

| Tầng | Bảng chính | Ý nghĩa |
|---|---|---|
| Raw | `raw.file_archive`, `raw.import_batch` | Lưu nguyên byte của file, SHA256 và lịch sử nhập |
| Clean | `station`, `channel`, `quality_flag`, `measurement`, `earthquake_event`, `earthquake_daily` | Dữ liệu chuẩn hóa đã nhận từ CV1 |
| Analytics | `measurement_hourly`, `measurement_daily`, `model_run`, `filtered_series`, `forecast_result` | Aggregate và kết quả của CV3/CV4 |

**Repo hiện chỉ có ba file clean.** Chúng được lưu nguyên byte ở file_archive với
`source_stage='clean_handoff'`; không được coi là dữ liệu thô. Khi CV1 bàn giao
file gốc, đặt chúng dưới `data/raw/intermagnet/` và `data/raw/usgs/`, rồi chạy
`archive-raw`. Báo cáo verify luôn ghi rõ số file original_raw thực sự có.

## Chạy trên Windows không cần Docker

`windows-native.ps1` chạy PostgreSQL + TimescaleDB trong `database/.local/`,
không đăng ký dịch vụ Windows, không đổi cấu hình database khác, chỉ nghe ở
`127.0.0.1:5433`. Dữ liệu và mật khẩu trong `.local/` bị loại khỏi Git.

Mở PowerShell ở thư mục repo. Đây là quy trình dựng mới; database đã có chỉ
cần start. Nếu bị chặn script, dùng Set-ExecutionPolicy -Scope Process
-ExecutionPolicy Bypass -Force trong cửa sổ hiện tại; xem USAGE.md:

```powershell
.\database\windows-native.ps1 setup
.\database\windows-native.ps1 import
.\database\windows-native.ps1 verify
.\database\windows-native.ps1 test
.\database\windows-native.ps1 benchmark
.\database\windows-native.ps1 status
```

Nếu Python không nằm trong PATH, truyền `-PythonExecutable 'C:\...\python.exe'`
ở lần setup. Script ghi nhớ đường dẫn này. `start` mở lại database sau khi
khởi động lại máy; `stop` dừng database và giữ nguyên dữ liệu.

## Chạy bằng Docker

Máy cần Docker Desktop với Linux containers đang chạy. Chạy từ thư mục repo:

```powershell
.\database\manage.ps1 start
.\database\manage.ps1 inspect
.\database\manage.ps1 import
.\database\manage.ps1 verify
.\database\manage.ps1 test
.\database\manage.ps1 benchmark
```

Script tự sinh mật khẩu ngẫu nhiên trong `database/.env` nếu chưa có.
`docker compose stop` giữ volume dữ liệu. Không cần xóa database để chạy import
lần nữa. Không chạy hai phương án native/Docker đồng thời trên cùng cổng.

## Kết quả nhập kỳ vọng

| Dữ liệu | Số dòng vật lý/logical |
|---|---:|
| `clean.measurement` | 6.831.360 dòng vật lý = 1.707.840 phút × 4 kênh |
| `clean.kak_1min` | View khôi phục 1.707.840 dòng với 11 cột giống CV1 |
| `clean.earthquake_event` | 4.184 |
| `clean.earthquake_daily` | 1.186 |
| `analytics.measurement_hourly` | 113.856 = 1.186 ngày × 24 giờ × 4 kênh |
| `analytics.measurement_daily` | 4.744 = 1.186 ngày × 4 kênh |

Mỗi số đo giữ `quality_flag` của chính kênh và `source_quality_flag` tổng hợp
của dòng CV1. Các điểm spike/flatline vẫn ở Clean với giá trị gốc. Analytics
thống kê theo mặc định chỉ dùng cờ 0; `n_total` vẫn đếm tất cả mốc thời gian.

Import chạy trong transaction: lỗi ở bất kỳ file nào sẽ rollback cả lần nhập.
Snapshot có cùng source_kind và SHA256 sẽ được bỏ qua khi đã nhập. Snapshot
khác có khóa dữ liệu trùng sẽ bị từ chối, không tự ghi đè dữ liệu trước đó.
Bộ v1 dành cho chính snapshot CV1 hiện tại; khi thay phạm vi, cần cập nhật
preflight và thiết kế quản lý phiên bản trước khi nhập dữ liệu mới.

## Power BI và truy vấn

- Server: `localhost:5433`; database: `geopulse`.
- Tài khoản đọc: `geopulse_reader`; mật khẩu nằm trong `.local/credentials.json`
  (native) hoặc dòng `PG_READER_PASSWORD` trong `.env` (Docker).
- Chọn view ở schema `analytics`: `vw_signal`, `vw_earthquake_events`,
  `vw_earthquake_daily`, `vw_daily_context`, `vw_filtered_comparison`, `vw_forecast`.
- Chuỗi đầy đủ ở `vw_signal.original_value`; `strict_value` chỉ hiện điểm cờ 0.
- `cv1_display_value` giữ chính sách hiển thị của tài liệu bàn giao CV1: cờ
  1/2/4 thành NULL; cờ 3/5 vẫn hiển thị. Không dùng nó như chứng nhận chất lượng.

Các thời điểm đều là TIMESTAMPTZ; session UTC. Dùng khoảng nửa mở `[start,end)`.
Sự kiện USGS không có FK tới station vì động đất thuộc vùng rộng, không phải
số đo của KAK. Nối ngày chỉ cung cấp ngữ cảnh, không khẳng định quan hệ nhân quả.

## Index và partition

`measurement`, `filtered_series`, `forecast_result` là hypertable với chunk
thời gian cố định `interval '1 month'` (30 ngày), không phải partition theo tháng
lịch. PK luôn chứa cột thời gian của hypertable. PK measurement bắt đầu bằng
station/channel để hỗ trợ truy vấn một kênh theo khoảng thời gian. Index
`(station_code,time_utc DESC)` hỗ trợ truy vấn cả bốn kênh; partial index cho
điểm có cờ khác 0. Events và daily là bảng PostgreSQL thường vì số dòng nhỏ;
events có index thời gian và `(region,time_utc)`.

Continuous aggregate giờ/ngày được refresh đúng khoảng dữ liệu lịch sử sau
import. Không dùng policy chỉ refresh vài ngày gần hôm nay, vì sẽ bỏ sót dữ liệu
2023–2026. Lệnh `refresh` chạy lại an toàn khi có thêm kết quả nhập được hỗ trợ.
V1 không bật retention tự xóa dữ liệu hoặc compression.

## Kiểm chứng và benchmark

`inspect` đọc mọi dòng trong ba file, kiểm tra grid UTC, cờ, số lượng sự kiện và
thống kê theo từng ngày. `verify --full` đối chiếu mọi giá trị và cờ sau import
bằng staging có kiểu SQL giống dữ liệu đích, đồng thời kiểm tra SHA256 của
file lưu trữ, số dòng aggregate và ba hypertable. Không suy ra rằng SQL chạy
thành công chỉ vì parse được cú pháp.

`benchmark` dùng EXPLAIN ANALYZE BUFFERS trên database thật, một lần warmup và
năm lần đo. So sánh planner mặc định với baseline tắt các đường truy cập index
chỉ trong transaction, trên cùng hypertable và cùng chunk pruning. Đây là so
sánh đường truy cập, không phải hai database độc lập có/không index. Benchmark
cũng so sánh query aggregate trực tiếp với continuous aggregate và xác nhận
kết quả hai query khớp. Không xóa index hoặc bịa số liệu hiệu năng.

`test` kiểm tra ràng buộc và tài khoản đọc trên database thật. Các bản ghi thử
được tạo trong transaction và luôn rollback; không để lại kết quả lọc/dự báo giả.

## Nguồn kỹ thuật

- [TimescaleDB Docker chính thức](https://github.com/timescale/timescaledb-docker)
- [TimescaleDB 2.30.2 và gói Windows](https://github.com/timescale/timescaledb/releases/tag/2.30.2)
- [PostgreSQL Windows binaries](https://www.enterprisedb.com/download-postgresql-binaries)
- [create_hypertable](https://docs.timescale.com/api/latest/hypertable/create_hypertable/)
- [Continuous aggregate](https://docs.timescale.com/api/latest/continuous-aggregates/create_materialized_view/)
- [Psycopg COPY](https://www.psycopg.org/psycopg3/docs/basic/copy.html)
