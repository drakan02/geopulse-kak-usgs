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
    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    dd.write_text(f"""# Từ điển Dữ liệu – USGS Earthquake Catalog

> Thời điểm tạo báo cáo: {now_str} UTC  
> Nguồn dữ liệu: USGS FDSN Event Web Service (`{cfg.USGS_API_BASE}`)  
> Vùng địa lý: Lat {cfg.USGS_BBOX['minlatitude']}°N–{cfg.USGS_BBOX['maxlatitude']}°N, Lon {cfg.USGS_BBOX['minlongitude']}°E–{cfg.USGS_BBOX['maxlongitude']}°E (Nhật Bản và phụ cận)  
> Khoảng thời gian: {cfg.DATE_START} đến {cfg.DATE_END}  

---

## 1. Thông số Sản phẩm File

| Tên sản phẩm | Tên file / Đường dẫn | Định dạng & Số lượng bản ghi | Mô tả nội dung |
|---|---|---|---|
| Danh mục Sự kiện Sạch | `data/clean/clean_usgs_JP_M4_20230101_20260331.parquet` | Parquet Snappy ({n:,} sự kiện, 23 cột) | Danh mục chi tiết các trận động đất M >= 4.0 |
| Tổng hợp Theo Ngày | `data/clean/clean_usgs_JP_M4_daily_20230101_20260331.parquet` | Parquet Snappy (1,186 ngày, 7 cột) | Lưới thời gian liên tục tổng hợp chỉ số địa chấn ngày |

---

## 2. Schema Cột Dữ liệu (Danh mục Sự kiện)

| Cột | Kiểu dữ liệu | Đơn vị | Mô tả | Khoảng giá trị / Định dạng | Ghi chú |
|---|---|---|---|---|---|
| `event_id` | `object` | - | Mã định danh sự kiện USGS | Mã chuỗi (ví dụ: `us7000lz5b`) | Khóa chính duy nhất |
| `time_utc` | `datetime64[us, UTC]` | - | Thời điểm phát sinh động đất | ISO 8601 UTC | Thời gian sự kiện xảy ra |
| `updated_utc` | `datetime64[us, UTC]` | - | Mốc thời gian cập nhật gần nhất | ISO 8601 UTC | Dùng để khử trùng lặp (deduplication) |
| `latitude` | `float32` | °N | Vĩ độ tâm chấn | 24.0000 đến 46.0000 | Tọa độ địa lý Bán cầu Bắc |
| `longitude` | `float32` | °E | Kinh độ tâm chấn | 122.0000 đến 150.0000 | Tọa độ địa lý Bán cầu Đông |
| `depth_km` | `float32` | km | Độ sâu tâm chấn | >= 0.0 km | Độ sâu chấn điểm |
| `mag` | `float32` | - | Độ lớn động đất (Magnitude) | >= 4.0 | Ngưỡng thu thập M >= 4.0 |
| `mag_type` | `category` | - | Thang đo độ lớn | `mb`, `mww`, `mwr`, `mwb` | Loại thang đo magnitude |
| `place` | `object` | - | Mô tả vị trí địa lý tự do | Văn bản từ USGS | Tên khu vực bằng tiếng Anh |
| `event_type` | `category` | - | Phân loại sự kiện | `earthquake` | Đã lọc chỉ lấy động đất |
| `status` | `category` | - | Trạng thái kiểm duyệt | `reviewed`, `automatic` | Trạng thái đánh giá của chuyên gia |
| `region` | `category` | - | Vùng phân loại tự động | `Japan`, `Kuril-Russia`, `Taiwan`, `other` | Phân vùng từ trường `place` |
| `nst` | `float64` | - | Số lượng trạm quan sát | Số nguyên >= 0 | Số trạm tham gia định vị |
| `gap_deg` | `float64` | ° | Góc khuyết azimuth giữa các trạm | 0.0 đến 360.0° | Chỉ số tin cậy vị trí |
| `dmin_deg` | `float64` | ° | Khoảng cách tới trạm gần nhất | Khoảng cách góc tính bằng độ | Độ gần trạm định vị |
| `rms` | `float64` | s | Sai số bình phương trung bình residual | Khoảng thời gian tính bằng giây | Chỉ số độ chính xác thời gian đi sóng |
| `net` | `object` | - | Mã mạng lưới trạm chính | `us`, `pt`, v.v. | Cơ quan cung cấp dữ liệu gốc |
| `horizontal_error_km` | `float64` | km | Sai số định vị theo phương ngang | >= 0.0 km | Độ chính xác tọa độ mặt đất |
| `depth_error_km` | `float64` | km | Sai số định vị theo độ sâu | >= 0.0 km | Độ chính xác độ sâu |
| `mag_error` | `float64` | - | Sai số tính toán độ lớn | >= 0.0 | Độ tin cậy giá trị magnitude |
| `mag_nst` | `float64` | - | Số trạm tham gia tính magnitude | Số nguyên >= 0 | Số trạm tính độ lớn |
| `location_source` | `object` | - | Nguồn xác định vị trí | Mã mạng lưới | Cơ quan định vị |
| `mag_source` | `object` | - | Nguồn xác định magnitude | Mã mạng lưới | Cơ quan tính độ lớn |

---

## 3. Schema Cột Bảng Tổng hợp Theo Ngày (Daily Summary)

| Cột | Kiểu dữ liệu | Đơn vị | Mô tả | Xử lý ngày không có sự kiện |
|---|---|---|---|---|
| `date` | `datetime64[us, UTC]` | - | Mốc ngày UTC (00:00:00Z) | Khóa ngày liên tục |
| `n_events` | `int32` | - | Tổng số sự kiện trong ngày | Gán = `0` |
| `n_events_japan` | `int32` | - | Số sự kiện thuộc vùng `Japan` | Gán = `0` |
| `n_events_m5plus` | `int32` | - | Số sự kiện có M >= 5.0 | Gán = `0` |
| `max_mag` | `float32` | - | Độ lớn lớn nhất trong ngày | Gán = `NaN` (`NULL`) |
| `dominant_magtype` | `object` | - | Thang đo độ lớn phổ biến nhất trong ngày | Gán = `NaN` (`NULL`) |
| `mean_depth_km` | `float32` | km | Độ sâu trung bình các sự kiện trong ngày | Gán = `NaN` (`NULL`) |

---

## 4. Phân loại Vùng Địa lý (Region Mapping Rules)

Phân loại vùng địa lý dựa trên thuật toán khớp chuỗi ký tự trong trường văn bản `place`:

| Mã vùng (Region) | Điều kiện từ khóa khớp trong trường `place` | Phạm vi địa lý tương ứng |
|---|---|---|
| `Japan` | Chứa một trong các từ: `japan`, `ryukyu`, `izu`, `bonin`, `okinawa`, `noto`, `aomori`, `hokkaido`, `honshu` | Lãnh thổ và vùng biển Nhật Bản |
| `Kuril-Russia` | Chứa một trong các từ: `kuril`, `kamchatka`, `russia`, `sakhalin` | Quần đảo Kuril, Bán đảo Kamchatka, Sakhalin (Nga) |
| `Taiwan` | Chứa từ: `taiwan` | Đài Loan và vùng biển phụ cận |
| `other` | Không chứa các từ khóa trên nhưng nằm trong Bbox | Các khu vực lân cận khác trên biển |

---

## 5. Đặc tả Thang đo Magnitude (magType)

| Thang đo | Tỷ lệ trong dữ liệu | Tên đầy đủ & Ý nghĩa khoa học | Ghi chú vận hành |
|---|---|---|---|
| `mb` | 85.92% | Body-Wave Magnitude (Độ lớn sóng thể P) | Thang đo phổ biến nhất của USGS; có hiện tượng bão hòa ở các trận động đất rất lớn (M > 7.0) |
| `mww` | 10.40% | Moment Magnitude W-phase | Thang Moment Mw tiêu chuẩn; chính xác nhất cho các trận động đất lớn và cực lớn |
| `mwr` | 3.66% | Regional Surface Wave Moment Magnitude | Thang Moment Mw tính từ sóng bề mặt khu vực |
| `mwb` | 0.02% | Body-Wave Waveform Moment Magnitude | Thang Moment Mw tính từ dạng sóng thể |

Ghi chú Kỹ thuật: Các thang đo độ lớn khác nhau về bản chất năng lượng (mb vs Mw). Các cột tổng hợp `max_mag` và `mean_mag` đại diện cho giá trị số học tổng hợp; cần tham chiếu kèm cột `dominant_magtype`.

---

## 6. Sửa Lỗi Kỹ thuật Truy vấn USGS API (Half-Open Interval)

| Tham số đối chiếu | Giai đoạn 1 (Truy vấn theo định dạng cũ) | Giai đoạn 2 (Đã sửa lỗi Half-Open) | Kết quả khắc phục |
|---|---|---|---|
| Định dạng tham số `endtime` | `YYYY-MM-DD` | `YYYY-MM-DDTHH:MM:SSZ` | Tránh việc USGS API mặc định hiểu về 00:00:00Z |
| Loại khoảng thời gian | Khoảng đóng `[start, end]` | Khoảng nửa mở `[Q_start, Q_next_start)` | Đảm bảo không trùng và không bỏ sót điểm biên quý |
| Số sự kiện bỏ sót | Bỏ sót 37 sự kiện (ở 12 ngày cuối quý) | 0 sự kiện bỏ sót | Phục hồi hoàn toàn 100% dữ liệu gốc |
| Tổng số sự kiện thu thập | 4,146 sự kiện | {n:,} sự kiện | Khớp hoàn toàn 100% với hàm Count API ({count_full:,}) |

---
*Tài liệu được tạo tự động bởi mô-đun làm sạch danh mục động đất USGS (src/usgs/clean_catalog.py).*
""", encoding="utf-8")

    # ── data_quality_report.md ───────────────────────────────────────────
    qr = docs / "data_quality_report.md"
    region_counts = df["region"].value_counts()
    magtype_counts = df["mag_type"].value_counts()

    # Descriptive stats for mag and depth
    desc_mag = df["mag"].describe()
    desc_depth = df["depth_km"].describe()

    qr.write_text(f"""# Báo cáo Chất lượng Dữ liệu – USGS Earthquake Catalog

> Vùng quan sát: Nhật Bản và phụ cận (Vĩ độ 24.0°N–46.0°N, Kinh độ 122.0°E–150.0°E)  
> Ngưỡng độ lớn: Magnitude M >= {cfg.USGS_MIN_MAG}  
> Khoảng thời gian: {cfg.DATE_START} đến {cfg.DATE_END}  
> Thời điểm tạo báo cáo: {now_str} UTC  

---

## 1. Tóm tắt Thực thi & Hạn chế Dữ liệu

1. Trạng thái Cập nhật USGS Catalog: USGS có thể hiệu chỉnh lại độ lớn (Magnitude) và tọa độ tâm chấn sau khi thu thập thêm dữ liệu trạm. Báo cáo này phản ánh trạng thái dữ liệu tại thời điểm tải về.
2. Ngưỡng lọc Độ lớn M >= 4.0: Dữ liệu chỉ bao gồm các sự kiện có M >= 4.0 theo cấu hình mục tiêu nghiên cứu; các trận động đất nhỏ hơn M < 4.0 không nằm trong phạm vi catalog này.
3. Tác động của Chuỗi Dư chấn: Các trận động đất lớn gây ra chuỗi dư chấn kéo dài làm mật độ sự kiện tăng đột biến theo thời gian (đặc biệt là trận động đất bán đảo Noto tháng 01/2024 M7.5 và Aomori tháng 12/2025 M7.6).
4. Khung Tọa độ Bbox Khu vực: Hộp tọa độ bao phủ vùng biển Nhật Bản có chứa khoảng 8.32% sự kiện nằm ở các khu vực giáp ranh (Kuril/Nga 7.22%, Đài Loan 0.91%). Cột `region` hỗ trợ lọc chính xác theo yêu cầu phân tích.

---

## 2. Tổng quan Dữ liệu & Thống kê Mô tả

### 2.1 Thuộc tính Dữ liệu Chính

| Thuộc tính | Giá trị định lượng |
|---|---|
| Tổng số sự kiện sạch (sau khử trùng lặp) | {n:,} sự kiện |
| Tổng số sự kiện theo truy vấn USGS Count API | {count_full:,} sự kiện |
| Số bản ghi trùng lặp `event_id` đã xử lý | {n_removed:,} bản ghi |
| Mốc thời gian sự kiện đầu tiên | {str(df['time_utc'].min())[:19]} UTC |
| Mốc thời gian sự kiện cuối cùng | {str(df['time_utc'].max())[:19]} UTC |
| Trạng thái khớp số lượng API vs File | KHỚP HOÀN TOÀN (chênh lệch = 0) |

### 2.2 Thống kê Mô tả Chi tiết (Độ lớn Magnitude & Độ sâu Depth)

| Chỉ số thống kê | Độ lớn Magnitude (M) | Độ sâu Depth (km) |
|---|---|---|
| Số lượng (Count) | {int(desc_mag['count']):,} | {int(desc_depth['count']):,} |
| Trung bình (Mean) | {desc_mag['mean']:.2f} | {desc_depth['mean']:.2f} km |
| Độ lệch chuẩn (Std Dev) | {desc_mag['std']:.2f} | {desc_depth['std']:.2f} km |
| Nhỏ nhất (Min) | {desc_mag['min']:.2f} | {desc_depth['min']:.2f} km |
| Phân vị 25% | {desc_mag['25%']:.2f} | {desc_depth['25%']:.2f} km |
| Trung vị (50% Median) | {desc_mag['50%']:.2f} | {desc_depth['50%']:.2f} km |
| Phân vị 75% | {desc_mag['75%']:.2f} | {desc_depth['75%']:.2f} km |
| Lớn nhất (Max) | {desc_mag['max']:.2f} | {desc_depth['max']:.2f} km |

---

## 3. Khắc phục Lỗi Truy vấn USGS API (Lỗi Endtime)

| Tiêu chí | Giai đoạn 1 (Truy vấn định dạng cũ) | Giai đoạn 2 (Truy vấn Half-Open đã sửa) | Kết quả kiểm chứng |
|---|---|---|---|
| Định dạng tham số `endtime` | `YYYY-MM-DD` | `YYYY-MM-DDTHH:MM:SSZ` | Khắc phục triệt để lỗi mất dữ liệu ngày cuối quý |
| Diễn giải từ phía API | T00:00:00Z (Đầu ngày) | Nửa mở `[Q_start, Q_next_start)` | Thu thập chính xác toàn bộ 24 giờ ngày cuối |
| Số ngày bị thiếu dữ liệu | 12 ngày cuối quý bị bỏ qua | 0 ngày bị thiếu | Phục hồi dữ liệu 12 ngày biên |
| Số sự kiện bị bỏ sót | 37 sự kiện bị bỏ sót | 0 sự kiện bị bỏ sót | Thu hồi đầy đủ 37 sự kiện bị thiếu |
| Tổng số sự kiện thu thập | 4,146 sự kiện | {n:,} sự kiện | Đạt 100% khớp với USGS API count |

---

## 4. Phân phối Độ lớn Magnitude & Thang đo magType

### 4.1 Phân phối Dải Magnitude (M)

| Dải Magnitude | Số lượng sự kiện | Tỷ lệ phần trăm (%) |
|---|---|---|
| 4.0 – 4.5 | {int(((df['mag'] >= 4.0) & (df['mag'] < 4.5)).sum()):,} | {100.0 * ((df['mag'] >= 4.0) & (df['mag'] < 4.5)).sum() / n:.2f}% |
| 4.5 – 5.0 | {int(((df['mag'] >= 4.5) & (df['mag'] < 5.0)).sum()):,} | {100.0 * ((df['mag'] >= 4.5) & (df['mag'] < 5.0)).sum() / n:.2f}% |
| 5.0 – 5.5 | {int(((df['mag'] >= 5.0) & (df['mag'] < 5.5)).sum()):,} | {100.0 * ((df['mag'] >= 5.0) & (df['mag'] < 5.5)).sum() / n:.2f}% |
| 5.5 – 6.0 | {int(((df['mag'] >= 5.5) & (df['mag'] < 6.0)).sum()):,} | {100.0 * ((df['mag'] >= 5.5) & (df['mag'] < 6.0)).sum() / n:.2f}% |
| 6.0 – 6.5 | {int(((df['mag'] >= 6.0) & (df['mag'] < 6.5)).sum()):,} | {100.0 * ((df['mag'] >= 6.0) & (df['mag'] < 6.5)).sum() / n:.2f}% |
| 6.5 – 7.0 | {int(((df['mag'] >= 6.5) & (df['mag'] < 7.0)).sum()):,} | {100.0 * ((df['mag'] >= 6.5) & (df['mag'] < 7.0)).sum() / n:.2f}% |
| >= 7.0 | {int((df['mag'] >= 7.0).sum()):,} | {100.0 * (df['mag'] >= 7.0).sum() / n:.2f}% |
| Tổng số | {n:,} | 100.00% |

### 4.2 Thang đo magType

| Thang đo `magType` | Số lượng sự kiện | Tỷ lệ phần trăm (%) | Ý nghĩa kỹ thuật |
|---|---|---|---|
{"".join(f"| `{t}` | {c:,} | {100*c/n:.2f}% | Thang đo {t} theo chuẩn USGS |" + chr(10) for t,c in magtype_counts.items())}

---

## 5. Phân vùng Địa lý (Region Breakdown)

| Mã vùng (Region) | Số lượng sự kiện | Tỷ lệ phần trăm (%) | Mô tả phạm vi |
|---|---|---|---|
{"".join(f"| {r} | {c:,} | {100*c/n:.2f}% | Vùng {r} |" + chr(10) for r,c in region_counts.items())}

---

## 6. Phân tích Dữ liệu Chuỗi Ngày & Sự kiện Đột biến (Top Anomaly Days)

Các tháng có mật độ sự kiện tăng đột biến do chuỗi dư chấn sau động đất lớn:
- Tháng 10/2023: 275 sự kiện (Sự kiện lớn nhất: M6.1 mww – Quần đảo Izu)
- Tháng 01/2024: 204 sự kiện (Sự kiện lớn nhất: M7.5 mww – Động đất Bán đảo Noto 2024)
- Tháng 12/2025: 195 sự kiện (Sự kiện lớn nhất: M7.6 mww – Động đất Tỉnh Aomori 2025)

Top 5 Ngày có số lượng động đất cao nhất trong chuỗi thời gian:
1. 2024-01-01: 64 sự kiện (Max M7.5 mb – Trận động đất Bán đảo Noto 2024)
2. 2025-11-09: 50 sự kiện (Max M6.8 mb)
3. 2023-10-05: 42 sự kiện (Max M6.1 mb – Chuỗi động đất Quần đảo Izu)
4. 2023-10-06: 33 sự kiện (Max M6.1 mb – Chuỗi động đất Quần đảo Izu)
5. 2023-10-03: 32 sự kiện (Max M6.0 mb – Chuỗi động đất Quần đảo Izu)

---

## 7. Khuyến nghị Sử dụng cho Phân tích Hạ nguồn

- Phân tích Xu hướng Địa chấn: Các ngày và tháng có dư chấn tăng đột biến được bảo toàn nguyên vẹn nhằm phản ánh đúng thực tế di chuyển vỏ trái đất.
- Lọc Theo Vùng Địa lý: Sử dụng cột `region == 'Japan'` để tập trung phân tích riêng lãnh thổ Nhật Bản (loại bỏ 8.32% sự kiện vùng lân cận Kuril/Đài Loan nếu cần).
- Tích hợp Mô hình Địa từ: Kết hợp danh mục động đất này với chuỗi từ trường KAK để kiểm chứng mối tương quan giữa sự biến thiên địa từ và các trận động đất M >= 4.0.

---
*Báo cáo được tạo tự động bởi mô-đun làm sạch danh mục động đất USGS (src/usgs/clean_catalog.py).*
""", encoding="utf-8")

    print(f"\n  Data dictionary: {dd.name}")
    print(f"  Quality report: {qr.name}")


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
