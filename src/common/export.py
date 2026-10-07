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
    Viết docs/kak/data_dictionary.md từ schema thực tế của DataFrame.
    """
    out_dir = cfg.DOCS_DIR / "kak"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data_dictionary.md"

    lines = [
        "# Data Dictionary – SOP-01 Geophysical Data Pipeline",
        "",
        f"> **Tạo lúc:** {datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} UTC  ",
        f"> **Nguồn:** INTERMAGNET (trạm PHU, DLT) + USGS Earthquake  ",
        f"> **Khoảng thời gian:** {cfg.DATE_START} → {cfg.DATE_END}  ",
        "",
        "---",
        "",
        "## 1. Schema cột",
        "",
        "| Cột | Kiểu | Đơn vị | Mô tả | Giá trị hợp lệ | Ghi chú |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for col in df.columns:
        doc = _COLUMN_DOCS.get(col, {})
        # Kiểu thực tế từ DataFrame (ưu tiên doc)
        dtype  = doc.get("type", str(df[col].dtype))
        unit   = doc.get("unit", "–")
        desc   = doc.get("description", "")
        valid  = doc.get("valid_values", "")
        note   = doc.get("notes", "")
        lines.append(f"| `{col}` | {dtype} | {unit} | {desc} | {valid} | {note} |")

    lines += [
        "",
        "---",
        "",
        "## 2. Bảng mã quality_flag",
        "",
        "| Mã | Ý nghĩa |",
        "| --- | --- |",
    ]
    for code, meaning in _FLAG_DOCS:
        lines.append(f"| {code} | {meaning} |")

    if meta:
        lines += [
            "",
            "---",
            "",
            "## 3. Metadata trạm (từ header IAGA-2002)",
            "",
            "| Trường | Giá trị |",
            "| --- | --- |",
        ]
        for k, v in meta.items():
            lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "---",
        "",
        "## 4. Ngưỡng vật lý hợp lệ",
        "",
        "| Cột | Min (nT) | Max (nT) | Nguồn tham chiếu |",
        "| --- | --- | --- | --- |",
    ]
    for col, (lo, hi) in cfg.PHYSICAL_BOUNDS.items():
        lines.append(f"| `{col}` | {lo:,} | {hi:,} | INTERMAGNET Guide + World Magnetic Model (khu vực ĐNÁ) |")

    lines += [
        "",
        "---",
        "",
        "## 5. Giá trị sentinel",
        "",
        "Theo tài liệu kỹ thuật INTERMAGNET (IAGA-2002 format description):",
        "- `99999.00` – dữ liệu thiếu (missing)",
        "- `88888.00` – không được đo (not observed/reported)",
        "",
        "Trong pipeline SOP-01: cả hai đều được thay bằng `NaN` ở Bước 3.3.",
        "",
        "---",
        "*Tài liệu này được tạo tự động bởi `src/export.py`. Chỉnh sửa qua code, không sửa thủ công.*",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  📄 Data dictionary: {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Quality Report
# ─────────────────────────────────────────────────────────────────────────────

def write_quality_report(qc_before: dict,
                          qc_after: dict,
                          processing_log: dict,
                          meta: dict | None = None) -> Path:
    """
    Viết docs/kak/data_quality_report.md với số liệu trước/sau xử lý.
    """
    out_dir = cfg.DOCS_DIR / "kak"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data_quality_report.md"
    station  = qc_before.get("station", "N/A")

    def fmt_df(df: pd.DataFrame) -> str:
        """Định dạng DataFrame thành Markdown table."""
        if df is None or df.empty:
            return "*(Không có dữ liệu)*"
        header = "| " + " | ".join(str(c) for c in df.columns) + " |"
        sep    = "| " + " | ".join("---" for _ in df.columns) + " |"
        rows   = []
        for _, row in df.iterrows():
            rows.append("| " + " | ".join(str(v) for v in row.values) + " |")
        return "\n".join([header, sep] + rows)

    lines = [
        "# Data Quality Report – SOP-01",
        "",
        f"> **Trạm:** {station}  ",
        f"> **Khoảng thời gian:** {cfg.DATE_START} → {cfg.DATE_END}  ",
        f"> **Tần số:** {cfg.SAMPLE_FREQ}  ",
        f"> **Loại dữ liệu:** {cfg.DATA_TYPE}  ",
        f"> **Tạo lúc:** {datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} UTC  ",
        "",
        "---",
        "",
        "## 1. Phạm vi dữ liệu",
        "",
        f"- **Nguồn:** INTERMAGNET (trạm {station}), USGS Earthquake",
        f"- **Khoảng:** {cfg.DATE_START} → {cfg.DATE_END}",
        f"- **Tần số:** 1 phút ({cfg.SAMPLE_FREQ})",
        f"- **Loại:** {cfg.DATA_TYPE}",
        f"- **Thành phần đo:** xác định từ header IAGA-2002 (xem Data Dictionary)",
        "",
        "---",
        "",
        "## 2. Chỉ số chất lượng TRƯỚC / SAU xử lý",
        "",
        "### 2.1 Thiếu giá trị",
        "",
        "**TRƯỚC:**",
        "",
        fmt_df(qc_before.get("missing")),
        "",
        "**SAU:**",
        "",
        fmt_df(qc_after.get("missing")),
        "",
        "### 2.2 Trùng timestamp",
        "",
        f"**TRƯỚC:** {qc_before.get('duplicates', {}).get('duplicate_count', 'N/A')} timestamp trùng",
        f"**SAU:** {qc_after.get('duplicates', {}).get('duplicate_count', 'N/A')} timestamp trùng",
        "",
        "### 2.3 Thiếu timestamp (gap)",
        "",
    ]

    gb = qc_before.get("gaps", {})
    ga = qc_after.get("gaps", {})
    lines += [
        "| Chỉ số | Trước | Sau |",
        "| --- | --- | --- |",
        f"| Điểm kỳ vọng | {gb.get('expected_points', 'N/A'):,} | {ga.get('expected_points', 'N/A'):,} |",
        f"| Điểm thực tế | {gb.get('actual_points', 'N/A'):,} | {ga.get('actual_points', 'N/A'):,} |",
        f"| Điểm thiếu | {gb.get('missing_points', 'N/A'):,} | {ga.get('missing_points', 'N/A'):,} |",
        f"| Số gap | {gb.get('n_gaps', 'N/A'):,} | {ga.get('n_gaps', 'N/A'):,} |",
        f"| Gap dài nhất (phút) | {gb.get('max_gap_minutes', 'N/A')} | {ga.get('max_gap_minutes', 'N/A')} |",
        "",
        "### 2.4 Ngoài khoảng vật lý",
        "",
        "**TRƯỚC:**",
        "",
        fmt_df(qc_before.get("bounds")),
        "",
        "### 2.5 Spike",
        "",
        "**TRƯỚC:**",
        "",
        fmt_df(qc_before.get("spikes")),
        "",
        f"*Ngưỡng: |diff| > {cfg.SPIKE_K} × std(diff)*",
        "",
        "### 2.6 Flatline",
        "",
        "**TRƯỚC:**",
        "",
        fmt_df(qc_before.get("flatlines")),
        "",
        f"*Ngưỡng: ≥ {cfg.FLATLINE_N} điểm liên tiếp cùng giá trị*",
        "",
        "---",
        "",
        "## 3. Phân phối quality_flag sau xử lý",
        "",
        "| Mã cờ | Ý nghĩa | Số điểm |",
        "| --- | --- | --- |",
    ]

    flag_counts = processing_log.get("steps", {}).get("5_flag_counts", {})
    flag_meanings = {0: "Hợp lệ", 1: "Nội suy", 2: "Thiếu (NaN)",
                     3: "Spike", 4: "Ngoài khoảng", 5: "Flatline"}
    for code in range(6):
        cnt = flag_counts.get(code, 0)
        lines.append(f"| {code} | {flag_meanings[code]} | {cnt:,} |")

    lines += [
        "",
        "---",
        "",
        "## 4. Quyết định xử lý và lý do",
        "",
        "| STT | Quyết định | Lý do |",
        "| --- | --- | --- |",
        "| 1 | Dùng dữ liệu **Definitive** (D) cho cả PHU và DLT | Đã hiệu chỉnh đầy đủ; nhất quán giữa các trạm |",
        "| 2 | Sentinel 99999.00 và 88888.00 → NaN | Theo tài liệu kỹ thuật INTERMAGNET IAGA-2002 |",
        "| 3 | Ngưỡng vật lý lấy từ INTERMAGNET Guide + WMM | Khu vực ĐNÁ; chỉ gắn cờ 4, không xoá |",
        f"| 4 | Spike: |diff| > {cfg.SPIKE_K}σ | Ngưỡng tiêu chuẩn, có thể điều chỉnh trong cfg.SPIKE_K |",
        f"| 5 | Flatline: ≥ {cfg.FLATLINE_N} điểm liên tiếp | Phát hiện lỗi cảm biến; chỉ gắn cờ 5 |",
        f"| 6 | Nội suy tuyến tính cho gap ≤ {cfg.INTERP_MAX_GAP} điểm | Gap ngắn có thể do dropout tín hiệu; gap dài giữ NaN |",
        "| 7 | Không xoá spike/flatline/out-of-range | TV3/TV5 cần dữ liệu gốc để phân tích trước/sau lọc |",
        "",
        "---",
        "",
        "## 5. Hạn chế còn lại",
        "",
        "- Spike được phát hiện theo ngưỡng thống kê (`SPIKE_K × std`); sự kiện địa từ thật (magnetic storm) có thể bị gắn cờ nhầm.",
        "- Flatline ngắn < 10 điểm không được gắn cờ; cần kiểm tra thủ công nếu cần.",
        "- Dữ liệu INTERMAGNET Definitive có thể có lỗi hệ thống trong baseline hiệu chỉnh (nằm ngoài phạm vi SOP này).",
        "- Ngưỡng vật lý là ước lượng từ WMM; giá trị thực tế tại PHU và DLT cần xác nhận từ tài liệu trạm.",
        "- Gap > 5 phút giữ NaN; tác động đến mô hình cần gap-filling ở bước sau (TV3/TV4).",
        "",
        "---",
        "*Báo cáo này được tạo tự động bởi `src/export.py`. Số liệu do code tính từ dữ liệu thật.*",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  📄 Quality report: {out_path}")
    return out_path
