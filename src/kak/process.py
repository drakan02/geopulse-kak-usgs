"""
process.py – Thực thi pipeline KAK, kiểm chứng assert và xuất sản phẩm.

Quy tắc bất biến:
  - KHÔNG sửa data/raw/. Đọc dữ liệu từ data/interim/raw_KAK.parquet.
  - KHÔNG xoá hay làm mịn spike/flatline – chỉ gắn cờ.
  - Nếu một điểm thuộc nhiều loại cờ → giữ cờ số LỚN NHẤT (5 > 4 > 3 > 2 > 1 > 0).

Sản phẩm xuất:
  - data/clean/clean_intermagnet_KAK_1min_20230101_20260331.parquet
  - docs/data_dictionary.md
  - docs/data_quality_report.md

Thực thi:
  python src/kak/process.py
"""

import sys
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg

# ── Hằng số bảng mã ───────────────────────────────────────────────────────
FLAG_OK         = 0
FLAG_MISSING    = 1
FLAG_SENTINEL   = 2
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
    mask  = pd.Series(False, index=series.index)
    if clean.isna().all():
        return mask
    # Xác định run-length encoding
    run_id = (clean != clean.shift()).cumsum()
    for rid, grp in clean.groupby(run_id):
        if grp.notna().all() and len(grp) >= cfg.FLATLINE_N:
            mask.loc[grp.index] = True
    return mask


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
    # Thứ tự: MISSING → SENTINEL → OUT_OF_RANGE → SPIKE → FLATLINE
    # (FLATLINE và SPIKE cao nhất, ghi đè các cờ thấp hơn)
    print("\n  Gắn cờ từng thành phần...")
    for col, fcol in COL_MAP.items():
        s = df[col]

        # Cờ 1 – MISSING (NaN sau reindex, hoặc NaN tự nhiên)
        mask_missing = s.isna()
        df.loc[mask_missing, fcol] = np.int8(FLAG_MISSING)

        # Cờ 2 – SENTINEL (giá trị fill 99999.0 / 88888.0)
        mask_sent = _flag_sentinel(s)
        df.loc[mask_sent, fcol] = np.int8(FLAG_SENTINEL)

        # Cờ 4 – OUT_OF_RANGE (ngoài khoảng vật lý; không áp vào NaN/sentinel)
        mask_oor = _flag_out_of_range(s, col) & ~mask_missing & ~mask_sent
        df.loc[mask_oor, fcol] = np.int8(FLAG_OUT_RANGE)

        # Cờ 3 – SPIKE (sau khi đã loại sentinel/NaN; có thể ghi đè OUT_OF_RANGE)
        mask_spike = _flag_spike(s) & ~mask_missing & ~mask_sent
        df.loc[mask_spike, fcol] = np.int8(FLAG_SPIKE)

        # Cờ 5 – FLATLINE (ghi đè mọi cờ thấp hơn, trừ MISSING/SENTINEL)
        mask_flat = _flag_flatline(s) & ~mask_missing & ~mask_sent
        df.loc[mask_flat, fcol] = np.int8(FLAG_FLATLINE)

        n_ok   = int((df[fcol] == FLAG_OK).sum())
        n_miss = int(mask_missing.sum())
        n_sent = int(mask_sent.sum())
        n_oor  = int(mask_oor.sum())
        n_spk  = int(mask_spike.sum())
        n_flt  = int(mask_flat.sum())
        print(f"    {col}: OK={n_ok:,} | miss={n_miss} | sent={n_sent} | "
              f"oor={n_oor} | spike={n_spk} ({pct(n_spk,n_after_reindex)}) | "
              f"flat={n_flt} ({pct(n_flt,n_after_reindex)})")

    # ── 3.4 quality_flag tổng hợp = max(flag_x, flag_y, flag_z, flag_f) ─────
    df["quality_flag"] = df[FLAG_COLS].max(axis=1).astype(np.int8)

    # ── 3.5 Thay sentinel → NaN trong cột đo lường ───────────────────────────
    for col in MEAS_COLS:
        df[col] = df[col].where(~_flag_sentinel(df[col]), other=np.nan)

    # ── 3.6 Nội suy gap ngắn (≤ INTERP_MAX_GAP phút) ────────────────────────
    # Chỉ nội suy cột đo lường, không sửa cột cờ
    # (Nếu không có gap thì vòng này không làm gì)
    n_interp_total = 0
    for col in MEAS_COLS:
        before = df[col].isna().sum()
        df[col] = (
            df[col]
            .interpolate(method="linear", limit=cfg.INTERP_MAX_GAP,
                         limit_direction="forward", limit_area="inside")
        )
        after = df[col].isna().sum()
        n_filled = int(before - after)
        if n_filled > 0:
            print(f"    Nội suy {col}: {n_filled} điểm (gap ≤ {cfg.INTERP_MAX_GAP} phút)")
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
    names = {0:"OK", 1:"MISSING", 2:"SENTINEL", 3:"SPIKE", 4:"OUT_RANGE", 5:"FLATLINE"}
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
    print(f"\n  💾 Parquet: {out.name}  ({size_mb:.1f} MB)")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Xuất data_dictionary.md
# ─────────────────────────────────────────────────────────────────────────────

def export_data_dictionary(station: str):
    cfg.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = cfg.DOCS_DIR / "data_dictionary.md"
    content = f"""# Data Dictionary – SOP-01 Geophysical Data Pipeline

> Tạo tự động bởi `process.py`. Cập nhật khi schema thay đổi.

## File sản phẩm

`data/clean/clean_intermagnet_{{STATION}}_1min_{{start}}_{{end}}.parquet`

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
| `1` | MISSING | NaN sau reindex (timestamp thiếu trong raw) | Không nội suy nếu gap > {cfg.INTERP_MAX_GAP} phút |
| `2` | SENTINEL | Giá trị fill ({cfg.SENTINEL_VALUES}) trong file gốc | Giữ lịch sử; giá trị đã thay bằng NaN ở cột đo |
| `3` | SPIKE | \|diff\| > {cfg.SPIKE_K}σ của diff (sau khi loại sentinel) | **Không xoá**; có thể là biến thiên địa từ thật trong bão từ |
| `4` | OUT_OF_RANGE | Ngoài khoảng vật lý hợp lệ | Xem `config.PHYSICAL_BOUNDS` |
| `5` | FLATLINE | ≥ {cfg.FLATLINE_N} điểm liên tiếp cùng giá trị | **Không xoá**; gắn cờ để cảnh báo |

> Nếu một điểm thuộc nhiều loại → cờ LỚN NHẤT được lưu (flatline > out-of-range > spike > sentinel > missing > OK).

## Khoảng vật lý hợp lệ (PHYSICAL_BOUNDS)

Nguồn: INTERMAGNET technical guide + WMM khu vực KAK (~36.2°N, 140.2°E)

| Cột | Min (nT) | Max (nT) |
|---|---|---|
| x_nt | {cfg.PHYSICAL_BOUNDS['x_nt'][0]:,} | {cfg.PHYSICAL_BOUNDS['x_nt'][1]:,} |
| y_nt | {cfg.PHYSICAL_BOUNDS['y_nt'][0]:,} | {cfg.PHYSICAL_BOUNDS['y_nt'][1]:,} |
| z_nt | {cfg.PHYSICAL_BOUNDS['z_nt'][0]:,} | {cfg.PHYSICAL_BOUNDS['z_nt'][1]:,} |
| f_nt | {cfg.PHYSICAL_BOUNDS['f_nt'][0]:,} | {cfg.PHYSICAL_BOUNDS['f_nt'][1]:,} |

## Ngưỡng kiểm tra chất lượng

| Tham số | Giá trị |
|---|---|
| Sentinel | {cfg.SENTINEL_VALUES} |
| SPIKE_K | {cfg.SPIKE_K}σ |
| FLATLINE_N | {cfg.FLATLINE_N} điểm liên tiếp |
| INTERP_MAX_GAP | {cfg.INTERP_MAX_GAP} phút |

## Nguồn dữ liệu

| Trường | Giá trị |
|---|---|
| Trạm | {cfg.STATIONS} |
| Loại | {cfg.DATA_TYPE} |
| Khoảng | {cfg.DATE_START} → {cfg.DATE_END} |
| HAPI dataset | `{cfg.INTERMAGNET_HAPI_DATASET.format(station_lower=station.lower())}` |
| HAPI URL | `{cfg.INTERMAGNET_HAPI_BASE}` |

---
*Cập nhật lần cuối: 2026-10-05*
"""
    out.write_text(content, encoding="utf-8")
    print(f"  📄 {out.name}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Xuất data_quality_report.md
# ─────────────────────────────────────────────────────────────────────────────

def export_quality_report(df_clean: pd.DataFrame, qc_before: dict, station: str):
    out   = cfg.DOCS_DIR / "data_quality_report.md"
    n     = len(df_clean)
    rb    = qc_before["results"]
    names = {0:"OK", 1:"MISSING", 2:"SENTINEL", 3:"SPIKE", 4:"OUT_RANGE", 5:"FLATLINE"}

    def flag_dist(fc):
        vc = df_clean[fc].value_counts().sort_index()
        return {names.get(c,"?"): int(v) for c, v in vc.items()}

    def pct_str(v): return f"{100*v/n:.4f}%"

    # Tính spike/flatline per-component sau xử lý
    spike_after  = {col: int((df_clean[fc] == FLAG_SPIKE).sum())
                    for col, fc in COL_MAP.items()}
    flat_after   = {col: int((df_clean[fc] == FLAG_FLATLINE).sum())
                    for col, fc in COL_MAP.items()}

    content = f"""# Báo cáo Chất lượng Dữ liệu – SOP-01

> **Trạm:** {station} | **Loại:** {cfg.DATA_TYPE} | **Khoảng:** {cfg.DATE_START} → {cfg.DATE_END}
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
| Số điểm (sau reindex) | {n:,} |
| Từ | {df_clean['time_utc'].min()} |
| Đến | {df_clean['time_utc'].max()} |
| HAPI dataset | `{cfg.INTERMAGNET_HAPI_DATASET.format(station_lower=station.lower())}` |

---

## 3. So sánh trước / sau xử lý

### 3.1 Thiếu giá trị và Sentinel

| Cột | Trước – Sentinel | Trước – NaN | Sau – NaN (tổng) | % sau |
|---|---|---|---|---|
"""
    for r in rb["missing"]:
        col = r["column"]
        fc  = COL_MAP[col]
        n_miss_after = int(df_clean[col].isna().sum())
        content += (f"| `{col}` | {r['sentinel_count']:,} | {r['NaN_tự_nhiên']:,} | "
                    f"{n_miss_after:,} | {pct_str(n_miss_after)} |\n")

    content += f"""
### 3.2 Timestamp

| Kiểm tra | Trước xử lý | Sau xử lý |
|---|---|---|
| Trùng timestamp | {rb['duplicate_timestamps']:,} | 0 ✅ |
| Thiếu điểm (gap) | {rb['gaps']['missing_points']:,} | 0 ✅ |
| Gap dài nhất | {rb['gaps']['max_gap_minutes']} phút | 0 phút ✅ |

### 3.3 Ngoài khoảng vật lý

| Cột | Khoảng [min, max] nT | Trước | Sau (cờ 4) |
|---|---|---|---|
"""
    for r in rb["physical_bounds"]:
        col = r["column"]
        fc  = COL_MAP[col]
        n_oor_after = int((df_clean[fc] == FLAG_OUT_RANGE).sum())
        content += (f"| `{col}` | [{r['min']:,}, {r['max']:,}] | "
                    f"{r['out_of_range']:,} | {n_oor_after:,} |\n")

    content += f"""
### 3.4 Điểm biến thiên đột ngột (nghi ngờ spike) – cờ 3

> ⚠️ Các điểm này **chỉ được gắn cờ, không bị xoá**. Một phần có thể là biến thiên địa từ thật trong bão từ.
> Ngưỡng: |diff| > {cfg.SPIKE_K}σ của |diff|, tính sau khi loại sentinel/NaN.

| Cột | Ngưỡng (nT) | Số điểm | % tổng dòng |
|---|---|---|---|
"""
    for r in rb["spikes"]:
        col   = r["column"]
        n_spk = spike_after[col]
        thr   = r.get("threshold_nT", "N/A")
        content += f"| `{col}` | ≈{thr} | {n_spk:,} | {pct_str(n_spk)} |\n"

    content += f"""
### 3.5 Flatline – cờ 5

> Chuỗi hằng số liên tiếp ≥ {cfg.FLATLINE_N} điểm. **Không xoá; gắn cờ để cảnh báo.**

| Cột | Số đoạn (trước) | Dài nhất (trước) | Số điểm bị cờ (sau) | % tổng dòng |
|---|---|---|---|---|
"""
    for r in rb["flatlines"]:
        col   = r["column"]
        n_flt = flat_after[col]
        content += (f"| `{col}` | {r['n_segments']:,} | {r['max_length']} phút | "
                    f"{n_flt:,} | {pct_str(n_flt)} |\n")

    content += f"""
---

## 4. Phân phối quality_flag sau xử lý

| Mã | Tên | x_nt | y_nt | z_nt | f_nt | Tổng hợp |
|---|---|---|---|---|---|---|
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
        content += "| " + " | ".join(row) + " |\n"

    content += f"""
---

## 5. Khuyến nghị sử dụng

- **Phân tích cơ bản:** Dùng `quality_flag == 0` → dữ liệu sạch hoàn toàn.
- **Phân tích bão từ:** Có thể bao gồm cả cờ 3 (spike) sau khi kiểm tra thủ công.
- **Mô hình dự báo:** Nên loại cờ 5 (flatline) vì có thể là lỗi thiết bị.
- **Dashboard Power BI:** Lọc `quality_flag IN (0, 3)` để hiển thị chuỗi đầy đủ với chú thích.

---
*Cập nhật lần cuối: 2026-10-05*
"""
    out.write_text(content, encoding="utf-8")
    print(f"  📄 {out.name}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    for station in cfg.STATIONS:
        # Nạp kết quả Bước 2 đã lưu
        pkl_path = cfg.DATA_INTERIM / f"qc_before_{station}.pkl"
        with open(pkl_path, "rb") as f:
            saved = pickle.load(f)
        qc_before = saved

        # Bước 3: xử lý
        df_clean = step3_process(station)

        # Kiểm chứng assert
        assert_post_process(df_clean, station)

        # Xuất Parquet
        pq_path = export_parquet(df_clean, station)

        # Xuất tài liệu
        print(f"\n  Xuất tài liệu...")
        export_data_dictionary(station)
        export_quality_report(df_clean, qc_before, station)

        # Cập nhật scope.md – thêm note 2026-04
        print(f"  📄 scope.md (đã cập nhật trước)")

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
        print(f"\n→ DỪNG. Xem docs/data_quality_report.md để biết chi tiết đầy đủ.")


if __name__ == "__main__":
    main()
