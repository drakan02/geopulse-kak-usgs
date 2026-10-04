# Data Dictionary – SOP-01 Geophysical Data Pipeline

> Tạo tự động bởi `step3_process.py`. Cập nhật khi schema thay đổi.

## File sản phẩm

`data/clean/clean_intermagnet_{STATION}_1min_{start}_{end}.parquet`

## Schema cột

| Cột | Kiểu | Đơn vị | Mô tả |
|---|---|---|---|
| `time_utc` | `datetime64[us, UTC]` | – | Dấu thời gian UTC, ISO 8601, bắt đầu mỗi phút |
| `station` | `category` | – | Mã IAGA 3 ký tự (ví dụ: `KAK`) |
| `x_nt` | `float32` | nT | Thành phần X (Bắc). Sentinel → NaN. Giá trị thật giữ nguyên |
| `y_nt` | `float32` | nT | Thành phần Y (Đông). Sentinel → NaN |
| `z_nt` | `float32` | nT | Thành phần Z (Thẳng đứng, xuống). Sentinel → NaN |
| `f_nt` | `float32` | nT | Cường độ toàn phần F. Sentinel → NaN |
| `flag_x` | `int8` | – | Cờ chất lượng riêng cho x_nt (xem bảng mã) |
| `flag_y` | `int8` | – | Cờ chất lượng riêng cho y_nt |
| `flag_z` | `int8` | – | Cờ chất lượng riêng cho z_nt |
| `flag_f` | `int8` | – | Cờ chất lượng riêng cho f_nt |
| `quality_flag` | `int8` | – | Cờ tổng hợp = max(flag_x, flag_y, flag_z, flag_f) |

## Bảng mã quality_flag

| Mã | Tên | Điều kiện | Ghi chú |
|---|---|---|---|
| `0` | OK | Giá trị hợp lệ, không vấn đề | Dùng được trực tiếp |
| `1` | MISSING | NaN sau reindex (timestamp thiếu trong raw) | Không nội suy nếu gap > 5 phút |
| `2` | SENTINEL | Giá trị fill ([99999.0, 88888.0]) trong file gốc | Giữ lịch sử; giá trị đã thay bằng NaN ở cột đo |
| `3` | SPIKE | \|diff\| > 5.0σ của diff (sau khi loại sentinel) | **Không xoá**; có thể là biến thiên địa từ thật trong bão từ |
| `4` | OUT_OF_RANGE | Ngoài khoảng vật lý hợp lệ | Xem `config.PHYSICAL_BOUNDS` |
| `5` | FLATLINE | ≥ 10 điểm liên tiếp cùng giá trị | **Không xoá**; gắn cờ để cảnh báo |

> Nếu một điểm thuộc nhiều loại → cờ LỚN NHẤT được lưu (flatline > out-of-range > spike > sentinel > missing > OK).

## Khoảng vật lý hợp lệ (PHYSICAL_BOUNDS)

Nguồn: INTERMAGNET technical guide + WMM khu vực KAK (~36.2°N, 140.2°E)

| Cột | Min (nT) | Max (nT) |
|---|---|---|
| x_nt | 20,000 | 50,000 |
| y_nt | -5,000 | 10,000 |
| z_nt | 20,000 | 60,000 |
| f_nt | 35,000 | 65,000 |

## Ngưỡng kiểm tra chất lượng

| Tham số | Giá trị |
|---|---|
| Sentinel | [99999.0, 88888.0] |
| SPIKE_K | 5.0σ |
| FLATLINE_N | 10 điểm liên tiếp |
| INTERP_MAX_GAP | 5 phút |

## Nguồn dữ liệu

| Trường | Giá trị |
|---|---|
| Trạm | ['KAK'] |
| Loại | quasi-definitive |
| Khoảng | 2023-01-01 → 2026-03-31 |
| HAPI dataset | `kak/quasi-def/PT1M/xyzf` |
| HAPI URL | `https://imag-data.bgs.ac.uk/GIN_V1/hapi` |

---
*Cập nhật lần cuối: 2026-10-05*
