# Báo cáo bàn giao CV2

Kiểm tra trên máy DELL ngày 07/10/2026 22:13 (giờ Việt Nam).

CV2 đã có database chạy với dữ liệu thật, ERD, DDL, công cụ import, các view
cho Power BI và báo cáo kiểm chứng. Dữ liệu thô gốc chưa có trong repo nên
tầng Raw vẫn cần bàn giao original_raw từ CV1; ba file clean hiện được lưu
nguyên byte với nhãn clean_handoff, không được gọi là dữ liệu thô.

## Môi trường đã chạy

- PostgreSQL 17.11; TimescaleDB 2.30.2.
- Database: `geopulse`; địa chỉ: `localhost:5433`.
- Chạy bản Windows trong `database/.local/`; không cài dịch vụ Windows.
- Chỉ nghe ở máy cục bộ; nhóm khác có thể dựng lại bằng bộ native hoặc Docker.
- Cấu hình Docker đã được rà soát và image tag đã được xác nhận; chưa chạy kiểm thử end-to-end bằng container. Số liệu bên dưới đều từ bản Windows.
- Tài khoản `geopulse_reader` đã kiểm tra quyền đọc Analytics, không ghi Clean.
- Mật khẩu nằm trong `.local/credentials.json`, đã xác nhận bị Git ignore.
- Dung lượng database tại thời điểm báo cáo: 976.4 MiB.

## Dữ liệu đã nhập và kiểm chứng

| Bảng | Số dòng sau khi dừng và mở lại database |
|---|---:|
| `clean.measurement` | 6,831,360 |
| `clean.earthquake_event` | 4,184 |
| `clean.earthquake_daily` | 1,186 |
| `analytics.measurement_hourly` | 113,856 |
| `analytics.measurement_daily` | 4,744 |

KAK được lưu theo dạng một giá trị/kênh/dòng: 1.707.840 phút × 4 kênh
= 6.831.360 measurement. View `clean.kak_1min` khôi phục 11 cột ban đầu.
Không xóa điểm spike/flatline; giữ cả giá trị và cờ từng kênh.

Tổng USGS: 4.184 sự kiện; 3.836 thuộc region Japan; 426 có M ≥ 5.
Bảng ngày có 86 ngày không có sự kiện, thống kê magnitude/độ sâu là NULL.

## Những kiểm tra đã đạt

- Đọc mọi dòng đầu vào; kiểm tra lưới UTC một phút và một ngày.
- Đối chiếu mọi giá trị và cờ của ba file Parquet với database bằng typed staging.
- Đối chiếu thống kê sự kiện theo từng ngày và tổng các continuous aggregate.
- Kiểm tra byte của file lưu trữ khớp SHA256 của file bàn giao.
- Chạy import lần hai: cả ba snapshot được bỏ qua; số dòng không đổi.
- Kiểm tra dữ liệu giữ nguyên sau khi dừng và mở lại database.
- Kiểm tra UPDATE/DELETE vào file archive bị từ chối.
- Kiểm tra PK, NULL/cờ, FK kênh và loại model_run; tài khoản chỉ đọc.

Các bảng cho nhóm sau hiện chưa có kết quả giả: model_run=0, filtered_series=0, forecast_result=0.

Bằng chứng đã đưa vào bản bàn giao: [evidence/2026-10-07](evidence/2026-10-07).
Báo cáo của các lần chạy mới nằm ở reports/ và được Git ignore mặc định.

## Hiệu năng đo trên database thật

| Trường hợp | Median execution time (ms), 5 lần đo |
|---|---:|
| Lấy kênh X trong một giờ, planner mặc định dùng index | 0.049 |
| Cùng truy vấn, baseline tắt đường truy cập index trong transaction | 41.679 |
| Tính mean giờ trực tiếp từ số đo X trong tháng 01/2024 | 13.892 |
| Đọc cùng kết quả từ continuous aggregate giờ | 1.377 |

Một lần warmup không tính vào kết quả. Hai đường truy cập dùng cùng
hypertable, cùng chunk pruning; không xóa index. Hai query aggregate đã
được kiểm tra có cùng kết quả. Đây là số đo cache ấm trên máy này, không
phải cam kết hiệu năng cho máy khác hoặc các khoảng thời gian khác.

Lần nhập đầu tiên: chuyển và ghi số đo KAK mất 317,80 giây; events 0,21
giây; daily 0,05 giây. Toàn bộ import, preflight, refresh và kiểm tra ban đầu
mất 356,30 giây. Full roundtrip verification mất 58,77 giây.

## Đầu ra giao cho nhóm

- `ERD.md`: sơ đồ quan hệ.
- `sql/001_schema.sql`, `sql/002_timescale.sql`: bảng, khóa, index, hypertable và aggregate.
- `HANDOFF.md`: hợp đồng bảng/cột cho CV3 và CV4.
- `sql/queries.sql`: truy vấn khởi đầu cho nhóm phân tích.
- `README.md`: hướng dẫn Windows/Docker và kết nối Power BI.

## Phần còn cần bàn giao từ CV1

File archive hiện lưu nguyên ba file clean_handoff; số file original_raw thực tế là 0.
Cần nhận file CSV/JSON gốc, đặt dưới data/raw/intermagnet và data/raw/usgs,
rồi chạy `windows-native.ps1 archive-raw`. Không tái tạo raw từ clean.
Các bảng filtered_series/forecast_result được CV3/CV4 điền sau khi thực sự
chạy lọc và mô hình. Hai bộ KAK/USGS ghép theo ngày chỉ cung cấp ngữ cảnh.

## SHA256 của ba file bàn giao

| File | SHA256 |
|---|---|
| `clean_intermagnet_KAK_1min_20230101_20260331.parquet` | `b1c73b49cab713ebeb5a8de3366f761fe07ddb6d8cca6ded4440acb6dbdbc11f` |
| `clean_usgs_JP_M4_20230101_20260331.parquet` | `a02c8d5b326c585c3e0655626b0f3955cab9987ea69773b0452759274d28c712` |
| `clean_usgs_JP_M4_daily_20230101_20260331.parquet` | `2b2ef30842604d5817887dc969532c9f4687b39dd5db6ecee860d4d4bc149e22` |


## Cơ sở thiết kế và lựa chọn công nghệ

Dữ liệu có cấu trúc ổn định, cần trạm/kênh/số đo, truy nguyên đợt nhập và
quản lý các lần chạy. Mô hình quan hệ phù hợp vì hỗ trợ khóa, FK, ràng buộc
và SQL tổng hợp/JOIN. PostgreSQL được chọn theo định hướng CV2, kết hợp
TimescaleDB cho hypertable và continuous aggregate. SQL Server/MySQL đều là
phương án khả thi; chưa benchmark giữa các hệ, không kết luận PostgreSQL nhanh nhất.
Nếu chỉ phân tích snapshot trên một máy thì Parquet + Python/DuckDB cũng hợp lý;
database phục vụ thêm mục tiêu mô hình hóa, phân quyền và bàn giao giữa các phần.

Tách ba schema theo vai trò. raw lưu nguồn và batch, clean lưu số đo chuẩn hóa,
analytics lưu tổng hợp và đầu ra. Không chạy lại QC CV1 hoặc sửa file CV1.
12 bảng và các thuộc tính đầy đủ ở [DATA_DICTIONARY.md](DATA_DICTIONARY.md).

## Ánh xạ dữ liệu CV1 sang CV2

| Nguồn CV1 | Đích | Biến đổi |
|---|---|---|
| KAK 11 cột | clean.measurement | Mỗi phút thành 4 dòng; float32 thành REAL; giữ cờ riêng và tổng hợp |
| USGS events 23 cột | clean.earthquake_event | Giữ đủ thuộc tính, thêm batch_id; float64 giữ double precision |
| USGS daily 7 cột | clean.earthquake_daily | Ngày UTC thành DATE, giữ thống kê và thêm batch_id |
| Nguyên byte ba file | raw.file_archive | SHA256, loại clean_handoff, nội dung và kích thước |

View clean.kak_1min dựng lại dạng rộng để người dùng/CV3 không buộc đổi cách đọc.
Thiết kế dạng dài là lựa chọn mở rộng kênh, không phải yêu cầu duy nhất đúng.

## Khóa, index và tổ chức thời gian

| Đối tượng | Thiết kế | Mục đích |
|---|---|---|
| measurement | PK (station_code,channel_code,time_utc) | Ngăn trùng, truy chuỗi một kênh |
| measurement_station_time_idx | (station_code,time_utc DESC) | Lấy các kênh của trạm trong khoảng thời gian |
| measurement_flagged_idx | (station_code,channel_code,time_utc DESC), quality_flag<>0 | Tìm điểm đã gắn cờ |
| earthquake_time_idx | (time_utc DESC) | Lấy sự kiện theo khoảng thời gian |
| earthquake_region_time_idx | (region,time_utc DESC) | Lọc vùng và thời gian |
| filtered_series_station_time_idx | (station_code,channel_code,time_utc DESC) | Tra chuỗi đã lọc |
| forecast_station_time_idx | (station_code,channel_code,target_time DESC) | Tra kết quả dự báo |

TimescaleDB chuyển measurement, filtered_series, forecast_result thành hypertable.
Chunk interval khai báo 1 month được TimescaleDB chuẩn hóa thành 30 ngày cố định;
không tuyên bố partition theo tháng lịch. Event/daily nhỏ nên là bảng thường.
Các index tự tạo bởi hypertable/continuous aggregate bổ sung cho index khai báo.
Benchmark cho thấy planner có thể chọn index thời gian do TimescaleDB tạo, không
chứng minh mọi truy vấn đều dùng composite index tự khai báo.

Aggregate nhóm theo trạm/kênh/giờ hoặc ngày UTC. n_total đếm đủ điểm;
mean/min/max/stddev chỉ dùng quality_flag=0. Refresh toàn khoảng lịch sử sau import,
không có policy tự refresh, compression hoặc retention xóa dữ liệu.
Tổng hợp tháng dùng trọng số n_ok, không lấy trung bình không trọng số của các mean ngày.

## Import, giao dịch và phân quyền

Preflight kiểm tra tất cả file trước khi COPY theo batch. Một transaction bao
phủ lần nhập; lỗi rollback lần nhập. Advisory lock tuần tự hóa import/archive.
Cùng source_kind/SHA256 bỏ qua snapshot cũ; khác snapshot trùng PK bị từ chối.
Archive không cho sửa/xóa bằng thao tác thông thường; admin vẫn có quyền quản trị
cấu trúc và có thể bỏ trigger, nên không gọi đây là kho chống can thiệp tuyệt đối.

Reader có USAGE/SELECT trên clean và analytics, không ghi hoặc đọc raw.
Mỗi máy tự tạo mật khẩu trong .local/credentials.json hoặc .env, đều không commit.
Các kết quả thử nghiệm của integration_checks.py được rollback; không tạo dự báo giả.

## Vận hành và giới hạn bản bàn giao

- Hướng dẫn dựng mới/mở lại/pgAdmin/Power BI/Docker/backup: [USAGE.md](USAGE.md).
- DDL CV1 trong docs/database là gợi ý nguồn; dùng DDL ở database/sql cho CV2.
- V1 kiểm tra snapshot KAK/USGS đúng giai đoạn 2023-01-01 đến hết 2026-03-31.
  Thêm trạm, khoảng thời gian hoặc snapshot mới cần thiết kế/versioning tiếp.
- Mỗi model_run một trạm/kênh; chưa hỗ trợ một run nhiều kênh hoặc nhiều forecast
  origins có dự báo trùng target_time trong cùng run.
- input_series là text, chưa có FK truy chuỗi các run hoặc hash code mô hình.
- Chưa có backup tự động, chưa diễn tập full restore, chưa triển khai server dùng chung.
- Docker chưa được kiểm thử end-to-end; không dùng số đo native để chứng minh Docker.
- Một trạm KAK, vùng USGS rộng, magnitude trộn loại; không kết luận tương quan/nhân quả
  hoặc khả năng dự báo động đất từ việc ghép theo ngày.
- original_raw còn thiếu; filter/forecast/metrics chờ kết quả thực tế từ nhóm sau.

## Tài liệu kỹ thuật tham chiếu

- [PostgreSQL: mô hình quan hệ](https://www.postgresql.org/docs/17/tutorial-concepts.html).
- [TimescaleDB: hypertables](https://www.tigerdata.com/docs/reference/timescaledb/hypertables).
- [TimescaleDB: continuous aggregates](https://www.tigerdata.com/docs/learn/continuous-aggregates).
- [Psycopg COPY](https://www.psycopg.org/psycopg3/docs/basic/copy.html).
- [Docker volumes](https://docs.docker.com/engine/storage/volumes/).

## Kiểm tra lại trước khi push

Ngày 08/10/2026 17:04 (UTC+7), chạy lại full verification trên database
Windows đang dùng: toàn bộ giá trị và cờ khớp ba file CV1; số dòng, SHA256,
đối chiếu event/day và hypertable đạt. Thời gian chạy lần này 41,38 giây.
10 kiểm tra hợp đồng/ràng buộc/quyền đều đạt, fixtures được rollback.
Bằng chứng: [verification_full.json](evidence/2026-10-08/verification_full.json),
[contract_checks.json](evidence/2026-10-08/contract_checks.json).
Benchmark vẫn là kết quả ngày 07/10/2026; không gán thời gian kiểm tra mới
cho số liệu benchmark cũ. Không sửa pipeline hoặc dữ liệu CV1.
