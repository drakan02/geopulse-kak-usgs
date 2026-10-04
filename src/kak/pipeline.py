"""
pipeline.py – Core pipeline xử lý & cờ chất lượng cho dữ liệu địa từ KAK.

Thứ tự xử lý:
  1. Chuyển timestamp → UTC datetime
  2. Xoá dòng trùng timestamp
  3. Thay sentinel (99999.0) → NaN
  4. Reindex theo lưới thời gian đầy đủ 1-phút
  5. Gắn quality_flag: OK(0), INTERP(1), MISSING(2), SPIKE(3), OUT_BOUNDS(4), FLATLINE(5)
  6. Nội suy tuyến tính gap ngắn (≤ INTERP_MAX_GAP phút)
  7. Ép kiểu dữ liệu tối ưu (float32, int8, category)
  8. Kiểm chứng assert độc lập
"""

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
import common.quality_checks as qc


# ─────────────────────────────────────────────────────────────────────────────
# Bước 3: Xử lý
# ─────────────────────────────────────────────────────────────────────────────

def step1_convert_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Bước 3.1 – Đảm bảo time_utc là datetime64[ns, UTC]."""
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["time_utc"]):
        df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    elif df["time_utc"].dt.tz is None:
        df["time_utc"] = df["time_utc"].dt.tz_localize("UTC")
    else:
        df["time_utc"] = df["time_utc"].dt.tz_convert("UTC")
    return df


def step2_remove_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Bước 3.2 – Xoá dòng trùng timestamp, giữ dòng đầu."""
    before = len(df)
    df = df.drop_duplicates(subset=["time_utc"], keep="first")
    removed = before - len(df)
    if removed:
        print(f"  Bước 3.2: Xoá {removed} dòng trùng timestamp.")
    return df, removed


def step3_replace_sentinel(df: pd.DataFrame,
                            sentinel_values: list[float] | None = None) -> pd.DataFrame:
    """Bước 3.3 – Thay sentinel → NaN cho các cột đo lường."""
    sentinel_values = sentinel_values or cfg.SENTINEL_VALUES
    df = df.copy()
    meas_cols = [c for c in df.columns if c.endswith("_nt")]
    replaced_total = 0
    for col in meas_cols:
        mask = df[col].isin(sentinel_values)
        n    = int(mask.sum())
        if n:
            df.loc[mask, col] = np.nan
            replaced_total += n
    print(f"  Bước 3.3: Thay {replaced_total} sentinel → NaN.")
    return df


def step4_reindex(df: pd.DataFrame,
                  freq: str = cfg.PANDAS_FREQ) -> pd.DataFrame:
    """Bước 3.4 – Tạo lưới thời gian đầy đủ; dòng mới có NaN."""
    df = df.set_index("time_utc").sort_index()
    full_idx = pd.date_range(df.index.min(), df.index.max(),
                              freq=freq, tz="UTC", name="time_utc")
    df = df.reindex(full_idx)
    # Điền lại station (category sẽ xử lý sau)
    if "station" in df.columns:
        df["station"] = df["station"].ffill().bfill()
    return df.reset_index()


def _flag_max(existing: pd.Series, new_flag: int, mask: pd.Series) -> pd.Series:
    """Cập nhật cờ: giữ giá trị lớn hơn (cờ nghiêm trọng hơn thắng)."""
    result = existing.copy()
    result[mask] = result[mask].where(result[mask] >= new_flag, new_flag)
    return result


def step5_flag(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bước 3.5 – Gắn quality_flag cho từng cột đo lường.
    Thứ tự ưu tiên khi một điểm thuộc nhiều loại: 5 > 4 > 3 > 2 > 0.
    Tạo cột quality_flag_<component> cho từng cột đo.
    """
    df = df.copy()
    meas_cols = [c for c in df.columns if c.endswith("_nt")]

    for col in meas_cols:
        flag_col = f"quality_flag_{col.replace('_nt', '')}"
        df[flag_col] = np.int8(0)  # mặc định: hợp lệ

        series = df[col]

        # Cờ 2: NaN (sau khi đã thay sentinel và reindex)
        mask_nan = series.isna()
        df[flag_col] = _flag_max(df[flag_col], 2, mask_nan)

        # Cờ 4: ngoài khoảng vật lý
        bounds = cfg.PHYSICAL_BOUNDS.get(col)
        if bounds:
            lo, hi   = bounds
            not_null = series.notna()
            mask_out = not_null & ((series < lo) | (series > hi))
            df[flag_col] = _flag_max(df[flag_col], 4, mask_out)

        # Cờ 3: spike – tính trên series không có sentinel/NaN
        clean = series.copy()
        diff  = clean.diff().abs()
        thresh = cfg.SPIKE_K * diff.std()
        if not np.isnan(thresh):
            mask_spike = diff > thresh
            df[flag_col] = _flag_max(df[flag_col], 3, mask_spike)

        # Cờ 5: flatline
        not_null = series.notna()
        runs      = (series != series.shift()).cumsum()
        run_len   = series.groupby(runs).transform("count")
        mask_flat = not_null & (run_len >= cfg.FLATLINE_N)
        df[flag_col] = _flag_max(df[flag_col], 5, mask_flat)

    # Tạo một cột quality_flag tổng (max của tất cả thành phần)
    flag_cols = [c for c in df.columns if c.startswith("quality_flag_")]
    if flag_cols:
        df["quality_flag"] = df[flag_cols].max(axis=1).astype("int8")

    return df


def step6_interpolate(df: pd.DataFrame,
                       max_gap: int = cfg.INTERP_MAX_GAP) -> pd.DataFrame:
    """
    Bước 3.6 – Nội suy tuyến tính gap ngắn (≤ max_gap điểm).
    Gắn cờ 1 cho các điểm được nội suy.
    Gap dài (> max_gap) giữ NaN.
    """
    df = df.copy()
    meas_cols = [c for c in df.columns if c.endswith("_nt")]

    for col in meas_cols:
        flag_col  = f"quality_flag_{col.replace('_nt', '')}"
        if flag_col not in df.columns:
            flag_col = "quality_flag"

        series = df[col].copy()
        # Chỉ nội suy điểm bị gắn cờ 2 (thiếu)
        null_mask = series.isna()
        if not null_mask.any():
            continue

        # Nội suy tuyến tính với limit = max_gap (số điểm liên tiếp tối đa)
        interpolated = series.interpolate(method="linear", limit=max_gap,
                                           limit_direction="forward")
        # Tìm những điểm đã được nội suy (từ NaN → có giá trị)
        newly_filled = null_mask & interpolated.notna()
        df.loc[newly_filled, col] = interpolated[newly_filled]

        # Gắn cờ 1 chỉ cho các điểm vừa nội suy (không ghi đè cờ ≥ 3)
        if flag_col in df.columns:
            # Cờ 1 chỉ được đặt nếu hiện tại là 2 (thiếu)
            mask_to_flag = newly_filled & (df[flag_col] == 2)
            df.loc[mask_to_flag, flag_col] = np.int8(1)

    # Cập nhật lại cột quality_flag tổng
    flag_cols = [c for c in df.columns if c.startswith("quality_flag_")]
    if flag_cols:
        df["quality_flag"] = df[flag_cols].max(axis=1).astype("int8")

    return df


def step7_cast_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Bước 3.7 – Ép kiểu dữ liệu theo SOP."""
    df = df.copy()
    for col in df.columns:
        if col.endswith("_nt"):
            df[col] = df[col].astype(cfg.FLOAT_DTYPE)
        elif col == "station":
            df[col] = df[col].astype(cfg.STATION_DTYPE)
        elif col.startswith("quality_flag"):
            df[col] = df[col].astype(cfg.FLAG_DTYPE)
    return df


def run_pipeline(df_raw: pd.DataFrame,
                 station: str,
                 sentinel_values: list[float] | None = None) -> tuple[pd.DataFrame, dict]:
    """
    Chạy toàn bộ pipeline Bước 3 cho một trạm.
    Trả (df_clean, processing_log).
    """
    log = {"station": station, "steps": {}}
    sentinel_values = sentinel_values or cfg.SENTINEL_VALUES

    print(f"\n{'='*55}")
    print(f"  Pipeline | {station}")
    print(f"{'='*55}")
    print(f"  Đầu vào: {len(df_raw):,} dòng")

    # 3.1
    df = step1_convert_timestamps(df_raw)
    log["steps"]["1_timestamps"] = "OK"

    # 3.2
    df, n_dup = step2_remove_duplicates(df)
    log["steps"]["2_duplicates_removed"] = n_dup

    # 3.3
    df = step3_replace_sentinel(df, sentinel_values)
    log["steps"]["3_sentinel_replaced"] = "OK"

    # 3.4
    df = step4_reindex(df)
    log["steps"]["4_reindexed_rows"] = len(df)
    print(f"  Bước 3.4: Sau reindex: {len(df):,} dòng")

    # 3.5
    df = step5_flag(df)
    flag_counts = {}
    if "quality_flag" in df.columns:
        flag_counts = df["quality_flag"].value_counts().to_dict()
    log["steps"]["5_flag_counts"] = {int(k): int(v) for k, v in flag_counts.items()}
    print(f"  Bước 3.5: Phân phối cờ: {flag_counts}")

    # 3.6
    df = step6_interpolate(df)
    n_interp = int((df["quality_flag"] == 1).sum()) if "quality_flag" in df.columns else 0
    log["steps"]["6_interpolated_points"] = n_interp
    print(f"  Bước 3.6: {n_interp} điểm được nội suy (cờ 1)")

    # 3.7
    df = step7_cast_dtypes(df)
    log["steps"]["7_dtypes"] = {c: str(df[c].dtype) for c in df.columns}
    print(f"  Bước 3.7: Ép kiểu xong")

    print(f"\n  ✅ Pipeline hoàn tất | {station}: {len(df):,} dòng")
    return df, log


# ─────────────────────────────────────────────────────────────────────────────
# Bước 4: Kiểm chứng (Assert)
# ─────────────────────────────────────────────────────────────────────────────

def run_assertions(df: pd.DataFrame,
                   station: str,
                   expected_rows: int | None = None,
                   qc_before: dict | None = None) -> None:
    """
    Bước 4 – Kiểm chứng sau xử lý.
    Raise AssertionError nếu bất kỳ điều kiện nào không thoả.
    """
    print(f"\n{'─'*50}")
    print(f"  Kiểm chứng (Bước 4) | {station}")
    print(f"{'─'*50}")

    # 4a. Số dòng = số mốc thời gian kỳ vọng
    if expected_rows is not None:
        assert len(df) == expected_rows, (
            f"❌ Số dòng thực tế ({len(df):,}) ≠ kỳ vọng ({expected_rows:,})"
        )
    print(f"  ✅ Số dòng: {len(df):,}")

    # 4b. Timestamp duy nhất
    assert df["time_utc"].nunique() == len(df), "❌ Timestamp không duy nhất!"
    print(f"  ✅ Timestamp duy nhất")

    # 4c. Timestamp tăng dần
    assert df["time_utc"].is_monotonic_increasing, "❌ Timestamp không tăng dần!"
    print(f"  ✅ Timestamp tăng dần")

    # 4d. Không còn sentinel
    meas_cols = [c for c in df.columns if c.endswith("_nt")]
    for col in meas_cols:
        sent_remaining = df[col].isin(cfg.SENTINEL_VALUES).sum()
        assert sent_remaining == 0, (
            f"❌ Còn {sent_remaining} sentinel trong cột {col}!"
        )
    print(f"  ✅ Không còn sentinel")

    # 4e. Cờ chỉ trong phạm vi 0-5
    flag_cols = [c for c in df.columns if c.startswith("quality_flag")]
    for fc in flag_cols:
        invalid_flags = df[fc].dropna()
        invalid_flags = invalid_flags[~invalid_flags.isin(range(6))]
        assert len(invalid_flags) == 0, (
            f"❌ Cột {fc} có giá trị cờ không hợp lệ: {invalid_flags.unique()}"
        )
    print(f"  ✅ quality_flag trong phạm vi 0–5")

    # 4f. Đối chiếu với kết quả Bước 2 (nếu có)
    if qc_before:
        qc_before_gaps = qc_before.get("gaps", {})
        expected_pts   = qc_before_gaps.get("expected_points")
        if expected_pts:
            assert len(df) == expected_pts, (
                f"❌ Số dòng ({len(df)}) ≠ kỳ vọng Bước 2 ({expected_pts})"
            )
        print(f"  ✅ Khớp với kỳ vọng từ Bước 2")

    print(f"\n  🎉 Tất cả kiểm chứng ĐẠT | {station}")
