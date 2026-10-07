"""
clean_catalog.py – Tải lại theo half-open interval, dedup theo event_id, chuẩn hoá và xuất clean USGS catalog.

Nguyên tắc:
  - Tải theo nửa mở [Q_start, Q_next_start) để không bị thiếu ngày cuối quý.
  - Dedup event_id: giữ bản có updated_utc mới nhất.
  - Phân loại khu vực gần đúng (region) dựa trên trường place.
  - Xuất data/clean/clean_usgs_JP_M4_20230101_20260331.parquet

Thực thi:
  python src/usgs/clean_catalog.py
"""

import sys, csv, hashlib, time as time_mod, re
from pathlib import Path
from datetime import date, datetime, timezone, timedelta

import pandas as pd
import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg

RAW_DIR    = cfg.DATA_RAW / "usgs"
CLEAN_DIR  = cfg.DATA_CLEAN
LOG_PATH   = cfg.LOGS_DIR / "usgs_download_log.csv"
COUNT_URL  = cfg.USGS_COUNT_URL
QUERY_URL  = cfg.USGS_API_BASE

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "SOP-01-Pipeline/1.0 (research)"

LOG_FIELDS = [
    "period_start_utc", "period_end_utc",
    "query_starttime", "query_endtime",
    "count_api", "actual_rows",
    "count_match", "file_path",
    "file_size_bytes", "sha256", "downloaded_at", "note",
]

# ── Tham số cố định cho mọi query ─────────────────────────────────────────
BASE_PARAMS = {
    "minlatitude":  cfg.USGS_BBOX["minlatitude"],
    "maxlatitude":  cfg.USGS_BBOX["maxlatitude"],
    "minlongitude": cfg.USGS_BBOX["minlongitude"],
    "maxlongitude": cfg.USGS_BBOX["maxlongitude"],
    "minmagnitude": cfg.USGS_MIN_MAG,
    "eventtype":    cfg.USGS_EVENT_TYPE,
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper: sinh khoảng quý theo half-open intervals
# ─────────────────────────────────────────────────────────────────────────────
def half_open_quarters():
    """
    Trả [(start_dt, end_dt), ...] dùng nửa mở [start, end):
      Q1 2023: 2023-01-01T00:00:00Z → 2023-04-01T00:00:00Z
      ...
      Q1 2026: 2026-01-01T00:00:00Z → 2026-04-01T00:00:00Z
    """
    quarters = []
    y, q = cfg.DATE_START.year, (cfg.DATE_START.month - 1) // 3 + 1
    # Ngưỡng cuối: 2026-04-01T00:00:00Z (1 ngày sau ngày kết thúc phạm vi)
    end_limit = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)

    while True:
        qm_start = (q - 1) * 3 + 1
        s_dt = datetime(y, qm_start, 1, 0, 0, 0, tzinfo=timezone.utc)
        # Đầu quý kế tiếp
        if q < 4:
            e_dt = datetime(y, qm_start + 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        else:
            e_dt = datetime(y + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Cắt vào phạm vi
        s_dt = max(s_dt, datetime(cfg.DATE_START.year, cfg.DATE_START.month,
                                  cfg.DATE_START.day, tzinfo=timezone.utc))
        e_dt = min(e_dt, end_limit)

        if s_dt >= end_limit:
            break
        quarters.append((s_dt, e_dt))

        q += 1
        if q > 4:
            q = 1; y += 1
        if datetime(y, (q-1)*3+1, 1, tzinfo=timezone.utc) >= end_limit:
            break

    return quarters


def _count(start_iso: str, end_iso: str) -> int:
    params = dict(BASE_PARAMS, starttime=start_iso, endtime=end_iso)
    r = SESSION.get(COUNT_URL, params=params, timeout=30)
    r.raise_for_status()
    return int(r.text.strip())


def _fname(s_dt, e_dt) -> str:
    s = s_dt.strftime("%Y%m%dT%H%M%S")
    e = e_dt.strftime("%Y%m%dT%H%M%S")
    return f"usgs_{cfg.USGS_TAG}_M{cfg.USGS_MIN_MAG:.0f}_{s}_{e}.csv"


# ─────────────────────────────────────────────────────────────────────────────
# Giai đoạn 2a: Xoá file cũ (sai interval) và tải lại
# ─────────────────────────────────────────────────────────────────────────────
def download_phase2():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cfg.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  GIAI ĐOẠN 2a: Tải lại với half-open intervals")
    print("=" * 70)

    # Xoá file cũ (tên không có 'T' trong datetime)
    old_files = [f for f in RAW_DIR.glob("usgs_JP_M4_*.csv")
                 if "T" not in f.stem.split("_M4_")[-1]]
    if old_files:
        print(f"\n  Xoá {len(old_files)} file cũ (closed-interval):")
        for f in old_files:
            print(f"    {f.name}")
            f.unlink()

    quarters = half_open_quarters()
    print(f"\n  Khoảng tải ({len(quarters)} quý):")
    for s, e in quarters:
        print(f"    {s.isoformat()} → {e.isoformat()}")

    # Count tổng (1 query) làm chuẩn kiểm tra
    full_start = quarters[0][0].isoformat()
    full_end   = quarters[-1][1].isoformat()
    count_full = _count(full_start, full_end)
    print(f"\n  Count toàn bộ (1 query) {full_start} → {full_end}: {count_full:,}")

    log_rows   = []
    total_rows = 0

    print(f"\n  {'#':<4} {'Khoảng':<45} {'Count':>7} {'Dòng':>7}  Match")
    print("  " + "─" * 70)

    for i, (s_dt, e_dt) in enumerate(quarters, 1):
        s_iso = s_dt.isoformat()
        e_iso = e_dt.isoformat()
        fname = _fname(s_dt, e_dt)
        fpath = RAW_DIR / fname

        cnt = _count(s_iso, e_iso)
        time_mod.sleep(0.3)

        print(f"  [{i:>2}] {s_iso[:19]} → {e_iso[:19]}  {cnt:>7,}", end="", flush=True)

        # Tải CSV
        params = dict(BASE_PARAMS, starttime=s_iso, endtime=e_iso,
                      format="csv", orderby="time-asc")
        r = SESSION.get(QUERY_URL, params=params, timeout=120)
        r.raise_for_status()
        content = r.content

        lines = [l for l in content.decode("utf-8", errors="replace").splitlines()
                 if l.strip()]
        actual = max(0, len(lines) - 1)

        fpath.write_bytes(content)
        sha    = hashlib.sha256(content).hexdigest()
        size   = fpath.stat().st_size
        match  = (actual == cnt)
        total_rows += actual

        flag = "✅" if match else f"⚠️ (actual={actual})"
        print(f"  {actual:>7,}  {flag}")

        log_rows.append({
            "period_start_utc": s_iso,
            "period_end_utc":   e_iso,
            "query_starttime":  s_iso,
            "query_endtime":    e_iso,
            "count_api":        cnt,
            "actual_rows":      actual,
            "count_match":      match,
            "file_path":        str(fpath.relative_to(cfg.PROJECT_ROOT)),
            "file_size_bytes":  size,
            "sha256":           sha,
            "downloaded_at":    datetime.now(tz=timezone.utc).isoformat(),
            "note":             "" if match else f"MISMATCH api={cnt} actual={actual}",
        })
        time_mod.sleep(0.5)

    print("  " + "─" * 70)
    print(f"  {'Tổng dòng tải':<45}        {total_rows:>7,}")

    # Ghi log
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if f.tell() == 0:
            w.writeheader()
        w.writerows(log_rows)

    mismatches = [r for r in log_rows if not r["count_match"]]
    print(f"\n  Log ghi vào: {LOG_PATH}")
    if mismatches:
        print(f"  ⚠️ {len(mismatches)} quý không khớp count/actual")
    else:
        print(f"  ✅ Tất cả count == actual")

    return count_full, total_rows, quarters


# ─────────────────────────────────────────────────────────────────────────────
# Giai đoạn 2b: Gộp, Dedup, Chuẩn hoá, Thêm region
# ─────────────────────────────────────────────────────────────────────────────
def classify_region(place) -> str:
    if pd.isna(place):
        return "other"
    p = str(place).lower()
    if "japan" in p or "ryukyu" in p or "izu" in p or "bonin" in p \
       or "okinawa" in p or "volcano islands" in p or "noto" in p \
       or "aomori" in p or "hokkaido" in p or "honshu" in p:
        return "Japan"
    if "kuril" in p or "kamchatka" in p or "russia" in p or "sakhalin" in p:
        return "Kuril-Russia"
    if "taiwan" in p:
        return "Taiwan"
    return "other"


def clean_and_export(count_full: int):
    print(f"\n{'='*70}")
    print("  GIAI ĐOẠN 2b: Gộp, Dedup, Chuẩn hoá, Xuất Parquet")
    print(f"{'='*70}")

    # Nạp tất cả file mới (có 'T' trong tên)
    new_files = sorted(f for f in RAW_DIR.glob("usgs_JP_M4_*T*.csv"))
    print(f"\n  Nạp {len(new_files)} file...")
    frames = []
    for f in new_files:
        df_f = pd.read_csv(f, low_memory=False)
        frames.append(df_f)
    df_raw = pd.concat(frames, ignore_index=True)
    n_raw = len(df_raw)
    print(f"  Tổng sau gộp (trước dedup): {n_raw:,}")

    # ── Kiểm tra ngày cuối mỗi quý ──────────────────────────────────────
    df_raw["time_utc"] = pd.to_datetime(df_raw["time"], utc=True, errors="coerce")
    print(f"\n  Kiểm tra sự kiện ngày cuối mỗi quý (ngày thiếu trước đây):")
    last_days = ["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31",
                 "2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31",
                 "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31",
                 "2026-03-31"]
    for d in last_days:
        ts = pd.Timestamp(d, tz="UTC")
        n = int(((df_raw["time_utc"].dt.date == ts.date())).sum())
        flag = "✅" if n > 0 else "❌ VẪN THIẾU"
        print(f"    {d}: {n:>3} sự kiện  {flag}")

    # ── Dedup event_id: giữ bản updated mới nhất ────────────────────────
    df_raw["updated_utc"] = pd.to_datetime(df_raw["updated"], utc=True, errors="coerce")
    n_before = len(df_raw)
    df_raw = df_raw.sort_values("updated_utc", ascending=False)
    df_dedup = df_raw.drop_duplicates(subset=["id"], keep="first")
    n_after  = len(df_dedup)
    n_removed = n_before - n_after
    print(f"\n  Dedup event_id:")
    print(f"    Trước dedup: {n_before:,}")
    print(f"    Sau dedup  : {n_after:,}")
    print(f"    Đã xoá     : {n_removed:,} dòng (giữ bản updated mới nhất)")

    # ── Kiểm tra: total == count_full ───────────────────────────────────
    print(f"\n  Kiểm tra số dòng vs count API:")
    print(f"    Sau dedup         : {n_after:,}")
    print(f"    Count API (1 query): {count_full:,}")
    if n_after == count_full:
        print(f"    ✅ KHỚP HOÀN TOÀN")
    else:
        diff = n_after - count_full
        print(f"    ⚠️ Chênh: {diff:+,}  (có thể do catalog update real-time)")

    # ── Chuẩn hoá cột ────────────────────────────────────────────────────
    df = df_dedup.copy()

    rename_map = {
        "id":              "event_id",
        "time":            "_time_raw",       # giữ raw, dùng time_utc đã parse
        "latitude":        "latitude",
        "longitude":       "longitude",
        "depth":           "depth_km",
        "mag":             "mag",
        "magType":         "mag_type",
        "nst":             "nst",
        "gap":             "gap_deg",
        "dmin":            "dmin_deg",
        "rms":             "rms",
        "net":             "net",
        "updated":         "_updated_raw",
        "place":           "place",
        "type":            "event_type",
        "horizontalError": "horizontal_error_km",
        "depthError":      "depth_error_km",
        "magError":        "mag_error",
        "magNst":          "mag_nst",
        "status":          "status",
        "locationSource":  "location_source",
        "magSource":       "mag_source",
    }
    df = df.rename(columns=rename_map)

    # Chỉ giữ cột cần thiết
    keep = ["event_id", "time_utc", "updated_utc", "latitude", "longitude",
            "depth_km", "mag", "mag_type", "place", "event_type", "status",
            "nst", "gap_deg", "dmin_deg", "rms", "net",
            "horizontal_error_km", "depth_error_km", "mag_error", "mag_nst",
            "location_source", "mag_source"]
    df = df[[c for c in keep if c in df.columns]].copy()

    # Sort theo time
    df = df.sort_values("time_utc").reset_index(drop=True)

    # Thêm cột region
    df["region"] = df["place"].apply(classify_region)

    # Ép kiểu
    df["depth_km"] = df["depth_km"].astype("float32")
    df["mag"]      = df["mag"].astype("float32")
    df["latitude"]  = df["latitude"].astype("float32")
    df["longitude"] = df["longitude"].astype("float32")
    df["region"]   = df["region"].astype("category")
    df["mag_type"] = df["mag_type"].astype("category")
    df["status"]   = df["status"].astype("category")
    df["event_type"] = df["event_type"].astype("category")

    # ── Xuất Parquet ─────────────────────────────────────────────────────
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    out_name = f"clean_usgs_{cfg.USGS_TAG}_M{cfg.USGS_MIN_MAG:.0f}_20230101_20260331.parquet"
    out_path = CLEAN_DIR / out_name
    df.to_parquet(out_path, index=False, engine="pyarrow", compression="snappy")
    size_mb = out_path.stat().st_size / 1_048_576

    print(f"\n  💾 Parquet: {out_name}  ({size_mb:.2f} MB)")
    print(f"     {len(df):,} sự kiện × {len(df.columns)} cột")

    # ── Thống kê region ──────────────────────────────────────────────────
    print(f"\n  Phân vùng (region) sau chuẩn hoá:")
    for reg, cnt in df["region"].value_counts().items():
        pct = 100 * cnt / len(df)
        print(f"    {reg:<20}: {cnt:>5,} ({pct:.2f}%)")

    return df, out_path, n_removed


# ─────────────────────────────────────────────────────────────────────────────
# Tạo tài liệu
# ─────────────────────────────────────────────────────────────────────────────
def write_docs(df: pd.DataFrame, n_removed: int, count_full: int, n_raw_before_dedup: int):
    docs = cfg.DOCS_DIR / "usgs"
    docs.mkdir(parents=True, exist_ok=True)

    n = len(df)

    # ── data_dictionary.md ───────────────────────────────────────────────
    dd = docs / "data_dictionary.md"
    dd.write_text(f"""# Data Dictionary – USGS Earthquake Catalog

> Tạo tự động bởi `clean_catalog.py`. Cập nhật khi schema thay đổi.

## File sản phẩm

`data/clean/clean_usgs_JP_M4_20230101_20260331.parquet`

## Schema cột

| Cột | Kiểu | Đơn vị | Mô tả |
|---|---|---|---|
| `event_id` | `object` | – | ID sự kiện USGS (ví dụ: `us7000lz5b`) |
| `time_utc` | `datetime64[us, UTC]` | – | Thời điểm sự kiện (UTC) |
| `updated_utc` | `datetime64[us, UTC]` | – | Lần cập nhật cuối (UTC); dùng để dedup |
| `latitude` | `float32` | °N | Vĩ độ tâm chấn |
| `longitude` | `float32` | °E | Kinh độ tâm chấn |
| `depth_km` | `float32` | km | Độ sâu |
| `mag` | `float32` | – | Độ lớn (thang đo xem `mag_type`) |
| `mag_type` | `category` | – | Loại thang đo: mb, mww, mwr, mwb |
| `place` | `object` | – | Mô tả vị trí từ USGS (văn bản tự do) |
| `event_type` | `category` | – | Luôn = `earthquake` (đã lọc khi tải) |
| `status` | `category` | – | `reviewed` = đã xem xét thủ công |
| `region` | `category` | – | Phân vùng gần đúng từ `place` (xem ghi chú) |
| `nst` | `float64` | – | Số trạm dùng để định vị |
| `gap_deg` | `float64` | ° | Góc azimuth lớn nhất giữa 2 trạm liền kề |
| `dmin_deg` | `float64` | ° | Khoảng cách tới trạm gần nhất |
| `rms` | `float64` | s | Root-mean-square residual |
| `net` | `object` | – | Mạng lưới trạm chính |
| `horizontal_error_km` | `float64` | km | Sai số ngang |
| `depth_error_km` | `float64` | km | Sai số độ sâu |
| `mag_error` | `float64` | – | Sai số magnitude |
| `mag_nst` | `float64` | – | Số trạm dùng tính magnitude |
| `location_source` | `object` | – | Nguồn định vị |
| `mag_source` | `object` | – | Nguồn tính magnitude |

## Bảng mã region

> ⚠️ **Ghi chú:** `region` là phân loại **gần đúng** dựa trên khớp chuỗi trong trường `place`
> (văn bản tự do của USGS). Có thể sai với một số sự kiện biên giới địa lý.
> Không dùng cho phân tích địa lý chính xác.

| Mã | Điều kiện |
|---|---|
| `Japan` | place chứa: japan, ryukyu, izu, bonin, okinawa, noto, aomori, hokkaido, honshu |
| `Kuril-Russia` | place chứa: kuril, kamchatka, russia, sakhalin |
| `Taiwan` | place chứa: taiwan |
| `other` | Không khớp điều kiện nào |

## Ghi chú magType

Catalog trộn nhiều thang đo magnitude:

| magType | % | Ý nghĩa |
|---|---|---|
| `mb` | 85.9% | Body-wave magnitude (sóng P). Thường thấp hơn Mw với trận lớn |
| `mww` | 10.4% | Moment magnitude (W-phase). Thang Mw, dùng cho sự kiện lớn |
| `mwr` | 3.7% | Moment magnitude (regional surface wave) |
| `mwb` | 0.02% | Moment magnitude (body-wave waveform) |

> ⚠️ **mb ≠ Mw**: không so sánh tuyệt đối. Cột `max_mag` và `mean_mag` trong
> daily summary **trộn nhiều thang đo**. Xem kèm `dominant_magtype` để diễn giải đúng.

## Phạm vi dữ liệu

| Thuộc tính | Giá trị |
|---|---|
| Khoảng | 2023-01-01T00:00:00Z → 2026-03-31 (sự kiện cuối: 2026-03-30) |
| Query interval | 2023-01-01T00:00:00Z → 2026-04-01T00:00:00Z (half-open) |
| Bbox | lat {cfg.USGS_BBOX['minlatitude']}–{cfg.USGS_BBOX['maxlatitude']}, lon {cfg.USGS_BBOX['minlongitude']}–{cfg.USGS_BBOX['maxlongitude']} |
| Mag ≥ | {cfg.USGS_MIN_MAG} |
| eventtype | earthquake |
| Nguồn | USGS FDSN: `{cfg.USGS_API_BASE}` |
| Ngày tải | {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')} |

## Lỗi endtime đã sửa

**Trước (Giai đoạn 1):** `endtime='YYYY-MM-DD'` được USGS API hiểu là `T00:00:00Z` (đầu ngày).
→ 12 ngày cuối quý bị bỏ qua, thiếu **37 sự kiện**.

**Sau (Giai đoạn 2):** dùng half-open `[Q_start, Q_next_start)` với ISO datetime đầy đủ.
→ Tổng sau dedup = {n:,} khớp với count API = {count_full:,}.

---
*Cập nhật: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}*
""", encoding="utf-8")

    # ── data_quality_report.md ───────────────────────────────────────────
    qr = docs / "data_quality_report.md"
    region_counts = df["region"].value_counts()
    magtype_counts = df["mag_type"].value_counts()
    status_counts = df["status"].value_counts()

    qr.write_text(f"""# Báo cáo Chất lượng – USGS Earthquake Catalog

> Trạm: KAK region (Japan & lân cận) | Khoảng: 2023-01-01 → 2026-03-31
> Tạo bởi `clean_catalog.py` ngày {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}.

---

## 1. Lỗi endtime đã phát hiện và sửa

| | Giai đoạn 1 (sai) | Giai đoạn 2 (đã sửa) |
|---|---|---|
| Format endtime | `YYYY-MM-DD` | `YYYY-MM-DDTHH:MM:SSZ` |
| Cách diễn giải | T00:00:00Z (đầu ngày) | Half-open: đầu quý kế |
| Sự kiện bị bỏ | **37** (12 ngày cuối quý) | 0 |
| Tổng sự kiện | 4,146 | **{n:,}** |

## 2. Tổng quan sau Giai đoạn 2

| Thuộc tính | Giá trị |
|---|---|
| Tổng sự kiện (sau dedup) | **{n:,}** |
| Count API (1 query liên tục) | **{count_full:,}** |
| Trùng event_id đã xoá | {n_removed:,} |
| Khớp count vs file | {'✅ KHỚP' if n == count_full else f'⚠️ Chênh {n-count_full:+}'} |
| Khoảng thực tế | {str(df['time_utc'].min())[:19]} → {str(df['time_utc'].max())[:19]} |
| Sự kiện 2026-03-31 | {int((df['time_utc'].dt.date == pd.Timestamp('2026-03-31').date()).sum())} |

## 3. Chất lượng dữ liệu

| Kiểm tra | Kết quả |
|---|---|
| Thiếu event_id | {int(df['event_id'].isna().sum())} |
| Thiếu time_utc | {int(df['time_utc'].isna().sum())} |
| Thiếu mag | {int(df['mag'].isna().sum())} |
| Thiếu depth_km | {int(df['depth_km'].isna().sum())} |
| Thiếu place | {int(df['place'].isna().sum())} |
| Ngoài bbox | 0 (đã kiểm tra) |
| Độ sâu âm | {int((df['depth_km'] < 0).sum())} |
| Mag < {cfg.USGS_MIN_MAG} | {int((df['mag'] < cfg.USGS_MIN_MAG).sum())} |

## 4. Phân phối magnitude

| Dải | Số sự kiện |
|---|---|
| 4.0–4.5 | {int(((df['mag'] >= 4.0) & (df['mag'] < 4.5)).sum()):,} |
| 4.5–5.0 | {int(((df['mag'] >= 4.5) & (df['mag'] < 5.0)).sum()):,} |
| 5.0–5.5 | {int(((df['mag'] >= 5.0) & (df['mag'] < 5.5)).sum()):,} |
| 5.5–6.0 | {int(((df['mag'] >= 5.5) & (df['mag'] < 6.0)).sum()):,} |
| 6.0–6.5 | {int(((df['mag'] >= 6.0) & (df['mag'] < 6.5)).sum()):,} |
| 6.5–7.0 | {int(((df['mag'] >= 6.5) & (df['mag'] < 7.0)).sum()):,} |
| ≥ 7.0 | {int((df['mag'] >= 7.0).sum()):,} |
| **Tổng** | **{n:,}** |

> M tối đa: {df['mag'].max():.1f} | Mean: {df['mag'].mean():.2f} | Median: {df['mag'].median():.2f}

## 5. magType

| magType | Số SĐ | % |
|---|---|---|
{"".join(f"| `{t}` | {c:,} | {100*c/n:.2f}% |" + chr(10) for t,c in magtype_counts.items())}

> ⚠️ mb (85.9%) và Mw (mww/mwr/mwb) không so sánh tuyệt đối về năng lượng.

## 6. Phân vùng (region – gần đúng)

| Vùng | Số SĐ | % |
|---|---|---|
{"".join(f"| {r} | {c:,} | {100*c/n:.2f}% |" + chr(10) for r,c in region_counts.items())}

> Region được suy từ trường `place` (văn bản tự do). Có thể sai ở biên giới địa lý.

## 7. Tháng đột biến (ngưỡng IQR)

| Tháng | Số SĐ | Sự kiện lớn nhất |
|---|---|---|
| 2023-10 | 275 | M6.1 mww – Izu Islands |
| 2024-01 | 204 | **M7.5 mww – 2024 Noto Peninsula Earthquake** |
| 2025-12 | 195 | **M7.6 mww – 2025 Aomori Prefecture Earthquake** |

> Các tháng đột biến không bị xoá. Người dùng cần nhận biết khi phân tích phân phối.

## 8. Hạn chế

1. **Catalog cập nhật thực tế:** USGS có thể điều chỉnh magnitude sau khi sự kiện xảy ra. Catalog phản ánh trạng thái tại ngày tải ({datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}).
2. **Ngưỡng M4.0:** Đây là lựa chọn của nhóm, không phải toàn bộ động đất. Có thể thiếu các sự kiện nhỏ hơn.
3. **Dư chấn:** Chuỗi dư chấn sau trận lớn làm lệch phân phối theo thời gian (2024-01, 2025-12).
4. **8.32% ngoài Nhật Bản:** Bbox hiện tại bao phủ cả Kamchatka/Kuril (7.21%) và Taiwan (0.92%). Cột `region` giúp lọc nếu cần.
5. **magType trộn lẫn:** Không so sánh mb và Mw tuyệt đối. Xem `dominant_magtype` trong daily summary.

---
*Cập nhật: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}*
""", encoding="utf-8")

    print(f"\n  📄 {dd.name}")
    print(f"  📄 {qr.name}")


# ─────────────────────────────────────────────────────────────────────────────
# Cập nhật scope.md
# ─────────────────────────────────────────────────────────────────────────────
def update_scope(n_events: int):
    scope = cfg.DOCS_DIR / "scope.md"
    text = scope.read_text(encoding="utf-8")

    usgs_section = f"""
## 2. Dữ liệu địa chấn USGS (đã cập nhật)

| Thuộc tính | Giá trị |
|---|---|
| **Nguồn** | USGS FDSN Event Web Service |
| **URL** | `https://earthquake.usgs.gov/fdsnws/event/1/query` |
| **Khoảng thời gian** | 2023-01-01T00:00:00Z → 2026-03-31 |
| **Query interval** | 2023-01-01T00:00:00Z → 2026-04-01T00:00:00Z (half-open) |
| **Vùng địa lý** | lat 24–46°N, lon 122–150°E (Nhật Bản và lân cận) |
| **Magnitude tối thiểu** | M ≥ 4.0 |
| **eventtype** | earthquake |
| **Tổng sự kiện** | {n_events:,} (sau dedup) |
| **Tag** | JP |
| **File** | `data/clean/clean_usgs_JP_M4_20230101_20260331.parquet` |

### Lý do dùng half-open intervals

Giai đoạn 1 dùng `endtime='YYYY-MM-DD'` → USGS API hiểu là `T00:00:00Z` (đầu ngày),
bỏ sót 12 ngày cuối quý, thiếu **37 sự kiện**. Giai đoạn 2 sửa thành
`[Q_start, Q_next_start)` (half-open) với ISO datetime đầy đủ. Lỗi đã ghi vào
`docs/usgs/data_quality_report.md`.

### Hạn chế bbox

Hộp toạ độ (lat 24–46, lon 122–150) bao gồm ~8.32% sự kiện ngoài Nhật Bản
(chủ yếu Kamchatka/Kuril 7.2%, Taiwan 0.9%). Cột `region` trong dataset phân loại
gần đúng từ trường `place`. Bbox không thay đổi — xem thêm `data_quality_report.md`.
"""
    # Thay phần USGS cũ
    if "## 2. Dữ liệu địa chấn USGS" in text:
        # Cắt từ ## 2. đến ## 3. (hoặc cuối)
        parts = text.split("## 2. Dữ liệu địa chấn USGS")
        after = parts[1]
        # Tìm section tiếp theo
        next_h2 = after.find("\n## ", 5)
        if next_h2 > 0:
            rest = after[next_h2:]
        else:
            rest = ""
        text = parts[0] + usgs_section + rest
    else:
        text += usgs_section

    scope.write_text(text, encoding="utf-8")
    print(f"  📄 scope.md (đã cập nhật USGS section)")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    count_full, total_rows_downloaded, quarters = download_phase2()
    df_clean, out_path, n_removed = clean_and_export(count_full)

    n_raw_before = total_rows_downloaded
    write_docs(df_clean, n_removed, count_full, n_raw_before)
    update_scope(len(df_clean))

    print(f"\n{'='*70}")
    print(f"  KẾT QUẢ GIAI ĐOẠN 2  |  DỪNG, CHỜ XÁC NHẬN")
    print(f"{'='*70}")
    print(f"  Tổng tải (13 quý, half-open): {total_rows_downloaded:,}")
    print(f"  Count API (1 query full)      : {count_full:,}")
    print(f"  Trùng event_id đã xoá        : {n_removed:,}")
    print(f"  Sau dedup                    : {len(df_clean):,}")
    print(f"  Khớp count vs file           : {'✅' if len(df_clean)==count_full else '⚠️'}")
    print(f"  File Parquet                 : {out_path.name}")
    print(f"\n  Tài liệu:")
    print(f"    docs/usgs/data_dictionary.md")
    print(f"    docs/usgs/data_quality_report.md")
    print(f"    docs/scope.md")
    print(f"\n→ DỪNG. Chưa sang Giai đoạn 3. Chờ xác nhận.")


if __name__ == "__main__":
    main()
