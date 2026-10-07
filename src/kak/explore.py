"""
explore.py – Khảo sát cấu trúc và kiểm tra chất lượng dữ liệu KAK thô.

Mục đích:
  - Khảo sát metadata HAPI info & đặc trưng dữ liệu thô KAK (Bước 1).
  - Đánh giá chất lượng dữ liệu thô trước xử lý (Bước 2): sentinel, NaN, gap, spike, flatline.
  - Lưu kết quả QC interim vào data/interim/qc_before_KAK.pkl.

Thực thi:
  python src/kak/explore.py
"""

import sys
import pickle
from pathlib import Path
from datetime import timezone

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from common.parsers import load_all_intermagnet, get_station_meta


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _meas_cols(df): return [c for c in df.columns if c.endswith("_nt")]

def pct(n, total): return f"{100*n/total:.4f}%" if total else "N/A"


# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 1: Khảo sát cấu trúc
# ─────────────────────────────────────────────────────────────────────────────

def step1_survey(station: str):
    print(f"\n{'='*65}")
    print(f"  BƯỚC 1 – KHẢO SÁT CẤU TRÚC  |  {station}")
    print(f"{'='*65}")

    # 1a. Metadata từ HAPI info endpoint (nguồn chính thức)
    print("\n── 1a. Metadata từ HAPI info endpoint ──")
    meta_hapi = get_station_meta(station)
    for k, v in meta_hapi.items():
        if k != "parameters":
            print(f"   {k:<28}: {v}")

    # Tham số đo lường từ HAPI
    print("\n   Tham số (từ HAPI parameters):")
    for p in meta_hapi.get("parameters", []):
        print(f"   ├─ name={p['name']}, size={p.get('size','scalar')}, "
              f"units={p.get('units','')}, fill={p.get('fill','N/A')}")

    # 1b. Nạp dữ liệu thô
    print("\n── 1b. Nạp dữ liệu thô ──")
    df, meta_file = load_all_intermagnet(station)
    print(f"   Số file tải về : {len(list((cfg.DATA_RAW / 'intermagnet').glob(f'intermagnet_{station}_quasi-def_1min_*.csv')))}")
    print(f"   Số dòng        : {len(df):,}")
    print(f"   Số cột         : {len(df.columns)}")
    print(f"   Cột            : {list(df.columns)}")
    print(f"   Từ             : {df['time_utc'].min()}")
    print(f"   Đến            : {df['time_utc'].max()}")
    print(f"   Span           : {df['time_utc'].max() - df['time_utc'].min()}")

    # 1c. Kiểu dữ liệu
    print("\n── 1c. Kiểu dữ liệu ──")
    print(df.dtypes.to_string())

    # 1d. Thống kê mô tả (CÒN chứa sentinel – chưa xử lý)
    print("\n── 1d. Thống kê mô tả (RAW – còn sentinel 99999.0) ──")
    print(df[_meas_cols(df)].describe().T.to_string())

    # 1e. Phân nhóm cột
    print("\n── 1e. Phân nhóm cột ──")
    time_cols    = [c for c in df.columns if 'time' in c]
    id_cols      = [c for c in df.columns if c == 'station']
    meas_cols    = _meas_cols(df)
    flag_cols    = [c for c in df.columns if 'flag' in c or 'quality' in c]
    known        = set(time_cols + id_cols + meas_cols + flag_cols)
    meta_cols    = [c for c in df.columns if c not in known]
    print(f"   Thời gian  : {time_cols}")
    print(f"   Định danh  : {id_cols}")
    print(f"   Đo lường   : {meas_cols}")
    print(f"   Chất lượng : {flag_cols}")
    print(f"   Metadata   : {meta_cols}")

    return df, meta_hapi


# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 2: Kiểm tra chất lượng (TRƯỚC khi xử lý)
# ─────────────────────────────────────────────────────────────────────────────

def step2_quality(df: pd.DataFrame, station: str) -> dict:
    print(f"\n{'='*65}")
    print(f"  BƯỚC 2 – KIỂM TRA CHẤT LƯỢNG (TRƯỚC XỬ LÝ)  |  {station}")
    print(f"{'='*65}")

    n     = len(df)
    mcols = _meas_cols(df)
    results = {"station": station, "n_rows_raw": n}

    # ── 2.1 Thiếu giá trị: NaN tự nhiên + sentinel ──────────────────────────
    print(f"\n── 2.1 Thiếu giá trị (NaN tự nhiên + sentinel {cfg.SENTINEL_VALUES}) ──")
    missing_rows = []
    for col in mcols:
        nan_cnt  = int(df[col].isna().sum())
        sent_cnt = int(df[col].isin(cfg.SENTINEL_VALUES).sum())
        total    = nan_cnt + sent_cnt
        missing_rows.append({
            "column": col,
            "NaN_tự_nhiên":  nan_cnt,
            "sentinel_count": sent_cnt,
            "tổng_thiếu":    total,
            "thiếu_%":       f"{100*total/n:.4f}%",
        })
        print(f"   {col}: NaN={nan_cnt}, sentinel={sent_cnt}, "
              f"tổng={total} ({100*total/n:.4f}%)")
    results["missing"] = missing_rows

    # ── 2.2 Trùng timestamp ──────────────────────────────────────────────────
    print(f"\n── 2.2 Trùng timestamp ──")
    dup_mask = df.duplicated(subset=["time_utc"], keep=False)
    dup_keep = df.duplicated(subset=["time_utc"], keep="first")
    n_dup    = int(dup_keep.sum())
    print(f"   Timestamp trùng (dòng dư cần xoá): {n_dup}")
    if n_dup > 0:
        print(f"   Ví dụ: {df[dup_mask]['time_utc'].head(4).tolist()}")
    results["duplicate_timestamps"] = n_dup

    # ── 2.3 Thiếu timestamp so với lưới đầy đủ ──────────────────────────────
    print(f"\n── 2.3 Thiếu timestamp (gap so với lưới 1 phút) ──")
    # Dùng timestamp đã dedup để tính gap
    ts_sorted  = df["time_utc"].drop_duplicates().sort_values().reset_index(drop=True)
    t_min, t_max = ts_sorted.iloc[0], ts_sorted.iloc[-1]
    full_idx   = pd.date_range(t_min, t_max, freq=cfg.PANDAS_FREQ, tz="UTC")
    n_expected = len(full_idx)
    n_actual   = len(ts_sorted)
    n_missing  = n_expected - n_actual
    print(f"   Kỳ vọng (lưới đầy đủ): {n_expected:,}")
    print(f"   Thực tế (dedup)       : {n_actual:,}")
    print(f"   Thiếu timestamp       : {n_missing:,} ({pct(n_missing, n_expected)})")

    # Tính phân phối gap
    if n_missing > 0:
        missing_ts   = set(full_idx) - set(ts_sorted)
        missing_list = sorted(missing_ts)
        step         = pd.Timedelta("1min")
        gaps = []
        g    = 1
        for i in range(1, len(missing_list)):
            if missing_list[i] - missing_list[i-1] == step:
                g += 1
            else:
                gaps.append(g); g = 1
        gaps.append(g)
        from collections import Counter
        dist = dict(sorted(Counter(gaps).items()))
        print(f"   Số đoạn gap           : {len(gaps):,}")
        print(f"   Gap dài nhất (phút)   : {max(gaps)}")
        print(f"   Phân phối (độ dài→số lần): {dict(list(dist.items())[:10])}{'...' if len(dist)>10 else ''}")
    else:
        gaps = []
        dist = {}

    results["gaps"] = {
        "expected": n_expected, "actual": n_actual,
        "missing_points": n_missing,
        "n_gap_segments": len(gaps),
        "max_gap_minutes": max(gaps) if gaps else 0,
        "gap_distribution": dist,
    }

    # ── 2.4 Ngoài khoảng vật lý ─────────────────────────────────────────────
    print(f"\n── 2.4 Ngoài khoảng vật lý hợp lệ ──")
    print(f"   (Ngưỡng từ config.PHYSICAL_BOUNDS – nguồn: INTERMAGNET guide + WMM ĐNÁ)")
    bounds_rows = []
    for col in mcols:
        if col not in cfg.PHYSICAL_BOUNDS:
            continue
        lo, hi  = cfg.PHYSICAL_BOUNDS[col]
        # Chỉ xét ô không phải NaN và không phải sentinel
        valid   = df[col].dropna()
        valid   = valid[~valid.isin(cfg.SENTINEL_VALUES)]
        below   = int((valid < lo).sum())
        above   = int((valid > hi).sum())
        total   = below + above
        bounds_rows.append({"column": col, "min": lo, "max": hi,
                            "below_min": below, "above_max": above,
                            "out_of_range": total, "out_%": pct(total, n)})
        print(f"   {col} [{lo:,} – {hi:,} nT]: below={below}, above={above}, total={total} ({pct(total,n)})")
    results["physical_bounds"] = bounds_rows

    # ── 2.5 Spike ────────────────────────────────────────────────────────────
    print(f"\n── 2.5 Spike (|diff| > {cfg.SPIKE_K}σ) – đếm SAU KHI thay sentinel → NaN ──")
    spike_rows = []
    for col in mcols:
        # BƯỚC QUAN TRỌNG: thay sentinel bằng NaN TRƯỚC khi tính diff
        # Nếu không làm bước này, chuyển đổi real↔sentinel tạo diff ~99000 nT → spike giả
        series = df[col].copy()
        series = series.where(~series.isin(cfg.SENTINEL_VALUES), other=np.nan)
        series = series.where(series.notna(), other=np.nan)

        diff   = series.diff().abs()
        std_d  = diff.std()
        thresh = cfg.SPIKE_K * std_d
        mask   = diff > thresh
        cnt    = int(mask.sum())
        ts_ex  = df.loc[mask, "time_utc"].head(5).dt.strftime("%Y-%m-%dT%H:%MZ").tolist()
        spike_rows.append({
            "column":       col,
            "spike_count":  cnt,
            "threshold_nT": round(float(thresh), 3) if not np.isnan(thresh) else None,
            "examples":     ts_ex,
        })
        print(f"   {col}: {cnt} spike (ngưỡng ≈ {thresh:.3f} nT), ví dụ: {ts_ex[:3]}")
    results["spikes"] = spike_rows

    # ── 2.6 Flatline ─────────────────────────────────────────────────────────
    print(f"\n── 2.6 Flatline (≥ {cfg.FLATLINE_N} điểm liên tiếp cùng giá trị) ──")
    flat_rows = []
    for col in mcols:
        series   = df[col].replace(cfg.SENTINEL_VALUES, np.nan)
        not_null = series.notna()
        runs     = (series != series.shift()).cumsum()
        groups   = series[not_null].groupby(runs[not_null])
        segs     = [len(g) for _, g in groups if len(g) >= cfg.FLATLINE_N]
        total_pts = sum(segs)
        flat_rows.append({"column": col, "n_segments": len(segs),
                          "max_length": max(segs) if segs else 0,
                          "total_flagged": total_pts})
        print(f"   {col}: {len(segs)} đoạn flatline, dài nhất={max(segs) if segs else 0}, "
              f"tổng điểm={total_pts} ({pct(total_pts, n)})")
    results["flatlines"] = flat_rows

    return results


# ─────────────────────────────────────────────────────────────────────────────
# TỔNG HỢP & LƯU KẾT QUẢ
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(results: dict, meta_hapi: dict):
    station = results["station"]
    n       = results["n_rows_raw"]

    print(f"\n{'='*65}")
    print(f"  TÓM TẮT BƯỚC 1–2  |  {station}  |  (TRƯỚC XỬ LÝ)")
    print(f"{'='*65}")

    print(f"\n[METADATA HAPI – căn cứ chính thức]")
    print(f"  Dataset      : {meta_hapi.get('hapi_dataset', cfg.INTERMAGNET_HAPI_DATASET.format(station_lower=station.lower()))}")
    print(f"  Loại         : {meta_hapi.get('data_type', cfg.DATA_TYPE)}")
    print(f"  startDate    : {meta_hapi.get('start_date')}")
    print(f"  stopDate     : {meta_hapi.get('stop_date')}")
    print(f"  Toạ độ       : {meta_hapi.get('geodetic_lat')}°N, {meta_hapi.get('geodetic_lon')}°E")
    print(f"  Sentinel     : {meta_hapi.get('sentinel_values')}")

    print(f"\n[CẤU TRÚC DỮ LIỆU]")
    print(f"  Số dòng thô  : {n:,}")

    print(f"\n[CHẤT LƯỢNG TRƯỚC XỬ LÝ]")
    total_missing = sum(r["tổng_thiếu"] for r in results["missing"])
    print(f"  Thiếu giá trị (NaN+sentinel): {total_missing:,} ({pct(total_missing, n*4)})")
    for r in results["missing"]:
        print(f"    {r['column']}: sentinel={r['sentinel_count']}, NaN={r['NaN_tự_nhiên']}, total={r['tổng_thiếu']} ({r['thiếu_%']})")

    g = results["gaps"]
    print(f"  Trùng TS     : {results['duplicate_timestamps']:,}")
    print(f"  Gap điểm     : {g['missing_points']:,} ({pct(g['missing_points'], g['expected'])})")
    print(f"  Gap dài nhất : {g['max_gap_minutes']} phút | Số đoạn: {g['n_gap_segments']}")

    total_out = sum(r["out_of_range"] for r in results["physical_bounds"])
    print(f"  Ngoài khoảng : {total_out:,} điểm")

    total_spk = sum(r["spike_count"] for r in results["spikes"])
    print(f"  Spike        : {total_spk:,} điểm")

    total_flt = sum(r["total_flagged"] for r in results["flatlines"])
    print(f"  Flatline     : {total_flt:,} điểm")

    print(f"\n→ DỪNG LẠI. Chờ xác nhận trước khi sang Bước 3.")


def main():
    for station in cfg.STATIONS:
        df, meta_hapi = step1_survey(station)
        results = step2_quality(df, station)
        print_summary(results, meta_hapi)

        # Lưu kết quả để dùng ở Bước 3–5
        cfg.DATA_INTERIM.mkdir(parents=True, exist_ok=True)
        pkl_path = cfg.DATA_INTERIM / f"qc_before_{station}.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump({"results": results, "meta_hapi": meta_hapi}, f)

        raw_parquet = cfg.DATA_INTERIM / f"raw_{station}.parquet"
        df.to_parquet(raw_parquet, index=False)
        print(f"\n  💾 Lưu: {pkl_path}")
        print(f"  💾 Lưu: {raw_parquet}")


if __name__ == "__main__":
    main()
