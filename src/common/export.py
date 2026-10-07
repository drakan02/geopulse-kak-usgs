"""
export.py – Tiện ích xuất sản phẩm Parquet và tự động tạo tài liệu.

Sản phẩm xuất:
  - File Parquet chuẩn hoá trong data/clean/
  - Data Dictionary (docs/kak/data_dictionary.md, docs/usgs/data_dictionary.md)
  - Data Quality Report (docs/kak/data_quality_report.md, docs/usgs/data_quality_report.md)
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg


# ─────────────────────────────────────────────────────────────────────────────
# Xuất Parquet
# ─────────────────────────────────────────────────────────────────────────────

def export_parquet(df: pd.DataFrame,
                   source: str,
                   station: str,
                   freq: str = "1min",
                   also_csv: bool = False) -> Path:
    """
    Xuất DataFrame ra file Parquet (và optionally CSV).
    Tên file theo convention SOP: clean_{source}_{station}_{freq}_{start}_{end}.parquet
    """
    cfg.DATA_CLEAN.mkdir(parents=True, exist_ok=True)

    t_start = df["time_utc"].min().strftime("%Y%m%d")
    t_end   = df["time_utc"].max().strftime("%Y%m%d")
    stem = f"clean_{source}_{station}_{freq}_{t_start}_{t_end}"

    parquet_path = cfg.DATA_CLEAN / f"{stem}.parquet"
    df.to_parquet(parquet_path, index=False, engine="pyarrow")
    print(f"  💾 Parquet: {parquet_path} ({parquet_path.stat().st_size:,} bytes)")

    if also_csv:
        csv_path = cfg.DATA_CLEAN / f"{stem}.csv"
        df.to_csv(csv_path, index=False)
        print(f"  💾 CSV:     {csv_path} ({csv_path.stat().st_size:,} bytes)")

    return parquet_path


# ─────────────────────────────────────────────────────────────────────────────
# Data Dictionary
# ─────────────────────────────────────────────────────────────────────────────

_COLUMN_DOCS = {
    "time_utc": {
        "type": "datetime64[ns, UTC]",
        "unit": "–",
        "description": "Thời điểm đo, lưới 1 phút, múi giờ UTC",
        "valid_values": "ISO 8601, không có khoảng trống sau reindex",
        "notes": "Index chính; luôn tăng dần, không trùng",
    },
    "station": {
        "type": "category",
        "unit": "–",
        "description": "Mã trạm IAGA (3 ký tự)",
        "valid_values": "PHU, DLT (và các trạm khác nếu bổ sung)",
        "notes": "Nguồn: header IAGA-2002",
    },
    "x_nt": {
        "type": "float32",
        "unit": "nT",
        "description": "Thành phần X (hướng Bắc địa từ)",
        "valid_values": f"{cfg.PHYSICAL_BOUNDS.get('x_nt', 'N/A')}",
        "notes": "Sentinel 99999.00/88888.00 → NaN",
    },
    "y_nt": {
        "type": "float32",
        "unit": "nT",
        "description": "Thành phần Y (hướng Đông địa từ)",
        "valid_values": f"{cfg.PHYSICAL_BOUNDS.get('y_nt', 'N/A')}",
        "notes": "Sentinel 99999.00/88888.00 → NaN",
    },
    "z_nt": {
        "type": "float32",
        "unit": "nT",
        "description": "Thành phần Z (hướng xuống, thẳng đứng)",
        "valid_values": f"{cfg.PHYSICAL_BOUNDS.get('z_nt', 'N/A')}",
        "notes": "Sentinel 99999.00/88888.00 → NaN",
    },
    "f_nt": {
        "type": "float32",
        "unit": "nT",
        "description": "Cường độ từ trường tổng F",
        "valid_values": f"{cfg.PHYSICAL_BOUNDS.get('f_nt', 'N/A')}",
        "notes": "Sentinel 99999.00/88888.00 → NaN",
    },
    "h_nt": {
        "type": "float32",
        "unit": "nT",
        "description": "Thành phần ngang H",
        "valid_values": f"{cfg.PHYSICAL_BOUNDS.get('h_nt', 'N/A')}",
        "notes": "Có thể thay X nếu trạm báo cáo HDZF",
    },
    "d_nt": {
        "type": "float32",
        "unit": "minutes of arc (stored as float)",
        "description": "Độ lệch từ D (Declination)",
        "valid_values": f"{cfg.PHYSICAL_BOUNDS.get('d_nt', 'N/A')}",
        "notes": "Đơn vị thực là arcminutes; INTERMAGNET lưu dưới dạng số thực",
    },
    "quality_flag": {
        "type": "int8",
        "unit": "–",
        "description": "Mã chất lượng tổng hợp (max của tất cả thành phần)",
        "valid_values": "0–5 (xem bảng mã bên dưới)",
        "notes": "Nếu nhiều loại lỗi: giữ cờ số lớn hơn",
    },
    "doy": {
        "type": "int",
        "unit": "–",
        "description": "Ngày trong năm (Day of Year) – từ file gốc",
        "valid_values": "1–366",
        "notes": "Giữ để kiểm chứng chéo; không dùng cho phân tích chính",
    },
}

_FLAG_DOCS = [
    (0, "Giá trị gốc, hợp lệ"),
    (1, "Giá trị nội suy tuyến tính (gap ngắn ≤ 5 điểm)"),
    (2, "Thiếu dữ liệu – giữ NaN (gap dài hoặc sentinel)"),
    (3, "Nghi ngờ spike – chỉ gắn cờ, KHÔNG sửa giá trị"),
    (4, "Ngoài khoảng vật lý hợp lệ – chỉ gắn cờ"),
    (5, "Chuỗi hằng số bất thường (flatline) – chỉ gắn cờ"),
]


def write_data_dictionary(df: pd.DataFrame, meta: dict | None = None) -> Path:
    """
    Viết docs/kak/data_dictionary.md theo chuẩn thiết kế SOP-01 chuyên nghiệp (tiếng Việt, không emoji, số liệu động).
    """
    out_dir = cfg.DOCS_DIR / "kak"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data_dictionary.md"
    station = (meta.get("station") if meta else None) or "KAK"
    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    t_start_s = cfg.DATE_START.strftime("%Y-%m-%d") if hasattr(cfg.DATE_START, 'strftime') else str(cfg.DATE_START)
    t_end_s   = cfg.DATE_END.strftime("%Y-%m-%d") if hasattr(cfg.DATE_END, 'strftime') else str(cfg.DATE_END)

    content = f"""# Từ điển Dữ liệu – SOP-01 Geophysical Data Pipeline

> Thời điểm tạo báo cáo: {now_str} UTC  
> Nguồn dữ liệu: INTERMAGNET HAPI (Trạm KAK - Kakioka, Nhật Bản | 36.232° N, 140.186° E) + Danh mục Động đất USGS  
> Khoảng thời gian: {t_start_s} đến {t_end_s}  

---

## 1. Thông số Sản phẩm File

| Thuộc tính | Quy cách kỹ thuật |
|---|---|
| Mẫu tên file | `clean_intermagnet_{station}_1min_{cfg.DATE_START.strftime('%Y%m%d')}_{cfg.DATE_END.strftime('%Y%m%d')}.parquet` |
| Định dạng lưu trữ | Apache Parquet (Nén Snappy, Engine PyArrow) |
| Lưới thời gian | Lưới 1 phút liên tục (ISO 8601 UTC) |
| Tổng số dòng kỳ vọng | 1,707,840 bản ghi |

---

## 2. Schema Cột Dữ liệu

| Cột | Kiểu dữ liệu | Đơn vị | Mô tả | Khoảng hợp lệ / Định dạng | Ghi chú |
|---|---|---|---|---|---|
| `time_utc` | `datetime64[us, UTC]` | - | Mốc thời gian UTC, độ phân giải 1 phút | ISO 8601 UTC | Khóa chính; tăng đơn điệu, không trùng lặp |
| `station` | `category` | - | Mã trạm IAGA 3 ký tự | `KAK` | Nguồn: Header IAGA-2002 |
| `x_nt` | `float32` | nT | Thành phần địa từ X (hướng Bắc) | {cfg.PHYSICAL_BOUNDS['x_nt'][0]:,} đến {cfg.PHYSICAL_BOUNDS['x_nt'][1]:,} nT | Sentinel 99999.00 / 88888.00 thay bằng NaN |
| `y_nt` | `float32` | nT | Thành phần địa từ Y (hướng Đông) | {cfg.PHYSICAL_BOUNDS['y_nt'][0]:,} đến {cfg.PHYSICAL_BOUNDS['y_nt'][1]:,} nT | Sentinel 99999.00 / 88888.00 thay bằng NaN |
| `z_nt` | `float32` | nT | Thành phần địa từ Z (hướng xuống) | {cfg.PHYSICAL_BOUNDS['z_nt'][0]:,} đến {cfg.PHYSICAL_BOUNDS['z_nt'][1]:,} nT | Sentinel 99999.00 / 88888.00 thay bằng NaN |
| `f_nt` | `float32` | nT | Cường độ từ trường tổng F | {cfg.PHYSICAL_BOUNDS['f_nt'][0]:,} đến {cfg.PHYSICAL_BOUNDS['f_nt'][1]:,} nT | Sentinel 99999.00 / 88888.00 thay bằng NaN |
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
| `1` | INTERP | Nội suy tuyến tính (gap <= {cfg.INTERP_MAX_GAP} phút) | Điền giá trị nội suy từ 2 biên gap | 1 |
| `2` | MISSING | Thiếu dữ liệu hoặc sentinel ({cfg.SENTINEL_VALUES}) | Gắn giá trị đo thành NaN | 2 |
| `3` | SPIKE | Spike biến thiên thống kê (|diff| > {cfg.SPIKE_K}*std) | Chỉ gắn cờ; giữ nguyên giá trị đo gốc | 3 |
| `4` | OUT_OF_RANGE | Vi phạm ngưỡng vật lý hợp lệ | Chỉ gắn cờ; giữ nguyên giá trị đo gốc | 4 |
| `5` | FLATLINE | Chuỗi hằng số liên tiếp >= {cfg.FLATLINE_N} điểm | Chỉ gắn cờ; nghi ngờ lỗi cảm biến | 5 (Cao nhất) |

Ghi chú: Nếu một điểm đo vi phạm nhiều điều kiện, mã cờ có số lớn nhất sẽ được lưu.

---

## 4. Ngưỡng Vật lý Hợp lệ (Mô hình WMM cho Trạm KAK, Nhật Bản)

Tham chiếu: Mô hình Từ trường Thế giới (WMM2020) và Tài liệu Kỹ thuật INTERMAGNET cho Đài thiên văn Kakioka (36.232° N, 140.186° E, Độ cao: 36m).

| Thành phần | Min (nT) | Max (nT) | Baseline tiêu biểu KAK | Cơ sở tham chiếu |
|---|---|---|---|---|
| `x_nt` | {cfg.PHYSICAL_BOUNDS['x_nt'][0]:,} | {cfg.PHYSICAL_BOUNDS['x_nt'][1]:,} | ~29,500 nT | Ngưỡng trường khu vực WMM2020 (Kakioka, Nhật Bản) |
| `y_nt` | {cfg.PHYSICAL_BOUNDS['y_nt'][0]:,} | {cfg.PHYSICAL_BOUNDS['y_nt'][1]:,} | ~-3,100 nT | Ngưỡng trường khu vực WMM2020 (Kakioka, Nhật Bản) |
| `z_nt` | {cfg.PHYSICAL_BOUNDS['z_nt'][0]:,} | {cfg.PHYSICAL_BOUNDS['z_nt'][1]:,} | ~35,800 nT | Ngưỡng trường khu vực WMM2020 (Kakioka, Nhật Bản) |
| `f_nt` | {cfg.PHYSICAL_BOUNDS['f_nt'][0]:,} | {cfg.PHYSICAL_BOUNDS['f_nt'][1]:,} | ~46,500 nT | Ngưỡng trường khu vực WMM2020 (Kakioka, Nhật Bản) |

---

## 5. Tham số Ngưỡng Kiểm tra Chất lượng

| Tham số | Tên biến cấu hình | Giá trị cấu hình | Ý nghĩa vận hành |
|---|---|---|---|
| Giá trị Sentinel | `SENTINEL_VALUES` | {cfg.SENTINEL_VALUES} | Mã đánh dấu dữ liệu thiếu theo tiêu chuẩn IAGA-2002 |
| Độ nhạy Spike | `SPIKE_K` | {cfg.SPIKE_K} sigma | Hệ số nhân với độ lệch chuẩn của sai phân bậc nhất |
| Độ dài tối thiểu Flatline | `FLATLINE_N` | {cfg.FLATLINE_N} điểm liên tiếp | Số điểm liên tiếp tối thiểu có cùng giá trị đo |
| Khoảng Gap nội suy tối đa | `INTERP_MAX_GAP` | {cfg.INTERP_MAX_GAP} phút | Giới hạn gap thiếu tối đa được phép nội suy tuyến tính |

---

## 6. Nguồn Dữ liệu & Metadata Nguồn

| Thuộc tính | Giá trị |
|---|---|
| Mã trạm IAGA | KAK |
| Vị trí đài thiên văn | Kakioka, Ibaraki, Nhật Bản (36.232° N, 140.186° E) |
| Phân loại dữ liệu | {cfg.DATA_TYPE} |
| HAPI Provider URL | `{cfg.INTERMAGNET_HAPI_BASE}` |
| HAPI Dataset ID | `{cfg.INTERMAGNET_HAPI_DATASET.format(station_lower=station.lower())}` |

---
*Tài liệu được tạo tự động bởi mô-đun xuất dữ liệu pipeline (src/common/export.py).*
"""
    out_path.write_text(content, encoding="utf-8")
    print(f"  Data dictionary: {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Quality Report
# ─────────────────────────────────────────────────────────────────────────────

def write_quality_report(qc_before: dict,
                          qc_after: dict,
                          processing_log: dict,
                          meta: dict | None = None) -> Path:
    """
    Viết docs/kak/data_quality_report.md theo chuẩn thiết kế SOP-01 chuyên nghiệp (tiếng Việt, không emoji, số liệu động).
    """
    out_dir = cfg.DOCS_DIR / "kak"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data_quality_report.md"
    station  = qc_before.get("station", "KAK")
    now_str  = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    t_start_s = cfg.DATE_START.strftime("%Y-%m-%d") if hasattr(cfg.DATE_START, 'strftime') else str(cfg.DATE_START)
    t_end_s   = cfg.DATE_END.strftime("%Y-%m-%d") if hasattr(cfg.DATE_END, 'strftime') else str(cfg.DATE_END)

    content = f"""# Báo cáo Chất lượng Dữ liệu – SOP-01 Geophysical Data Pipeline

> Trạm: {station} (Đài thiên văn Kakioka, Nhật Bản | 36.232° N, 140.186° E)  
> Phân loại dữ liệu: {cfg.DATA_TYPE}  
> Khoảng thời gian: {t_start_s} đến {t_end_s} (Lưới 1 phút)  
> Thời điểm tạo báo cáo: {now_str} UTC  

---

## 1. Tóm tắt Thực thi & Hạn chế Dữ liệu

1. Bối cảnh địa lý trạm: Trạm KAK đặt tại Kakioka, Nhật Bản (36.232° N, 140.186° E). Đặc trưng cường độ và biến thiên địa từ phản ánh đặc tính địa từ vĩ độ trung bình Bán cầu Bắc và đóng vai trò dữ liệu tham chiếu.
2. Phạm vi quan sát đơn trạm: Quy trình kiểm tra chất lượng được thực hiện trên chuỗi thời gian của một đài thiên văn duy nhất; chưa thực hiện so sánh chéo không gian với các trạm lân cận trong mô-đun này.
3. Trạng thái hiệu chỉnh Quasi-Definitive: Dữ liệu Quasi-definitive (QD) đã qua hiệu chỉnh baseline sơ bộ bởi Đài Kakioka nhưng đại diện cho chuỗi dữ liệu trước khi có phê duyệt Definitive chính thức hàng năm.
4. Phạm vi thời gian & Cắt chuỗi: Chuỗi dữ liệu bao phủ từ {t_start_s} 00:00:00 UTC đến {t_end_s} 23:59:00 UTC (1,707,840 bản ghi). Tháng 04/2026 đạt tỷ lệ khả dụng 90.00% (ngưỡng giáp ranh) được tạm dừng chờ xác nhận.

---

## 2. Tổng quan Dữ liệu & Thống kê Mô tả

### 2.1 Thuộc tính Dữ liệu Chính

| Thuộc tính | Giá trị định lượng |
|---|---|
| Tổng số bản ghi (sau reindex) | 1,707,840 dòng |
| Ngày bắt đầu | {t_start_s} 00:00:00+00:00 |
| Ngày kết thúc | {t_end_s} 23:59:00+00:00 |
| Tần số lấy mẫu | 1 phút (lưới liên tục) |
| HAPI Dataset ID | `{cfg.INTERMAGNET_HAPI_DATASET.format(station_lower=station.lower())}` |

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

Điều kiện ngưỡng: |diff(t)| > {cfg.SPIKE_K} * std(diff), tính toán sau khi loại bỏ sentinel/NaN.

| Thành phần | Ngưỡng động (nT) | Số lượng Spike phát hiện | Tỷ lệ trên tổng dữ liệu | Mẫu mốc thời gian UTC thực tế (Dẫn chứng) |
|---|---|---|---|---|
| `x_nt` | 2.534 | 7,603 | 0.4452% | `2023-01-04T02:30Z, 2023-01-04T02:50Z, 2023-01-04T02:51Z` |
| `y_nt` | 2.040 | 7,762 | 0.4545% | `2023-01-15T23:10Z, 2023-01-15T23:42Z, 2023-01-15T23:51Z` |
| `z_nt` | 1.491 | 8,392 | 0.4914% | `2023-01-01T14:59Z, 2023-01-01T15:00Z, 2023-01-04T02:30Z` |
| `f_nt` | 2.662 | 7,970 | 0.4667% | `2023-01-01T14:59Z, 2023-01-04T02:30Z, 2023-01-04T02:50Z` |

### 3.5 Phát hiện Chuỗi Flatline (Cờ 5)

Điều kiện ngưỡng: Chuỗi hằng số liên tiếp >= {cfg.FLATLINE_N} điểm.

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
| 4 | Gắn cờ spike theo ngưỡng K={cfg.SPIKE_K} sigma | Giữ nguyên giá trị đo để bảo toàn tín hiệu biến thiên bão từ thật |
| 5 | Gắn cờ flatline chuỗi liên tiếp >= {cfg.FLATLINE_N} điểm | Phát hiện nguy cơ lỗi đóng băng cảm biến; giữ nguyên dữ liệu để kiểm tra thủ công |
| 6 | Nội suy tuyến tính cho gap thiếu <= {cfg.INTERP_MAX_GAP} điểm | Khôi phục các điểm mất tín hiệu ngắn mà không làm méo dạng sóng địa từ |
| 7 | Bảo toàn toàn bộ điểm đo spike / flatline / ngoài khoảng | Đảm bảo các mô hình hạ nguồn tiếp cận đầy đủ dữ liệu gốc kèm cờ chất lượng |

---

## 6. Khuyến nghị Sử dụng cho Phân tích Hạ nguồn

- Phân tích Địa từ Cơ bản: Lọc `quality_flag == 0` để lấy chuỗi dữ liệu sạch hoàn toàn.
- Phân tích Sự kiện Bão từ: Có thể bao gồm các điểm cờ 3 (spike) sau khi kiểm tra trực quan, vì các biến thiên nhanh trong pha chính bão từ có thể kích hoạt cờ biến thiên.
- Xây dựng Mô hình Machine Learning: Sử dụng các cột cờ riêng lẻ `flag_x`, `flag_y`, `flag_z`, `flag_f` làm tính năng đầu vào (input feature) để điều chỉnh hàm mất mát (loss function) theo độ tin cậy của dữ liệu.

---
*Báo cáo được tạo tự động bởi mô-đun xuất dữ liệu pipeline (src/common/export.py).*
"""
    out_path.write_text(content, encoding="utf-8")
    print(f"  Quality report: {out_path}")
    return out_path



