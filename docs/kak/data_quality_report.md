# Báo cáo Chất lượng Dữ liệu – SOP-01 Geophysical Data Pipeline

> Trạm: KAK (Đài thiên văn Kakioka, Nhật Bản | 36.232° N, 140.186° E)  
> Phân loại dữ liệu: quasi-definitive  
> Khoảng thời gian: 2023-01-01 đến 2026-03-31 (Lưới 1 phút)  

---

## 1. Tóm tắt Thực thi & Hạn chế Dữ liệu

1. Bối cảnh địa lý trạm: Trạm KAK đặt tại Kakioka, Nhật Bản (36.232° N, 140.186° E). Đặc trưng cường độ và biến thiên địa từ phản ánh đặc tính địa từ vĩ độ trung bình Bán cầu Bắc và đóng vai trò dữ liệu tham chiếu.
2. Phạm vi quan sát đơn trạm: Quy trình kiểm tra chất lượng được thực hiện trên chuỗi thời gian của một đài thiên văn duy nhất; chưa thực hiện so sánh chéo không gian với các trạm lân cận trong mô-đun này.
3. Trạng thái hiệu chỉnh Quasi-Definitive: Dữ liệu Quasi-definitive (QD) đã qua hiệu chỉnh baseline sơ bộ bởi Đài Kakioka nhưng đại diện cho chuỗi dữ liệu trước khi có phê duyệt Definitive chính thức hàng năm.
4. Phạm vi thời gian & Cắt chuỗi: Chuỗi dữ liệu bao phủ từ 2023-01-01 00:00:00 UTC đến 2026-03-31 23:59:00 UTC (1,707,840 bản ghi). Tháng 04/2026 đạt tỷ lệ khả dụng 90.00% (ngưỡng giáp ranh) được tạm dừng chờ xác nhận.

---

## 2. Tổng quan Dữ liệu & Thống kê Mô tả

### 2.1 Thuộc tính Dữ liệu Chính

| Thuộc tính | Giá trị định lượng |
|---|---|
| Tổng số bản ghi (sau reindex) | 1,707,840 dòng |
| Ngày bắt đầu | 2023-01-01 00:00:00+0000 |
| Ngày kết thúc | 2026-03-31 23:59:00+0000 |
| Tần số lấy mẫu | 1 phút (lưới liên tục) |
| HAPI Dataset ID | `kak/quasi-def/PT1M/xyzf` |

### 2.2 Thống kê Mô tả Dữ liệu Sạch (nT)

| Chỉ số thống kê | x_nt (Hướng Bắc) | y_nt (Hướng Đông) | z_nt (Hướng xuống) | f_nt (Cường độ tổng F) |
|---|---|---|---|---|
| Số lượng (Count) | 1,707,840 | 1,707,840 | 1,707,840 | 1,707,840 |
| Trung bình (Mean) | 29824.59 | -4158.25 | 35964.00 | 46906.36 |
| Độ lệch chuẩn (Std Dev) | 25.96 | 27.10 | 35.62 | 33.50 |
| Nhỏ nhất (Min) | 29399.01 | -4425.70 | 35790.00 | 46520.90 |
| Phân vị 25% | 29815.06 | -4177.99 | 35933.50 | 46882.50 |
| Trung vị (50% Median) | 29828.84 | -4158.81 | 35963.30 | 46906.40 |
| Phân vị 75% | 29840.01 | -4138.75 | 35995.00 | 46932.90 |
| Lớn nhất (Max) | 29944.88 | -4023.57 | 36108.80 | 47086.60 |

---

## 3. Chỉ số Chất lượng Trước & Sau Xử lý

### 3.1 Thiếu Giá trị và Sentinel

| Thành phần | Sentinel trước xử lý | NaN trước xử lý | Tổng NaN sau xử lý | Tỷ lệ thiếu sau xử lý |
|---|---|---|---|---|
| `x_nt` | 0 | 0 | 0 | 0.0000% |
| `y_nt` | 0 | 0 | 0 | 0.0000% |
| `z_nt` | 0 | 0 | 0 | 0.0000% |
| `f_nt` | 0 | 0 | 0 | 0.0000% |

### 3.2 Tính Toàn vẹn Timestamp & Độ Đầy đủ của Lưới

| Tiêu chí kiểm tra | Chỉ số trước xử lý | Chỉ số sau xử lý | Trạng thái |
|---|---|---|---|
| Timestamp trùng lặp | 0 bản ghi trùng | 0 bản ghi trùng | Đạt |
| Điểm thiếu trên lưới (Gap) | 0 điểm thiếu | 0 điểm thiếu | Đạt |
| Gap thiếu dài nhất | 0 phút | 0 phút | Đạt |

### 3.3 Kiểm tra Ngưỡng Vật lý

| Thành phần | Khoảng vật lý hợp lệ [Min, Max] (nT) | Vi phạm trước xử lý | Số điểm gắn cờ 4 sau xử lý |
|---|---|---|---|
| `x_nt` | [20,000, 50,000] | 0 | 0 |
| `y_nt` | [-5,000, 10,000] | 0 | 0 |
| `z_nt` | [20,000, 60,000] | 0 | 0 |
| `f_nt` | [35,000, 65,000] | 0 | 0 |

### 3.4 Phát hiện Spike Thống kê (Cờ 3)

Điều kiện ngưỡng: |diff(t)| > 5.0 * std(diff), tính toán sau khi loại bỏ sentinel/NaN.

| Thành phần | Ngưỡng động (nT) | Số lượng Spike phát hiện | Tỷ lệ trên tổng dữ liệu | Mẫu mốc thời gian UTC thực tế (Dẫn chứng) |
|---|---|---|---|---|
| `x_nt` | 2.534 | 7,603 | 0.4452% | `2023-01-04T02:30Z, 2023-01-04T02:50Z, 2023-01-04T02:51Z` |
| `y_nt` | 2.04 | 7,762 | 0.4545% | `2023-01-15T23:10Z, 2023-01-15T23:42Z, 2023-01-15T23:51Z` |
| `z_nt` | 1.491 | 8,392 | 0.4914% | `2023-01-01T14:59Z, 2023-01-01T15:00Z, 2023-01-04T02:30Z` |
| `f_nt` | 2.662 | 7,970 | 0.4667% | `2023-01-01T14:59Z, 2023-01-04T02:30Z, 2023-01-04T02:50Z` |

### 3.5 Phát hiện Chuỗi Flatline (Cờ 5)

Điều kiện ngưỡng: Chuỗi hằng số liên tiếp >= 10 điểm.

| Thành phần | Số đoạn trước xử lý | Độ dài tối đa (Phút) | Số điểm bị gắn cờ sau xử lý | Tỷ lệ trên tổng dữ liệu |
|---|---|---|---|---|
| `x_nt` | 3 | 11 | 31 | 0.0018% |
| `y_nt` | 3 | 11 | 31 | 0.0018% |
| `z_nt` | 176 | 21 | 2,048 | 0.1199% |
| `f_nt` | 32 | 15 | 366 | 0.0214% |

---

## 4. Ma trận Phân phối Cờ Chất lượng Sau Xử lý

| Mã cờ | Tên cờ | x_nt | y_nt | z_nt | f_nt | Cờ tổng hợp | Tỷ lệ phần trăm |
|---|---|---|---|---|---|---|---|
| `0` | OK | 1,700,206 | 1,700,047 | 1,697,400 | 1,699,504 | 1,690,346 | 98.9757% |
| `1` | INTERP | 0 | 0 | 0 | 0 | 0 | 0.0000% |
| `2` | MISSING | 0 | 0 | 0 | 0 | 0 | 0.0000% |
| `3` | SPIKE | 7,603 | 7,762 | 8,392 | 7,970 | 15,082 | 0.8831% |
| `4` | OUT_RANGE | 0 | 0 | 0 | 0 | 0 | 0.0000% |
| `5` | FLATLINE | 31 | 31 | 2,048 | 366 | 2,412 | 0.1412% |

---

## 5. Quyết định Xử lý & Cơ sở Kỹ thuật

| Bước | Quyết định xử lý | Cơ sở lý luận kỹ thuật |
|---|---|---|
| 1 | Chuẩn hóa trên chuỗi dữ liệu KAK Quasi-Definitive (QD) | Chuỗi dữ liệu đã qua hiệu chỉnh baseline chính thức từ Đài Kakioka |
| 2 | Thay sentinel 99999.00 / 88888.00 bằng NaN | Tuân thủ đúng quy cách kỹ thuật IAGA-2002 |
| 3 | Áp dụng ngưỡng vật lý WMM2020 cho KAK (36.232° N, 140.186° E) | Tránh gắn cờ nhầm ngưỡng vật lý vĩ độ trung bình Bán cầu Bắc |
| 4 | Gắn cờ spike theo ngưỡng K=5.0 sigma | Giữ nguyên giá trị đo để bảo toàn tín hiệu biến thiên bão từ thật |
| 5 | Gắn cờ flatline chuỗi liên tiếp >= 10 điểm | Phát hiện nguy cơ lỗi đóng băng cảm biến; giữ nguyên dữ liệu để kiểm tra thủ công |
| 6 | Nội suy tuyến tính cho gap thiếu <= 5 điểm | Khôi phục các điểm mất tín hiệu ngắn mà không làm méo dạng sóng địa từ |
| 7 | Bảo toàn toàn bộ điểm đo spike / flatline / ngoài khoảng | Đảm bảo các mô hình hạ nguồn tiếp cận đầy đủ dữ liệu gốc kèm cờ chất lượng |

---

## 6. Khuyến nghị Sử dụng cho Phân tích Hạ nguồn

- Phân tích Địa từ Cơ bản: Lọc `quality_flag == 0` để lấy chuỗi dữ liệu sạch hoàn toàn.
- Phân tích Sự kiện Bão từ: Có thể bao gồm các điểm cờ 3 (spike) sau khi kiểm tra trực quan, vì các biến thiên nhanh trong pha chính bão từ có thể kích hoạt cờ biến thiên.
- Xây dựng Mô hình Machine Learning: Sử dụng các cột cờ riêng lẻ `flag_x`, `flag_y`, `flag_z`, `flag_f` làm tính năng đầu vào (input feature) để điều chỉnh hàm mất mát (loss function) theo độ tin cậy của dữ liệu.

---
*Báo cáo được tạo tự động bởi mô-đun xuất dữ liệu pipeline (src/kak/process.py).*
