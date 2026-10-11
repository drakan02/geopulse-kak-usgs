# Hướng dẫn sử dụng CV2

## 1. Chọn cách chạy

Database của mỗi thành viên là một bản riêng. Clone GitHub chỉ lấy thiết kế,
script và ba file Parquet; không lấy database đang chạy hoặc mật khẩu của máy khác.

| Phương án | Điều kiện | Trạng thái kiểm chứng |
|---|---|---|
| Windows native | Windows x64, Python 3.12 có pip, Internet ở lần setup đầu | Đã chạy với PostgreSQL 17.11, TimescaleDB 2.30.2, Python 3.12.14 |
| Docker Compose | Docker Desktop hỗ trợ Linux containers và Compose v2 đang chạy | Có cấu hình; chưa kiểm thử toàn bộ quy trình bằng container |

Chỉ chạy một phương án trên cổng 5433. pgAdmin là giao diện quản lý, không
thay thế PostgreSQL. Chạy PowerShell bằng tài khoản Windows bình thường.
Không cần chạy lại pipeline CV1 hoặc tải lại dữ liệu để dùng snapshot đã bàn giao.

## 2. Dựng mới trên Windows

Clone repo bằng GitHub Desktop, chọn nhánh CV2, rồi mở Windows PowerShell.
Thay đường dẫn repo dưới đây bằng đường dẫn clone trên máy của bạn:

```powershell
Set-Location 'D:\Documents\geopulse-kak-usgs'
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
python --version
```

Nếu Python chưa dùng được, cài Python 3.12 x64 có pip, mở lại PowerShell.
Nếu Python không có trong PATH, tìm đường dẫn thật tới python.exe và truyền
`-PythonExecutable` vào lệnh setup. Không dùng đường dẫn Python của máy người khác.

```powershell
& .\database\windows-native.ps1 setup
& .\database\windows-native.ps1 inspect
& .\database\windows-native.ps1 import
& .\database\windows-native.ps1 verify
& .\database\windows-native.ps1 test
& .\database\windows-native.ps1 benchmark
```

Setup tải các gói PostgreSQL/TimescaleDB chính thức, cài thư viện vào `.local/`,
tạo mật khẩu riêng và khởi động database. Import tạo dữ liệu từ ba file trong
`data/clean/`, lưu nguyên file, nhập các dòng và refresh tổng hợp giờ/ngày.
`verify` qua wrapper Windows luôn đối chiếu toàn bộ giá trị và cờ với Parquet.
Lần dựng mới cần tải các gói cài đặt và chừa dung lượng cho chúng cùng database;
database mẫu đo được khoảng 976,4 MiB, chưa tính các gói/bản sao lưu.

Ví dụ khi cần truyền đường dẫn Python (thay bằng đường dẫn có thật):

```powershell
& .\database\windows-native.ps1 setup -PythonExecutable 'C:\duong-dan-python\python.exe'
```

Không chạy lệnh ví dụ với đường dẫn giả. `setup` ghi nhớ Python của máy đó.

## 3. Mở lại database đã có

Mở PowerShell tại repo, rồi chạy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\database\windows-native.ps1 start
& .\database\windows-native.ps1 status
```

Thông báo kỳ vọng: `Running: localhost:5433/geopulse`.
Không cần setup hoặc import lại mỗi lần mở máy. Không có dịch vụ Windows tự
khởi động trong bản native. Có thể đóng PowerShell sau khi start thành công.

Dừng an toàn, giữ nguyên dữ liệu:

```powershell
& .\database\windows-native.ps1 stop
```

Wrapper chạy trực tiếp trong PowerShell, không cần gọi `powershell.exe` theo tên.
Chính sách `Scope Process` hết hiệu lực khi đóng cửa sổ.

## 4. Kết nối bằng pgAdmin

1. Tải và cài [pgAdmin cho Windows](https://www.pgadmin.org/download/pgadmin-4-windows/).
2. Khởi động database theo mục 3; mở pgAdmin 4.
3. Nếu pgAdmin hỏi Master Password, tự đặt mật khẩu bảo vệ thông tin kết nối;
   đây không phải mật khẩu database.
4. Dùng File Explorer mở `database/.local/credentials.json` bằng Notepad.
   Lấy giá trị `reader_password`; không lấy dấu ngoặc kép hoặc dấu phẩy.
5. Nhấp phải **Servers → Register → Server**.
6. Tab **General**: Name = `GeoPulse`.
7. Tab **Connection**: điền theo bảng và bấm **Save**.

| Mục | Giá trị |
|---|---|
| Host name/address | `127.0.0.1` |
| Port | `5433` (không phải mặc định 5432) |
| Maintenance database | `geopulse` |
| Username | `geopulse_reader` |
| Password | `reader_password` của chính máy này |

Mở **Servers → GeoPulse → Databases → geopulse → Schemas → clean → Tables**.
Nhấp phải `earthquake_event` → **View/Edit Data → First 100 Rows**.
Để xem KAK giống file CV1: vào **clean → Views → kak_1min**, xem 100 dòng đầu.
Các continuous aggregate nằm trong **analytics → Materialized Views**.
Không chọn All Rows để xem thử bảng measurement có hơn 6 triệu dòng.

Để quản trị, tạo kết nối riêng với username `geopulse`, mật khẩu `admin_password`.
Reader chỉ đọc Clean/Analytics; không đọc Raw và không ghi dữ liệu.
Không đưa credentials.json lên GitHub hoặc dùng chung tài khoản quản trị.

## 5. Dựng bằng Docker (phương án thay thế, chưa kiểm thử end-to-end)

Dừng database native trước. Mở Docker Desktop ở chế độ Linux containers,
mở PowerShell tại repo và xác nhận `docker compose version` chạy được.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\database\manage.ps1 start
& .\database\manage.ps1 inspect
& .\database\manage.ps1 import
& .\database\manage.ps1 verify
& .\database\manage.ps1 test
& .\database\manage.ps1 benchmark
```

Wrapper tự tạo `database/.env` nếu chưa có. Với Docker, pgAdmin dùng cùng
host/port/database/username reader ở mục 4 nhưng lấy `PG_READER_PASSWORD`
trong `.env`. Admin lấy `POSTGRES_PASSWORD`. Mỗi máy có mật khẩu riêng.

Image mặc định `timescale/timescaledb:2.30.2-pg17`; `pg17` cố định dòng major,
chưa cố định chính xác minor hoặc digest. Tools dùng Python 3.12 và các thư viện
khóa phiên bản trong requirements.txt. Chưa tuyên bố môi trường Docker tái hiện
từng byte hoặc hiệu năng giống bản Windows.

```powershell
& .\database\manage.ps1 status
& .\database\manage.ps1 stop
```

Dữ liệu Docker ở named volume `geopulse_data`; stop giữ dữ liệu.
Không dùng `docker compose down -v` khi cần giữ database: tùy chọn đó xóa volume.
Không gắn thư mục pgdata Windows vào container Linux để chuyển dữ liệu.
Không đổi mật khẩu trong .env rồi kỳ vọng tài khoản PostgreSQL của volume đã
khởi tạo tự đổi theo; giữ cấu hình hoặc đổi mật khẩu bằng thao tác quản trị phù hợp.

## 6. Kết nối Power BI và bàn giao cho CV3/CV4

Power BI Desktop → Get Data → PostgreSQL database:
Server = `localhost:5433`, Database = `geopulse`, xác thực bằng geopulse_reader.
Chọn `analytics.vw_signal`, `vw_earthquake_events`, `vw_earthquake_daily`,
`vw_daily_context`, `vw_filtered_comparison` hoặc `vw_forecast`.
Lọc trạm/kênh/khoảng thời gian trước khi tải chuỗi lớn khi công cụ hỗ trợ.

CV3/CV4 đọc [HANDOFF.md](HANDOFF.md) để biết cách tạo run_id và ghi kết quả.
Các bảng kết quả ban đầu rỗng là đúng: chưa có kết quả thực nghiệm để nhập.
Nếu không dùng máy này, dựng database riêng hoặc thống nhất một server chung;
`localhost` của mỗi người chỉ chính máy người đó. Bản mặc định chỉ nghe localhost.

## 7. Kiểm tra dữ liệu và lưu raw

Số dòng kỳ vọng:

| Đối tượng | Số dòng |
|---|---:|
| clean.measurement | 6.831.360 |
| clean.kak_1min (view) | 1.707.840 |
| clean.earthquake_event | 4.184 |
| clean.earthquake_daily | 1.186 |
| analytics.measurement_hourly | 113.856 |
| analytics.measurement_daily | 4.744 |

Import lại đúng ba file sẽ bỏ qua snapshot đã nhập. Nếu file đã thay đổi nhưng
trùng khóa dữ liệu, công cụ từ chối; không tự ghi đè snapshot cũ.
Không dùng import để cập nhật tùy ý các khoảng thời gian hoặc trạm mới.

Khi CV1 cung cấp file raw gốc, đặt dưới `data/raw/intermagnet/` hoặc
`data/raw/usgs/`, rồi chạy wrapper với `archive-raw`. Công cụ nhận CSV, JSON,
GeoJSON, TXT; chỉ lưu nguyên byte và provenance, không tự làm sạch lại.
Không đổi nhãn file clean thành raw. Hiện original_raw = 0.

## 8. Sao lưu và khôi phục

Chưa có sao lưu tự động. Dùng pgAdmin bằng tài khoản quản trị, nhấp phải
database geopulse → Backup, chọn Custom và lưu ngoài repo. Bản sao lưu có dữ
liệu thật; không commit mặc định. Với native, nếu pgAdmin yêu cầu PostgreSQL
binary path, chỉ tới thư mục tuyệt đối `database/.local/pgsql/bin` trên máy đó.

Khôi phục sang database riêng đã có TimescaleDB tương thích. Với bản backup
TimescaleDB dùng quy trình pre_restore/post_restore theo
[tài liệu backup/restore](https://docs.tigerdata.com/self-hosted/latest/backup-and-restore/).
Chưa diễn tập khôi phục full database; sau restore cần chạy verify để xác nhận.
Không sao chép nóng thư mục pgdata để thay cho bản backup hợp lệ.

## 9. Xử lý lỗi thường gặp

| Lỗi | Cách xử lý |
|---|---|
| powershell.exe not recognized | Chạy trực tiếp `& .\database\windows-native.ps1 start` trong PowerShell |
| Script execution is disabled | Chạy Set-ExecutionPolicy Scope Process như mục 2 |
| Provide -PythonExecutable | Kiểm tra đường dẫn Python của máy; truyền vào setup |
| Connection refused | Kiểm tra status, start, host 127.0.0.1 và port 5433 |
| Port 5433 is in use | Dừng bản native/Docker còn lại; không chạy hai bản cùng cổng |
| Password authentication failed | Chọn đúng reader/admin và đúng file mật khẩu của phương án đang chạy |
| Không thấy kak_1min | Tìm trong Views, không phải Tables; Refresh cây đối tượng |
| Thiếu file đầu vào hoặc SHA khác | Dùng đúng ba file CV1; xem báo cáo và không bỏ qua preflight |
| Docker không kết nối được daemon | Mở Docker Desktop, kiểm tra Linux containers và Compose v2 |

## 10. GitHub chứa gì?

Commit tài liệu, DDL, script, cấu hình mẫu và bằng chứng kiểm thử đã chọn lọc.
Không commit `.local/`, `.env`, mật khẩu, pgdata, Docker volume hoặc backup.
Đóng pgAdmin/Docker không phải điều kiện để commit/push. Git không đồng bộ
các bản ghi được thêm bằng pgAdmin. Các kết quả CV3/CV4 cần bàn giao riêng
bằng file, backup phù hợp hoặc server dùng chung.

Tài liệu giao diện: [Server dialog](https://www.pgadmin.org/docs/pgadmin4/latest/server_dialog.html),
[View/Edit Data](https://www.pgadmin.org/docs/pgadmin4/latest/editgrid.html).
