"""
quality_checks.py – Các hàm kiểm tra chất lượng dữ liệu (Data Quality Checks).

Nguyên tắc:
  - KHÔNG sửa dữ liệu, chỉ phát hiện và báo cáo.
  - Các kiểm tra: missing values/sentinels, duplicate/missing timestamps,
    physical bounds, statistical spikes, và flatlines.
"""

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _meas_cols(df: pd.DataFrame) -> list[str]:
    """Trả danh sách cột đo lường (_nt)."""
    return [c for c in df.columns if c.endswith("_nt")]


# ─────────────────────────────────────────────────────────────────────────────
# Từng kiểm tra
# ─────────────────────────────────────────────────────────────────────────────

def check_missing(df: pd.DataFrame,
                  sentinel_values: list[float] | None = None) -> pd.DataFrame:
    """
    Đếm NaN và sentinel cho từng cột đo lường.

    Trả DataFrame:
      column | nan_count | sentinel_count | total_missing | missing_pct
    """
    sentinel_values = sentinel_values or cfg.SENTINEL_VALUES
    rows = []
    n = len(df)
    for col in _meas_cols(df):
        nan_cnt = int(df[col].isna().sum())
        # Sentinel: chỉ đếm trong ô không phải NaN
        not_null = df[col].dropna()
        sent_cnt = int(not_null.isin(sentinel_values).sum())
        total    = nan_cnt + sent_cnt
        rows.append({
            "column":         col,
            "nan_count":      nan_cnt,
            "sentinel_count": sent_cnt,
            "total_missing":  total,
            "missing_pct":    round(100.0 * total / n, 4) if n > 0 else 0.0,
        })
    return pd.DataFrame(rows)


def check_duplicate_timestamps(df: pd.DataFrame) -> dict[str, Any]:
    """
    Tìm timestamp trùng.
    Trả dict: count (số dòng trùng), timestamps (list các giá trị bị trùng).
    """
    dup_mask = df.duplicated(subset=["time_utc"], keep=False)
    dup_df   = df[dup_mask]
    dup_ts   = df[df.duplicated(subset=["time_utc"], keep="first")]["time_utc"].tolist()
    return {
        "total_rows_involved": int(dup_mask.sum()),
        "duplicate_count":     len(dup_ts),
        "sample_timestamps":   [str(t) for t in dup_ts[:10]],
    }


def check_missing_timestamps(df: pd.DataFrame,
                               freq: str = cfg.PANDAS_FREQ) -> dict[str, Any]:
    """
    So sánh timestamp thực tế với lưới thời gian đầy đủ theo freq.
    Tính số gap, độ dài gap dài nhất, phân phối độ dài gap.

    Giả định df đã sắp xếp tăng dần theo time_utc.
    """
    ts_col = df["time_utc"]
    t_min  = ts_col.min()
    t_max  = ts_col.max()

    full_idx = pd.date_range(t_min, t_max, freq=freq, tz="UTC")
    actual_set = set(ts_col.dropna())
    missing_set = set(full_idx) - actual_set

    # Tính phân phối độ dài gap: nhóm các timestamp thiếu liên tiếp
    if not missing_set:
        return {
            "expected_points":  len(full_idx),
            "actual_points":    len(ts_col),
            "missing_points":   0,
            "n_gaps":           0,
            "max_gap_minutes":  0,
            "gap_distribution": {},
        }

    missing_sorted = sorted(missing_set)
    freq_td = pd.tseries.frequencies.to_offset(freq)
    step    = pd.Timedelta(freq_td)

    gaps  = []
    g_len = 1
    for i in range(1, len(missing_sorted)):
        if missing_sorted[i] - missing_sorted[i - 1] == step:
            g_len += 1
        else:
            gaps.append(g_len)
            g_len = 1
    gaps.append(g_len)

    from collections import Counter
    dist = Counter(gaps)

    return {
        "expected_points":  len(full_idx),
        "actual_points":    len(ts_col),
        "missing_points":   len(missing_set),
        "n_gaps":           len(gaps),
        "max_gap_minutes":  max(gaps),
        "gap_distribution": dict(sorted(dist.items())),
    }


def check_physical_bounds(df: pd.DataFrame,
                           bounds: dict | None = None) -> pd.DataFrame:
    """
    Kiểm tra giá trị ngoài khoảng vật lý hợp lệ.
    bounds: dict {col_name: (min_val, max_val)}. Mặc định dùng cfg.PHYSICAL_BOUNDS.

    Trả DataFrame:
      column | below_min | above_max | out_of_range | out_pct
    """
    bounds = bounds or cfg.PHYSICAL_BOUNDS
    rows = []
    n = len(df)
    for col in _meas_cols(df):
        if col not in bounds:
            continue
        lo, hi = bounds[col]
        series = df[col].dropna()
        # Loại sentinel trước khi kiểm tra
        series = series[~series.isin(cfg.SENTINEL_VALUES)]
        below  = int((series < lo).sum())
        above  = int((series > hi).sum())
        total  = below + above
        rows.append({
            "column":        col,
            "bound_min":     lo,
            "bound_max":     hi,
            "below_min":     below,
            "above_max":     above,
            "out_of_range":  total,
            "out_pct":       round(100.0 * total / n, 4) if n > 0 else 0.0,
        })
    return pd.DataFrame(rows)


def check_spikes(df: pd.DataFrame,
                 k: float = cfg.SPIKE_K) -> pd.DataFrame:
    """
    Phát hiện spike: |diff| > k × std(diff) cho từng cột đo lường.
    Bỏ qua NaN và sentinel khi tính diff.

    Trả DataFrame:
      column | spike_count | threshold | spike_timestamps (list[str], tối đa 20)
    """
    rows = []
    for col in _meas_cols(df):
        series = df[col].copy()
        # Thay sentinel bằng NaN để không tạo diff giả
        series = series.replace(cfg.SENTINEL_VALUES, np.nan)
        diff   = series.diff().abs()
        thresh = k * diff.std()
        spike_mask = diff > thresh
        spike_idx  = df.index[spike_mask]
        spike_ts   = df.loc[spike_idx, "time_utc"].tolist()

        rows.append({
            "column":           col,
            "spike_count":      int(spike_mask.sum()),
            "threshold_nT":     round(float(thresh), 4) if not np.isnan(thresh) else None,
            "spike_k":          k,
            "spike_timestamps": [str(t) for t in spike_ts[:20]],
        })
    return pd.DataFrame(rows)


def check_flatlines(df: pd.DataFrame,
                    n_min: int = cfg.FLATLINE_N) -> pd.DataFrame:
    """
    Phát hiện chuỗi hằng số (flatline): cùng giá trị lặp ≥ n_min điểm liên tiếp.
    Bỏ qua NaN và sentinel.

    Trả DataFrame:
      column | n_segments | max_length | total_flagged_points
    """
    rows = []
    for col in _meas_cols(df):
        series = df[col].copy().replace(cfg.SENTINEL_VALUES, np.nan)
        # Tạo nhóm runs (run-length encoding)
        not_null = series.notna()
        runs      = (series != series.shift()).cumsum()
        # Chỉ xét các run trong ô không phải NaN
        groups = series[not_null].groupby(runs[not_null])
        segs   = [len(g) for _, g in groups if len(g) >= n_min]

        rows.append({
            "column":               col,
            "n_segments":           len(segs),
            "max_segment_length":   max(segs) if segs else 0,
            "total_flagged_points": sum(segs),
            "flatline_min_length":  n_min,
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Hàm tổng hợp: chạy tất cả kiểm tra cho một DataFrame trạm
# ─────────────────────────────────────────────────────────────────────────────

def run_all_checks(df: pd.DataFrame,
                   station: str,
                   label: str = "before") -> dict[str, Any]:
    """
    Chạy toàn bộ kiểm tra chất lượng.
    label: "before" hoặc "after" (để phân biệt kết quả trước/sau xử lý).

    Trả dict gồm tất cả kết quả.
    """
    print(f"\n{'─'*50}")
    print(f"  Kiểm tra chất lượng | {station} | {label.upper()}")
    print(f"{'─'*50}")

    results = {
        "station": station,
        "label":   label,
        "n_rows":  len(df),
    }

    print("  1. Thiếu giá trị (NaN + sentinel)...")
    results["missing"] = check_missing(df)
    print(results["missing"].to_string(index=False))

    print("\n  2. Trùng timestamp...")
    results["duplicates"] = check_duplicate_timestamps(df)
    d = results["duplicates"]
    print(f"     Dòng liên quan: {d['total_rows_involved']} | Trùng: {d['duplicate_count']}")

    print("\n  3. Thiếu timestamp (gap)...")
    results["gaps"] = check_missing_timestamps(df)
    g = results["gaps"]
    print(f"     Kỳ vọng: {g['expected_points']} | Thực tế: {g['actual_points']} "
          f"| Thiếu: {g['missing_points']} | Số gap: {g['n_gaps']} "
          f"| Gap dài nhất: {g['max_gap_minutes']} phút")

    print("\n  4. Ngoài khoảng vật lý...")
    results["bounds"] = check_physical_bounds(df)
    if not results["bounds"].empty:
        print(results["bounds"].to_string(index=False))
    else:
        print("     (Không có cột nào trong bảng ngưỡng)")

    print(f"\n  5. Spike (|diff| > {cfg.SPIKE_K}σ)...")
    results["spikes"] = check_spikes(df)
    print(results["spikes"][["column", "spike_count", "threshold_nT"]].to_string(index=False))

    print(f"\n  6. Flatline (≥ {cfg.FLATLINE_N} điểm liên tiếp)...")
    results["flatlines"] = check_flatlines(df)
    print(results["flatlines"].to_string(index=False))

    # Thống kê mô tả
    results["describe"] = df[[c for c in df.columns if c.endswith("_nt")]].describe()

    return results
