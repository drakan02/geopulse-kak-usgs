"""
analyze_usgs.py – Khảo sát và phân tích cấu trúc dữ liệu thô USGS Earthquake Catalog.

Thực thi:
  python src/usgs/analyze_usgs.py
"""

import sys
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg

RAW_DIR = cfg.DATA_RAW / "usgs"
INTERIM_DIR = cfg.DATA_INTERIM
INTERIM_DIR.mkdir(parents=True, exist_ok=True)

# Cột USGS CSV chuẩn
USGS_TIME_COL    = "time"
USGS_ID_COL      = "id"
KEEP_COLS = ["time", "latitude", "longitude", "depth", "mag", "magType",
             "nst", "gap", "dmin", "rms", "net", "id", "updated",
             "place", "type", "horizontalError", "depthError", "magError",
             "magNst", "status", "locationSource", "magSource"]


def pct(n, total):
    return f"{100*n/total:.4f}%" if total else "N/A"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Nạp và gộp
# ─────────────────────────────────────────────────────────────────────────────

def load_all() -> pd.DataFrame:
    files = sorted(RAW_DIR.glob(f"usgs_{cfg.USGS_TAG}_M{cfg.USGS_MIN_MAG:.0f}_*.csv"))
    print(f"\n  Nạp {len(files)} file từ {RAW_DIR}")
    frames = []
    for f in files:
        df_f = pd.read_csv(f, low_memory=False)
        frames.append(df_f)
        print(f"    {f.name}: {len(df_f):,} dòng, cols={list(df_f.columns[:5])}...")
    df = pd.concat(frames, ignore_index=True)
    print(f"  Tổng sau gộp (trước dedup): {len(df):,}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 2. Kiểm tra và báo cáo
# ─────────────────────────────────────────────────────────────────────────────

def analyze(df: pd.DataFrame) -> dict:
    results = {}
    n_raw = len(df)
    results["n_raw"] = n_raw

    print(f"\n{'='*65}")
    print(f"  PHÂN TÍCH USGS CATALOG (trước khi làm sạch)")
    print(f"{'='*65}")
    print(f"\n  Tổng dòng sau gộp  : {n_raw:,}")
    print(f"  Cột                : {list(df.columns)}")

    # ── 2.1 Chuyển timestamp ─────────────────────────────────────────────
    print(f"\n── 2.1 Timestamp ──")
    df["time_utc"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df["updated_utc"] = pd.to_datetime(df["updated"], utc=True, errors="coerce")
    bad_time = df["time_utc"].isna().sum()
    print(f"  Không parse được time: {bad_time}")
    print(f"  Từ  : {df['time_utc'].min()}")
    print(f"  Đến : {df['time_utc'].max()}")
    results["bad_time"] = int(bad_time)
    results["t_min"] = str(df["time_utc"].min())
    results["t_max"] = str(df["time_utc"].max())

    # ── 2.2 Trùng event_id ───────────────────────────────────────────────
    print(f"\n── 2.2 Trùng event_id ──")
    n_dup_id = int(df.duplicated(subset=["id"], keep=False).sum())
    n_unique_id = df["id"].nunique()
    n_dup_keep = int(df.duplicated(subset=["id"], keep="first").sum())
    print(f"  Tổng dòng                   : {n_raw:,}")
    print(f"  event_id duy nhất           : {n_unique_id:,}")
    print(f"  Dòng có id trùng (tất cả)   : {n_dup_id:,}")
    print(f"  Dòng dư sẽ xoá (keep=first) : {n_dup_keep:,}")
    print(f"  → Sau dedup                 : {n_raw - n_dup_keep:,}")
    results["n_dup_keep"] = n_dup_keep
    results["n_after_dedup"] = n_raw - n_dup_keep

    # ── 2.3 Ngoài hộp toạ độ / khoảng thời gian ─────────────────────────
    print(f"\n── 2.3 Kiểm tra bbox & time range ──")
    bb = cfg.USGS_BBOX
    out_lat  = ((df["latitude"]  < bb["minlatitude"])  | (df["latitude"]  > bb["maxlatitude"])).sum()
    out_lon  = ((df["longitude"] < bb["minlongitude"]) | (df["longitude"] > bb["maxlongitude"])).sum()
    t_start  = pd.Timestamp(cfg.DATE_START, tz="UTC")
    t_end    = pd.Timestamp(cfg.DATE_END,   tz="UTC") + pd.Timedelta("1D") - pd.Timedelta("1s")
    out_time = ((df["time_utc"] < t_start) | (df["time_utc"] > t_end)).sum()
    print(f"  Ngoài lat [{bb['minlatitude']}, {bb['maxlatitude']}]: {out_lat}")
    print(f"  Ngoài lon [{bb['minlongitude']}, {bb['maxlongitude']}]: {out_lon}")
    print(f"  Ngoài time range: {out_time}")
    results.update({"out_lat": int(out_lat), "out_lon": int(out_lon), "out_time": int(out_time)})

    # ── 2.4 Thiếu giá trị ────────────────────────────────────────────────
    print(f"\n── 2.4 Thiếu giá trị (theo cột quan trọng) ──")
    important = ["mag", "depth", "place", "magType", "status",
                 "latitude", "longitude", "time_utc", "id"]
    miss_data = {}
    for col in important:
        if col not in df.columns and col not in ["time_utc"]:
            print(f"  {col:<20}: CỘT KHÔNG TỒN TẠI")
            continue
        n_miss = int(df[col].isna().sum()) if col in df.columns else 0
        miss_data[col] = n_miss
        print(f"  {col:<20}: {n_miss:,} ({pct(n_miss, n_raw)})")
    results["missing"] = miss_data

    # ── 2.5 Phân phối magnitude ──────────────────────────────────────────
    print(f"\n── 2.5 Phân phối magnitude ──")
    mag = df["mag"].dropna()
    print(f"  Count : {len(mag):,}")
    print(f"  Min   : {mag.min():.2f}")
    print(f"  Max   : {mag.max():.2f}")
    print(f"  Mean  : {mag.mean():.2f}")
    print(f"  Median: {mag.median():.2f}")
    print(f"  Std   : {mag.std():.2f}")
    bins = [4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 8.0, 10.0]
    labels = ["4.0–4.5", "4.5–5.0", "5.0–5.5", "5.5–6.0", "6.0–6.5", "6.5–7.0", "7.0–8.0", "≥8.0"]
    print(f"\n  Phân bố theo dải magnitude:")
    cuts = pd.cut(mag, bins=bins, labels=labels, right=False)
    for lbl, cnt in cuts.value_counts().sort_index().items():
        bar = "█" * (cnt // 10)
        print(f"    {lbl}: {cnt:>5,}  {bar}")
    results["mag_stats"] = {"min": float(mag.min()), "max": float(mag.max()),
                            "mean": float(mag.mean()), "std": float(mag.std())}

    # ── 2.6 Phân phối depth ──────────────────────────────────────────────
    print(f"\n── 2.6 Phân phối độ sâu (depth_km) ──")
    dep = df["depth"].dropna()
    neg_depth = int((dep < 0).sum())
    print(f"  Count  : {len(dep):,}")
    print(f"  Min    : {dep.min():.1f} km {'⚠️ CÓ ÂM' if neg_depth > 0 else ''}")
    print(f"  Max    : {dep.max():.1f} km")
    print(f"  Mean   : {dep.mean():.1f} km")
    print(f"  Median : {dep.median():.1f} km")
    print(f"  Std    : {dep.std():.1f} km")
    print(f"  Độ sâu âm (<0): {neg_depth:,}")
    dbins   = [0, 10, 30, 70, 150, 300, 700, 10000]
    dlabels = ["0–10", "10–30", "30–70", "70–150", "150–300", "300–700", "≥700"]
    cuts_d  = pd.cut(dep.clip(lower=0), bins=dbins, labels=dlabels, right=False)
    print(f"\n  Phân bố độ sâu (km):")
    for lbl, cnt in cuts_d.value_counts().sort_index().items():
        bar = "█" * (cnt // 10)
        print(f"    {lbl:>10} km: {cnt:>5,}  {bar}")
    results["depth_stats"] = {"min": float(dep.min()), "max": float(dep.max()),
                              "neg_count": neg_depth}

    # ── 2.7 magType ──────────────────────────────────────────────────────
    print(f"\n── 2.7 Phân phối magType ──")
    mt = df["magType"].fillna("(NaN)").value_counts()
    for mtype, cnt in mt.items():
        print(f"  {mtype:<10}: {cnt:>6,} ({pct(cnt, n_raw)})")
    results["magtype_dist"] = dict(mt)

    # ── 2.8 Status ───────────────────────────────────────────────────────
    print(f"\n── 2.8 Status ──")
    st = df["status"].fillna("(NaN)").value_counts()
    for sv, cnt in st.items():
        print(f"  {sv:<15}: {cnt:>6,} ({pct(cnt, n_raw)})")
    results["status_dist"] = dict(st)

    # ── 2.9 Số sự kiện theo tháng + phát hiện đột biến ──────────────────
    print(f"\n── 2.9 Số sự kiện theo tháng ──")
    df["ym"] = df["time_utc"].dt.to_period("M")
    monthly  = df.groupby("ym").size().reset_index(name="n_events")
    q75 = monthly["n_events"].quantile(0.75)
    q25 = monthly["n_events"].quantile(0.25)
    iqr = q75 - q25
    threshold_high = q75 + 1.5 * iqr
    print(f"\n  {'Tháng':<10} {'Số SĐ':>7}  Ghi chú")
    print("  " + "─" * 45)
    anomaly_months = []
    for _, row in monthly.iterrows():
        ym, n = str(row["ym"]), int(row["n_events"])
        flag = ""
        if n > threshold_high:
            flag = f"  ⚠️ ĐỈNH (>{threshold_high:.0f})"
            anomaly_months.append(ym)
        bar = "█" * min(n // 10, 40)
        print(f"  {ym:<10} {n:>7,}  {bar}{flag}")
    print(f"\n  Ngưỡng đột biến (Q75+1.5×IQR): {threshold_high:.0f}")
    print(f"  Tháng đỉnh: {anomaly_months if anomaly_months else 'không có'}")
    results["monthly"] = dict(zip(monthly["ym"].astype(str), monthly["n_events"]))
    results["anomaly_months"] = anomaly_months

    # ── 2.10 Giá trị magnitude bất thường ───────────────────────────────
    print(f"\n── 2.10 Magnitude bất thường (< 4.0 hoặc > 9.5) ──")
    below = df[df["mag"] < cfg.USGS_MIN_MAG]
    above = df[df["mag"] > 9.5]
    print(f"  Mag < {cfg.USGS_MIN_MAG}: {len(below):,}  (có thể do USGS revision sau khi catalog tải)")
    print(f"  Mag > 9.5 : {len(above):,}")
    if len(below) > 0:
        print(f"  Ví dụ mag thấp: {below[['id','mag','time_utc']].head(3).to_string(index=False)}")
    if len(above) > 0:
        print(f"  Ví dụ mag cao: {above[['id','mag','time_utc']].head(3).to_string(index=False)}")
    results["mag_below_min"] = int(len(below))
    results["mag_above_max"] = int(len(above))

    return df, results


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tóm tắt
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(results: dict):
    print(f"\n{'='*65}")
    print(f"  TÓM TẮT – USGS GIAI ĐOẠN 1  (TRƯỚC LÀM SẠCH)")
    print(f"{'='*65}")
    print(f"  Vùng            : lat {cfg.USGS_BBOX['minlatitude']}–{cfg.USGS_BBOX['maxlatitude']},"
          f" lon {cfg.USGS_BBOX['minlongitude']}–{cfg.USGS_BBOX['maxlongitude']}")
    print(f"  Tổng sau gộp    : {results['n_raw']:,} dòng")
    print(f"  Thực tế từ–đến  : {results['t_min'][:19]} → {results['t_max'][:19]}")
    print(f"\n  [TRÙNG LẶP]")
    print(f"  event_id trùng  : {results['n_dup_keep']:,} dòng dư (sẽ xoá ở Giai đoạn 2)")
    print(f"  Sau dedup       : {results['n_after_dedup']:,}")
    print(f"\n  [NGOÀI PHẠM VI]")
    print(f"  Ngoài bbox      : lat={results['out_lat']}, lon={results['out_lon']}")
    print(f"  Ngoài time      : {results['out_time']}")
    print(f"\n  [THIẾU GIÁ TRỊ]")
    for col, n in results["missing"].items():
        print(f"  {col:<20}: {n:,}")
    print(f"\n  [MAGNITUDE]")
    ms = results["mag_stats"]
    print(f"  Range: {ms['min']:.1f} – {ms['max']:.1f} | Mean: {ms['mean']:.2f} | Std: {ms['std']:.2f}")
    print(f"  Mag < {cfg.USGS_MIN_MAG}: {results['mag_below_min']} (có thể do USGS revision)")
    print(f"\n  [DEPTH]")
    ds = results["depth_stats"]
    print(f"  Range: {ds['min']:.1f} – {ds['max']:.1f} km | Âm: {ds['neg_count']}")
    print(f"\n  [THÁNG ĐỆT BIẾN]")
    print(f"  {results['anomaly_months'] if results['anomaly_months'] else 'Không có tháng đỉnh'}")
    print(f"\n→ DỪNG. Chờ xác nhận trước khi sang Giai đoạn 2.")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    df = load_all()
    df, results = analyze(df)

    # Lưu interim để dùng ở Giai đoạn 2
    interim_path = INTERIM_DIR / "raw_usgs.parquet"
    df.to_parquet(interim_path, index=False)
    print(f"\n  💾 Lưu interim: {interim_path}")

    print_summary(results)


if __name__ == "__main__":
    main()
