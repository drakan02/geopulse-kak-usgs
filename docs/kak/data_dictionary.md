# Từ điển Dữ liệu – SOP-01 Geophysical Data Pipeline

> Nguồn dữ liệu: INTERMAGNET HAPI (Trạm KAK - Kakioka, Nhật Bản | 36.232° N, 140.186° E) + Danh mục Động đất USGS  
> Khoảng thời gian: 2023-01-01 đến 2026-03-31  

---

## 1. Thông số Sản phẩm File

| Thuộc tính | Quy cách kỹ thuật |
|---|---|
| Mẫu tên file | `clean_intermagnet_KAK_1min_20230101_20260331.parquet` |
| Định dạng lưu trữ | Apache Parquet (Nén Snappy, Engine PyArrow) |
| Lưới thời gian | Lưới 1 phút liên tục (ISO 8601 UTC) |
| Tổng số dòng kỳ vọng | 1,707,840 bản ghi |

---

## 2. Schema Cột Dữ liệu

| Cột | Kiểu dữ liệu | Đơn vị | Mô tả | Khoảng hợp lệ / Định dạng | Ghi chú |
|---|---|---|---|---|---|
| `time_utc` | `datetime64[us, UTC]` | - | Mốc thời gian UTC, độ phân giải 1 phút | ISO 8601 UTC | Khóa chính; tăng đơn điệu, không trùng lặp |
| `station` | `category` | - | Mã trạm IAGA 3 ký tự | `KAK` | Nguồn: Header IAGA-2002 |
| `x_nt` | `float32` | nT | Thành phần địa từ X (hướng Bắc) | 20,000 đến 50,000 nT | Sentinel 99999.00 / 88888.00 thay bằng NaN |
| `y_nt` | `float32` | nT | Thành phần địa từ Y (hướng Đông) | -5,000 đến 10,000 nT | Sentinel 99999.00 / 88888.00 thay bằng NaN |
| `z_nt` | `float32` | nT | Thành phần địa từ Z (hướng xuống) | 20,000 đến 60,000 nT | Sentinel 99999.00 / 88888.00 thay bằng NaN |
| `f_nt` | `float32` | nT | Cường độ từ trường tổng F | 35,000 đến 65,000 nT | Sentinel 99999.00 / 88888.00 thay bằng NaN |
| `flag_x` | `int8` | - | Cờ chất lượng cho thành phần x_nt | 0 đến 5 | Xem chi tiết bảng mã cờ chất lượng |
| `flag_y` | `int8` | - | Cờ chất lượng cho thành phần y_nt | 0 đến 5 | Xem chi tiết bảng mã cờ chất lượng |
| `flag_z` | `int8` | - | Cờ chất lượng cho thành phần z_nt | 0 đến 5 | Xem chi tiết bảng mã cờ chất lượng |
| `flag_f` | `int8` | - | Cờ chất lượng cho thành phần f_nt | 0 đến 5 | Xem chi tiết bảng mã cờ chất lượng |
| `quality_flag` | `int8` | - | Cờ tổng hợp = max(flag_x, flag_y, flag_z, flag_f) | 0 đến 5 | Đại diện cho mức độ bất thường cao nhất |

---

## 3. Phân loại Cờ Chất lượng (Quality Flag)

| Mã cờ | Tên cờ | Điều kiện phát hiện | Quy tắc xử lý | Độ ưu tiên |
|---|---|---|---|---|
| `0` | OK | Giá trị đo gốc hợp lệ | Giữ nguyên dữ liệu cho phân tích | 0 (Thấp nhất) |
| `1` | INTERP | Nội suy tuyến tính (gap <= 5 phút) | Điền giá trị nội suy từ 2 biên gap | 1 |
| `2` | MISSING | Thiếu dữ liệu hoặc sentinel ([99999.0, 88888.0]) | Gắn giá trị đo thành NaN | 2 |
| `3` | SPIKE | Spike biến thiên thống kê (|diff| > 5.0*std) | Chỉ gắn cờ; giữ nguyên giá trị đo gốc | 3 |
| `4` | OUT_OF_RANGE | Vi phạm ngưỡng vật lý hợp lệ | Chỉ gắn cờ; giữ nguyên giá trị đo gốc | 4 |
| `5` | FLATLINE | Chuỗi hằng số liên tiếp >= 10 điểm | Chỉ gắn cờ; nghi ngờ lỗi cảm biến | 5 (Cao nhất) |

Ghi chú: Nếu một điểm đo vi phạm nhiều điều kiện, mã cờ có số lớn nhất sẽ được lưu.

---

## 4. Ngưỡng Vật lý Hợp lệ (Mô hình WMM cho Trạm KAK, Nhật Bản)

Tham chiếu: Mô hình Từ trường Thế giới (WMM2020) và Tài liệu Kỹ thuật INTERMAGNET cho Đài thiên văn Kakioka (36.232° N, 140.186° E, Độ cao: 36m).

| Thành phần | Min (nT) | Max (nT) | Baseline tiêu biểu KAK | Cơ sở tham chiếu |
|---|---|---|---|---|
| `x_nt` | 20,000 | 50,000 | ~29,500 nT | Ngưỡng trường khu vực WMM2020 (Kakioka, Nhật Bản) |
| `y_nt` | -5,000 | 10,000 | ~-3,100 nT | Ngưỡng trường khu vực WMM2020 (Kakioka, Nhật Bản) |
| `z_nt` | 20,000 | 60,000 | ~35,800 nT | Ngưỡng trường khu vực WMM2020 (Kakioka, Nhật Bản) |
| `f_nt` | 35,000 | 65,000 | ~46,500 nT | Ngưỡng trường khu vực WMM2020 (Kakioka, Nhật Bản) |

---

## 5. Tham số Ngưỡng Kiểm tra Chất lượng

| Tham số | Tên biến cấu hình | Giá trị cấu hình | Ý nghĩa vận hành |
|---|---|---|---|
| Giá trị Sentinel | `SENTINEL_VALUES` | [99999.0, 88888.0] | Mã đánh dấu dữ liệu thiếu theo tiêu chuẩn IAGA-2002 |
| Độ nhạy Spike | `SPIKE_K` | 5.0 sigma | Hệ số nhân với độ lệch chuẩn của sai phân bậc nhất |
| Độ dài tối thiểu Flatline | `FLATLINE_N` | 10 điểm liên tiếp | Số điểm liên tiếp tối thiểu có cùng giá trị đo |
| Khoảng Gap nội suy tối đa | `INTERP_MAX_GAP` | 5 phút | Giới hạn gap thiếu tối đa được phép nội suy tuyến tính |

---

## 6. Nguồn Dữ liệu & Metadata Nguồn

| Thuộc tính | Giá trị |
|---|---|
| Mã trạm IAGA | KAK |
| Vị trí đài thiên văn | Kakioka, Ibaraki, Nhật Bản (36.232° N, 140.186° E) |
| Phân loại dữ liệu | quasi-definitive |
| HAPI Provider URL | `https://imag-data.bgs.ac.uk/GIN_V1/hapi` |
| HAPI Dataset ID | `kak/quasi-def/PT1M/xyzf` |

---
*Tài liệu được tạo tự động bởi mô-đun xuất dữ liệu pipeline (src/kak/process.py).*
