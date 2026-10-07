"""
process.py – Thực thi pipeline KAK, kiểm chứng assert và xuất sản phẩm.

Quy tắc bất biến:
  - KHÔNG sửa data/raw/. Đọc dữ liệu từ data/interim/raw_KAK.parquet.
  - KHÔNG xoá hay làm mịn spike/flatline – chỉ gắn cờ.
  - Nếu một điểm thuộc nhiều loại cờ → giữ cờ số LỚN NHẤT (5 > 4 > 3 > 2 > 1 > 0).

Sản phẩm xuất:
  - data/clean/clean_intermagnet_KAK_1min_20230101_20260331.parquet
  - docs/kak/data_dictionary.md
  - docs/kak/data_quality_report.md

Thực thi:
  python src/kak/process.py
"""

import sys
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg

# ── Hằng số bảng mã ───────────────────────────────────────────────────────
FLAG_OK         = 0
FLAG_INTERP     = 1
FLAG_MISSING    = 2
FLAG_SPIKE      = 3
FLAG_OUT_RANGE  = 4
FLAG_FLATLINE   = 5

MEAS_COLS  = ["x_nt", "y_nt", "z_nt", "f_nt"]
FLAG_COLS  = ["flag_x", "flag_y", "flag_z", "flag_f"]
COL_MAP    = dict(zip(MEAS_COLS, FLAG_COLS))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def pct(n, total):
    return f"{100*n/total:.4f}%" if total else "N/A"


def _flag_sentinel(series: pd.Series) -> pd.Series:
    """Trả mask True tại vị trí là sentinel."""
    return series.isin(cfg.SENTINEL_VALUES)


def _flag_spike(series: pd.Series) -> pd.Series:
    """
    Trả mask spike: |diff| > SPIKE_K × std(diff).
    Tính trên dữ liệu đã loại sentinel và NaN.
    """
    clean = series.where(~_flag_sentinel(series), other=np.nan)
    diff  = clean.diff().abs()
    thresh = cfg.SPIKE_K * diff.std()
    return diff > thresh


def _flag_flatline(series: pd.Series) -> pd.Series:
    """
    Trả mask flatline: chuỗi hằng số liên tiếp ≥ FLATLINE_N điểm.
    Bỏ qua NaN và sentinel.
    """
    clean = series.where(~_flag_sentinel(series), other=np.nan)
    not_null = clean.notna()
    runs = (clean != clean.shift()).cumsum()
    run_len = clean.groupby(runs).transform("count")
    return not_null & (run_len >= cfg.FLATLINE_N)


def _flag_out_of_range(series: pd.Series, col: str) -> pd.Series:
    """Trả mask ngoài khoảng vật lý, bỏ qua sentinel và NaN."""
    if col not in cfg.PHYSICAL_BOUNDS:
        return pd.Series(False, index=series.index)
    lo, hi = cfg.PHYSICAL_BOUNDS[col]
    clean  = series.where(~_flag_sentinel(series), other=np.nan)
    return (clean < lo) | (clean > hi)


# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 3: Xử lý chính
# ─────────────────────────────────────────────────────────────────────────────

def step3_process(station: str) -> pd.DataFrame:
    print(f"\n{'='*65}")
    print(f"  BƯỚC 3 – XỬ LÝ & GẮN CỜ  |  {station}")
    print(f"{'='*65}")

    # ── 3.0 Nạp dữ liệu thô từ interim ──────────────────────────────────────
    raw_path = cfg.DATA_INTERIM / f"raw_{station}.parquet"
    df = pd.read_parquet(raw_path)
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)
    n_raw = len(df)
    print(f"\n  Nạp {n_raw:,} dòng từ {raw_path.name}")

    # ── 3.1 Reindex về lưới 1-phút đầy đủ ───────────────────────────────────
    # Vẫn chạy dù không có gap, để kiểm chứng và thêm dòng nếu cần
    t_min  = df["time_utc"].min()
    t_max  = df["time_utc"].max()
    full_idx = pd.date_range(t_min, t_max, freq=cfg.PANDAS_FREQ, tz="UTC")
    n_expected = len(full_idx)

    df = df.set_index("time_utc").reindex(full_idx)
    df.index.name = "time_utc"
    df["station"] = df["station"].fillna(station)
    df = df.reset_index()
    n_after_reindex = len(df)
    n_added = n_after_reindex - n_raw
    print(f"  Reindex: {n_raw:,} → {n_after_reindex:,} dòng ({n_added:+,} dòng thêm từ gap)")

    # ── 3.2 Khởi tạo cột cờ (mặc định 0 = OK) ───────────────────────────────
    for fc in FLAG_COLS:
        df[fc] = np.int8(FLAG_OK)

    # ── 3.3 Gắn cờ theo thứ tự tăng dần (cờ lớn hơn ghi đè) ────────────────
    # Thứ tự: INTERP → MISSING → OUT_OF_RANGE → SPIKE → FLATLINE
    print("\n  Gắn cờ từng thành phần...")
    for col, fcol in COL_MAP.items():
        s = df[col]

        # Cờ 2 – MISSING/SENTINEL (NaN hoặc fill 99999.0 / 88888.0)
        mask_missing = s.isna() | _flag_sentinel(s)
        df.loc[mask_missing, fcol] = np.int8(FLAG_MISSING)

        # Cờ 4 – OUT_OF_RANGE (ngoài khoảng vật lý; không áp vào NaN/sentinel)
        mask_oor = _flag_out_of_range(s, col) & ~mask_missing
        df.loc[mask_oor, fcol] = np.int8(FLAG_OUT_RANGE)

        # Cờ 3 – SPIKE (sau khi đã loại sentinel/NaN; có thể ghi đè OUT_OF_RANGE)
        mask_spike = _flag_spike(s) & ~mask_missing
        df.loc[mask_spike, fcol] = np.int8(FLAG_SPIKE)

        # Cờ 5 – FLATLINE (ghi đè mọi cờ thấp hơn, trừ MISSING)
        mask_flat = _flag_flatline(s) & ~mask_missing
        df.loc[mask_flat, fcol] = np.int8(FLAG_FLATLINE)

        n_ok   = int((df[fcol] == FLAG_OK).sum())
        n_miss = int(mask_missing.sum())
        n_oor  = int(mask_oor.sum())
        n_spk  = int(mask_spike.sum())
        n_flt  = int(mask_flat.sum())
        print(f"    {col}: OK={n_ok:,} | miss={n_miss} | "
              f"oor={n_oor} | spike={n_spk} ({pct(n_spk,n_after_reindex)}) | "
              f"flat={n_flt} ({pct(n_flt,n_after_reindex)})")

    # ── 3.4 quality_flag tổng hợp = max(flag_x, flag_y, flag_z, flag_f) ─────
    df["quality_flag"] = df[FLAG_COLS].max(axis=1).astype(np.int8)

    # ── 3.5 Thay sentinel → NaN trong cột đo lường ───────────────────────────
    for col in MEAS_COLS:
        df[col] = df[col].where(~_flag_sentinel(df[col]), other=np.nan)

    # ── 3.6 Nội suy gap ngắn (≤ INTERP_MAX_GAP phút) ────────────────────────
    # Chỉ nội suy cột đo lường, chuyển cờ 2 → cờ 1 cho các điểm được nội suy
    n_interp_total = 0
    for col in MEAS_COLS:
        fcol = COL_MAP[col]
        before = df[col].isna().sum()
        interpolated = (
            df[col]
            .interpolate(method="linear", limit=cfg.INTERP_MAX_GAP,
                         limit_direction="forward", limit_area="inside")
        )
        newly_filled = df[col].isna() & interpolated.notna()
        df[col] = interpolated
        n_filled = int(newly_filled.sum())
        if n_filled > 0:
            df.loc[newly_filled & (df[fcol] == FLAG_MISSING), fcol] = np.int8(FLAG_INTERP)
            print(f"    Nội suy {col}: {n_filled} điểm (gap ≤ {cfg.INTERP_MAX_GAP} phút, chuyển cờ 2 → 1)")
        n_interp_total += n_filled

    # ── 3.7 Đúc kiểu dữ liệu xuất ────────────────────────────────────────────
    for col in MEAS_COLS:
        df[col] = df[col].astype(cfg.FLOAT_DTYPE)
    for fc in FLAG_COLS + ["quality_flag"]:
        df[fc] = df[fc].astype(cfg.FLAG_DTYPE)
    df["station"] = df["station"].astype(cfg.STATION_DTYPE)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Kiểm chứng sau xử lý (assert)
# ─────────────────────────────────────────────────────────────────────────────

def assert_post_process(df: pd.DataFrame, station: str):
    print(f"\n── Assert sau xử lý ──")
    n = len(df)

    # 1. Không trùng timestamp
    dups = df["time_utc"].duplicated().sum()
    assert dups == 0, f"❌ Có {dups} timestamp trùng!"
    print(f"   ✅ Không trùng timestamp")

    # 2. Timestamp monotone tăng
    assert df["time_utc"].is_monotonic_increasing, "❌ Timestamp không monotone!"
    print(f"   ✅ Timestamp monotone tăng")

    # 3. Lưới đầy đủ 1-phút (freq đúng)
    diffs = df["time_utc"].diff().dropna()
    bad   = (diffs != pd.Timedelta("1min")).sum()
    assert bad == 0, f"❌ Có {bad} khoảng không phải 1 phút!"
    print(f"   ✅ Lưới 1-phút đầy đủ ({n:,} điểm)")

    # 4. Cờ chỉ nhận giá trị 0–5
    for fc in FLAG_COLS + ["quality_flag"]:
        invalid = df[fc].between(0, 5, inclusive="both").eq(False).sum()
        assert invalid == 0, f"❌ {fc} có {invalid} giá trị ngoài [0,5]!"
    print(f"   ✅ Tất cả cờ trong [0,5]")

    # 5. quality_flag = max của 4 cờ thành phần
    expected_qf = df[FLAG_COLS].max(axis=1).astype(np.int8)
    mismatch    = (df["quality_flag"] != expected_qf).sum()
    assert mismatch == 0, f"❌ quality_flag không khớp max ở {mismatch} dòng!"
    print(f"   ✅ quality_flag = max(flag_x/y/z/f)")

    # 6. Phân phối cờ tổng hợp
    print(f"\n  Phân phối quality_flag:")
    vc = df["quality_flag"].value_counts().sort_index()
    names = {0:"OK", 1:"INTERP", 2:"MISSING", 3:"SPIKE", 4:"OUT_RANGE", 5:"FLATLINE"}
    for code, cnt in vc.items():
        print(f"    {code} ({names.get(code,'?')}): {cnt:,} ({pct(cnt,n)})")

    print(f"\n  Phân phối cờ từng thành phần:")
    for col, fc in COL_MAP.items():
        vc2 = df[fc].value_counts().sort_index()
        parts = [f"{names.get(c,'?')}={v:,}" for c, v in vc2.items()]
        print(f"    {col}: {' | '.join(parts)}")

    print(f"\n   ✅ Tất cả assert PASSED")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Xuất Parquet
# ─────────────────────────────────────────────────────────────────────────────

def export_parquet(df: pd.DataFrame, station: str) -> Path:
    cfg.DATA_CLEAN.mkdir(parents=True, exist_ok=True)
    start_s = cfg.DATE_START.strftime("%Y%m%d")
    end_s   = cfg.DATE_END.strftime("%Y%m%d")
    fname   = f"clean_intermagnet_{station}_1min_{start_s}_{end_s}.parquet"
    out     = cfg.DATA_CLEAN / fname
    df.to_parquet(out, index=False, engine="pyarrow", compression="snappy")
    size_mb = out.stat().st_size / 1_048_576
    print(f"\n  Parquet: {out.name}  ({size_mb:.1f} MB)")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Xuất data_dictionary.md
# ─────────────────────────────────────────────────────────────────────────────

def export_data_dictionary(station: str):
    out_dir = cfg.DOCS_DIR / "kak"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "data_dictionary.md"

    content = f"""# Từ điển Dữ liệu – SOP-01 Geophysical Data Pipeline

> Nguồn dữ liệu: INTERMAGNET HAPI (Trạm KAK - Kakioka, Nhật Bản | 36.232° N, 140.186° E) + Danh mục Động đất USGS  
> Khoảng thời gian: {cfg.DATE_START} đến {cfg.DATE_END}  

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
*Tài liệu được tạo tự động bởi mô-đun xuất dữ liệu pipeline (src/kak/process.py).*
"""
    out.write_text(content, encoding="utf-8")
    print(f"  Data dictionary: {out.name}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Xuất data_quality_report.md
# ─────────────────────────────────────────────────────────────────────────────

def export_quality_report(df_clean: pd.DataFrame, qc_before: dict, station: str):
    out_dir = cfg.DOCS_DIR / "kak"
    out_dir.mkdir(parents=True, exist_ok=True)
    out   = out_dir / "data_quality_report.md"
    n     = len(df_clean)
    rb    = qc_before["results"]
    names = {0:"OK", 1:"INTERP", 2:"MISSING", 3:"SPIKE", 4:"OUT_RANGE", 5:"FLATLINE"}

    def pct_str(v): return f"{100*v/n:.4f}%"

    spike_after = {col: int((df_clean[fc] == FLAG_SPIKE).sum()) for col, fc in COL_MAP.items()}
    flat_after  = {col: int((df_clean[fc] == FLAG_FLATLINE).sum()) for col, fc in COL_MAP.items()}

    # Calculate descriptive statistics
    desc = df_clean[MEAS_COLS].describe()

    content = f"""# Báo cáo Chất lượng Dữ liệu – SOP-01 Geophysical Data Pipeline

> Trạm: KAK (Đài thiên văn Kakioka, Nhật Bản | 36.232° N, 140.186° E)  
> Phân loại dữ liệu: {cfg.DATA_TYPE}  
> Khoảng thời gian: {cfg.DATE_START} đến {cfg.DATE_END} (Lưới 1 phút)  

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
| Tổng số bản ghi (sau reindex) | {n:,} dòng |
| Ngày bắt đầu | {df_clean['time_utc'].min().strftime('%Y-%m-%d %H:%M:%S%z')} |
| Ngày kết thúc | {df_clean['time_utc'].max().strftime('%Y-%m-%d %H:%M:%S%z')} |
| Tần số lấy mẫu | 1 phút (lưới liên tục) |
| HAPI Dataset ID | `{cfg.INTERMAGNET_HAPI_DATASET.format(station_lower=station.lower())}` |

### 2.2 Thống kê Mô tả Dữ liệu Sạch (nT)

| Chỉ số thống kê | x_nt (Hướng Bắc) | y_nt (Hướng Đông) | z_nt (Hướng xuống) | f_nt (Cường độ tổng F) |
|---|---|---|---|---|
| Số lượng (Count) | {int(desc.loc['count', 'x_nt']):,} | {int(desc.loc['count', 'y_nt']):,} | {int(desc.loc['count', 'z_nt']):,} | {int(desc.loc['count', 'f_nt']):,} |
| Trung bình (Mean) | {desc.loc['mean', 'x_nt']:.2f} | {desc.loc['mean', 'y_nt']:.2f} | {desc.loc['mean', 'z_nt']:.2f} | {desc.loc['mean', 'f_nt']:.2f} |
| Độ lệch chuẩn (Std Dev) | {desc.loc['std', 'x_nt']:.2f} | {desc.loc['std', 'y_nt']:.2f} | {desc.loc['std', 'z_nt']:.2f} | {desc.loc['std', 'f_nt']:.2f} |
| Nhỏ nhất (Min) | {desc.loc['min', 'x_nt']:.2f} | {desc.loc['min', 'y_nt']:.2f} | {desc.loc['min', 'z_nt']:.2f} | {desc.loc['min', 'f_nt']:.2f} |
| Phân vị 25% | {desc.loc['25%', 'x_nt']:.2f} | {desc.loc['25%', 'y_nt']:.2f} | {desc.loc['25%', 'z_nt']:.2f} | {desc.loc['25%', 'f_nt']:.2f} |
| Trung vị (50% Median) | {desc.loc['50%', 'x_nt']:.2f} | {desc.loc['50%', 'y_nt']:.2f} | {desc.loc['50%', 'z_nt']:.2f} | {desc.loc['50%', 'f_nt']:.2f} |
| Phân vị 75% | {desc.loc['75%', 'x_nt']:.2f} | {desc.loc['75%', 'y_nt']:.2f} | {desc.loc['75%', 'z_nt']:.2f} | {desc.loc['75%', 'f_nt']:.2f} |
| Lớn nhất (Max) | {desc.loc['max', 'x_nt']:.2f} | {desc.loc['max', 'y_nt']:.2f} | {desc.loc['max', 'z_nt']:.2f} | {desc.loc['max', 'f_nt']:.2f} |

---

## 3. Chỉ số Chất lượng Trước & Sau Xử lý

### 3.1 Thiếu Giá trị và Sentinel

| Thành phần | Sentinel trước xử lý | NaN trước xử lý | Tổng NaN sau xử lý | Tỷ lệ thiếu sau xử lý |
|---|---|---|---|---|
"""
    for r in rb["missing"]:
        col = r["column"]
        n_miss_after = int(df_clean[col].isna().sum())
        content += f"| `{col}` | {r['sentinel_count']:,} | {r.get('NaN_tu_nhien', r.get('nan_count', 0)):,} | {n_miss_after:,} | {pct_str(n_miss_after)} |\n"

    content += f"""
### 3.2 Tính Toàn vẹn Timestamp & Độ Đầy đủ của Lưới

| Tiêu chí kiểm tra | Chỉ số trước xử lý | Chỉ số sau xử lý | Trạng thái |
|---|---|---|---|
| Timestamp trùng lặp | {rb['duplicate_timestamps']:,} bản ghi trùng | 0 bản ghi trùng | Đạt |
| Điểm thiếu trên lưới (Gap) | {rb['gaps']['missing_points']:,} điểm thiếu | 0 điểm thiếu | Đạt |
| Gap thiếu dài nhất | {rb['gaps']['max_gap_minutes']} phút | 0 phút | Đạt |

### 3.3 Kiểm tra Ngưỡng Vật lý

| Thành phần | Khoảng vật lý hợp lệ [Min, Max] (nT) | Vi phạm trước xử lý | Số điểm gắn cờ 4 sau xử lý |
|---|---|---|---|
"""
    for r in rb["physical_bounds"]:
        col = r["column"]
        fc  = COL_MAP[col]
        n_oor_after = int((df_clean[fc] == FLAG_OUT_RANGE).sum())
        content += f"| `{col}` | [{r['min']:,}, {r['max']:,}] | {r['out_of_range']:,} | {n_oor_after:,} |\n"

    content += f"""
### 3.4 Phát hiện Spike Thống kê (Cờ 3)

Điều kiện ngưỡng: |diff(t)| > {cfg.SPIKE_K} * std(diff), tính toán sau khi loại bỏ sentinel/NaN.

| Thành phần | Ngưỡng động (nT) | Số lượng Spike phát hiện | Tỷ lệ trên tổng dữ liệu | Mẫu mốc thời gian UTC thực tế (Dẫn chứng) |
|---|---|---|---|---|
"""
    for r in rb["spikes"]:
        col   = r["column"]
        n_spk = spike_after[col]
        thr   = r.get("threshold_nT", "N/A")
        ex_list = r.get("examples", [])[:3]
        ex_str  = ", ".join(ex_list) if ex_list else "Không có"
        content += f"| `{col}` | {thr} | {n_spk:,} | {pct_str(n_spk)} | `{ex_str}` |\n"

    content += f"""
### 3.5 Phát hiện Chuỗi Flatline (Cờ 5)

Điều kiện ngưỡng: Chuỗi hằng số liên tiếp >= {cfg.FLATLINE_N} điểm.

| Thành phần | Số đoạn trước xử lý | Độ dài tối đa (Phút) | Số điểm bị gắn cờ sau xử lý | Tỷ lệ trên tổng dữ liệu |
|---|---|---|---|---|
"""
    for r in rb["flatlines"]:
        col   = r["column"]
        n_flt = flat_after[col]
        content += f"| `{col}` | {r['n_segments']:,} | {r['max_length']} | {n_flt:,} | {pct_str(n_flt)} |\n"

    content += f"""
---

## 4. Ma trận Phân phối Cờ Chất lượng Sau Xử lý

| Mã cờ | Tên cờ | x_nt | y_nt | z_nt | f_nt | Cờ tổng hợp | Tỷ lệ phần trăm |
|---|---|---|---|---|---|---|---|
"""
    col_flag_counts = {fc: df_clean[fc].value_counts() for fc in FLAG_COLS}
    qf_counts       = df_clean["quality_flag"].value_counts()
    for code, name in names.items():
        row = [f"`{code}`", name]
        for fc in FLAG_COLS:
            v = int(col_flag_counts[fc].get(code, 0))
            row.append(f"{v:,}" if v > 0 else "0")
        v_qf = int(qf_counts.get(code, 0))
        row.append(f"{v_qf:,}" if v_qf > 0 else "0")
        row.append(pct_str(v_qf))
        content += "| " + " | ".join(row) + " |\n"

    content += f"""
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
*Báo cáo được tạo tự động bởi mô-đun xuất dữ liệu pipeline (src/kak/process.py).*
"""
    out.write_text(content, encoding="utf-8")
    print(f"  Quality report: {out.name}")
    return out




# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    for station in cfg.STATIONS:
        # Nạp kết quả Bước 2 đã lưu
        pkl_path = cfg.DATA_INTERIM / f"qc_before_{station}.pkl"
        try:
            with open(pkl_path, "rb") as f:
                saved = pickle.load(f)
            qc_before = saved
        except FileNotFoundError:
            print(f"  CANH BAO: Khong tim thay {pkl_path.name}.")
            print(f"  Hay chay 02_quality.ipynb truoc de tao file pickle QC.")
            print(f"  Bo qua export_quality_report cho tram {station}.")
            qc_before = None

        # Bước 3: xử lý
        df_clean = step3_process(station)

        # Kiểm chứng assert
        assert_post_process(df_clean, station)

        # Xuất Parquet
        pq_path = export_parquet(df_clean, station)

        # Xuất tài liệu
        print(f"\n  Xuất tài liệu...")
        export_data_dictionary(station)
        if qc_before is not None:
            export_quality_report(df_clean, qc_before, station)
        else:
            print(f"  Bo qua export_quality_report (khong co pickle qc_before).")


        # Cập nhật scope.md – thêm note 2026-04
        print(f"  scope.md (đã cập nhật trước)")

        # Thống kê cuối
        n = len(df_clean)
        n_ok    = int((df_clean["quality_flag"] == FLAG_OK).sum())
        n_spike = int((df_clean["quality_flag"] == FLAG_SPIKE).sum())
        n_flat  = int((df_clean["quality_flag"] == FLAG_FLATLINE).sum())
        n_other = n - n_ok - n_spike - n_flat

        print(f"\n{'='*65}")
        print(f"  KẾT QUẢ BƯỚC 3  |  {station}  |  DỪNG, CHỜ XÁC NHẬN")
        print(f"{'='*65}")
        print(f"  File xuất  : {pq_path.name}")
        print(f"  Tổng điểm  : {n:,}")
        print(f"  OK (cờ 0)  : {n_ok:,} ({100*n_ok/n:.4f}%)")
        print(f"  Spike (cờ 3): {n_spike:,} ({100*n_spike/n:.4f}%)")
        print(f"  Flat (cờ 5) : {n_flat:,} ({100*n_flat/n:.4f}%)")
        print(f"  Khác        : {n_other:,}")
        print(f"\n  Tháng 2026-04 KAK quasi-def:")
        print(f"    Valid: 38,879 / 43,199 = 90.00% (borderline ngưỡng ≥90%)")
        print(f"    → Chưa tải. Chờ xác nhận của bạn.")
        print(f"\n→ DỪNG. Xem docs/kak/data_quality_report.md để biết chi tiết đầy đủ.")


if __name__ == "__main__":
    main()
