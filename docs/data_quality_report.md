# Báo cáo Chất lượng Dữ liệu – SOP-01

> **Trạm:** KAK | **Loại:** quasi-definitive | **Khoảng:** 2023-01-01 → 2026-03-31
> Tạo tự động bởi `process.py` ngày 2026-10-05.

---

## 1. Hạn chế dữ liệu

1. **Trạm ngoài khu vực nghiên cứu:** KAK ở Nhật Bản (~36°N, 140°E), không phải trạm Việt Nam. Các đặc trưng từ trường (cường độ, hướng, biến thiên) khác với khu vực Đông Nam Á.
2. **Một trạm duy nhất:** Không thể phát hiện lỗi cục bộ bằng so sánh chéo trạm khác.
3. **Quasi-definitive, không phải Definitive:** QD đã qua hiệu chỉnh baseline sơ bộ nhưng chưa được phê duyệt cuối cùng. Sai số baseline có thể còn tồn tại.
4. **Chuỗi cắt tại 2026-03-31:** Tháng 4/2026 có valid 90.00% (borderline). Có thể kéo dài sau khi xác nhận.
5. **PHU không khả dụng:** Quasi-def PHU chỉ có dữ liệu thật từ 2026-01 (2023–2025 = 100% fill). Reported PHU có tháng 0% (2024-10) và nhiều tháng <90%.

---

## 2. Tổng quan dữ liệu

| Thuộc tính | Giá trị |
|---|---|
| Số điểm (sau reindex) | 1,707,840 |
| Từ | 2023-01-01 00:00:00+00:00 |
| Đến | 2026-03-31 23:59:00+00:00 |
| HAPI dataset | `kak/quasi-def/PT1M/xyzf` |

---

## 3. So sánh trước / sau xử lý

### 3.1 Thiếu giá trị và Sentinel

| Cột | Trước – Sentinel | Trước – NaN | Sau – NaN (tổng) | % sau |
|---|---|---|---|---|
| `x_nt` | 0 | 0 | 0 | 0.0000% |
| `y_nt` | 0 | 0 | 0 | 0.0000% |
| `z_nt` | 0 | 0 | 0 | 0.0000% |
| `f_nt` | 0 | 0 | 0 | 0.0000% |

### 3.2 Timestamp

| Kiểm tra | Trước xử lý | Sau xử lý |
|---|---|---|
| Trùng timestamp | 0 | 0 ✅ |
| Thiếu điểm (gap) | 0 | 0 ✅ |
| Gap dài nhất | 0 phút | 0 phút ✅ |

### 3.3 Ngoài khoảng vật lý

| Cột | Khoảng [min, max] nT | Trước | Sau (cờ 4) |
|---|---|---|---|
| `x_nt` | [20,000, 50,000] | 0 | 0 |
| `y_nt` | [-5,000, 10,000] | 0 | 0 |
| `z_nt` | [20,000, 60,000] | 0 | 0 |
| `f_nt` | [35,000, 65,000] | 0 | 0 |

### 3.4 Điểm biến thiên đột ngột (nghi ngờ spike) – cờ 3

> ⚠️ Các điểm này **chỉ được gắn cờ, không bị xoá**. Một phần có thể là biến thiên địa từ thật trong bão từ.
> Ngưỡng: |diff| > 5.0σ của |diff|, tính sau khi loại sentinel/NaN.

| Cột | Ngưỡng (nT) | Số điểm | % tổng dòng |
|---|---|---|---|
| `x_nt` | ≈2.534 | 7,603 | 0.4452% |
| `y_nt` | ≈2.04 | 7,762 | 0.4545% |
| `z_nt` | ≈1.491 | 8,392 | 0.4914% |
| `f_nt` | ≈2.662 | 7,970 | 0.4667% |

### 3.5 Flatline – cờ 5

> Chuỗi hằng số liên tiếp ≥ 10 điểm. **Không xoá; chưa xác định nguyên nhân, cần kiểm tra trước khi dùng.**

| Cột | Số đoạn (trước) | Dài nhất (trước) | Số điểm bị cờ (sau) | % tổng dòng |
|---|---|---|---|---|
| `x_nt` | 3 | 11 phút | 31 | 0.0018% |
| `y_nt` | 3 | 11 phút | 31 | 0.0018% |
| `z_nt` | 176 | 21 phút | 2,048 | 0.1199% |
| `f_nt` | 32 | 15 phút | 366 | 0.0214% |

---

## 4. Phân phối quality_flag sau xử lý

| Mã | Tên | x_nt | y_nt | z_nt | f_nt | Tổng hợp |
|---|---|---|---|---|---|---|
| `0` | OK | 1,700,206 | 1,700,047 | 1,697,400 | 1,699,504 | 1,690,346 |
| `1` | INTERP | 0 | 0 | 0 | 0 | 0 |
| `2` | MISSING | 0 | 0 | 0 | 0 | 0 |
| `3` | SPIKE | 7,603 | 7,762 | 8,392 | 7,970 | 15,082 |
| `4` | OUT_RANGE | 0 | 0 | 0 | 0 | 0 |
| `5` | FLATLINE | 31 | 31 | 2,048 | 366 | 2,412 |

---

## 5. Khuyến nghị sử dụng

- **Phân tích cơ bản:** Dùng `quality_flag == 0` → dữ liệu sạch hoàn toàn.
- **Phân tích bão từ:** Có thể bao gồm cả cờ 3 (spike) sau khi kiểm tra thủ công.
- **Mô hình dự báo:** Nên xem xét cờ 5 (flatline) vì chưa xác định nguyên nhân.
- **Dashboard Power BI:** Giữ đầy đủ chuỗi thời gian (không lọc dòng), thay NULL cho điểm cờ 1, 2, 4 nếu cần.

---
*Cập nhật lần cuối: 2026-10-05*
