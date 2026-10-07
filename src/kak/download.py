"""
download.py – Tải dữ liệu địa từ thô INTERMAGNET (trạm KAK) từ BGS HAPI API.

Nguyên tắc:
  - Lưu NGUYÊN VẸN file CSV thô vào data/raw/intermagnet/, KHÔNG sửa nội dung.
  - Ghi log tải vào logs/download_log.csv (URL, SHA-256, size, timestamp).
  - Bỏ qua file đã tồn tại (dùng --force để tải lại).

Thực thi:
  python src/kak/download.py [--force]
"""

import argparse
import calendar
import csv
import hashlib
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

# Thêm thư mục src vào path để import config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg

# ── Helpers ────────────────────────────────────────────────────────────────

def sha256(path: Path) -> str:
    """Tính SHA-256 của file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def log_download(row: dict) -> None:
    """Ghi một dòng vào logs/download_log.csv."""
    cfg.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = cfg.LOGS_DIR / "download_log.csv"
    fieldnames = ["source", "station", "url", "local_file",
                  "file_size_bytes", "sha256", "downloaded_at", "note"]
    write_header = not log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        w.writerow(row)


def safe_get(url: str, params: dict, timeout: int = 60) -> requests.Response:
    """HTTP GET với retry đơn giản (3 lần)."""
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            print(f"  ⚠  Lần {attempt}/3 thất bại: {e}")
            if attempt < 3:
                time.sleep(5 * attempt)
    raise RuntimeError(f"Không thể tải: {url} params={params}")


# ── INTERMAGNET ────────────────────────────────────────────────────────────

def _month_ranges(start: date, end: date):
    """Sinh các khoảng tháng (start_month, end_month) trong [start, end]."""
    cur = start.replace(day=1)
    while cur <= end:
        m_start = cur
        # Ngày cuối tháng
        if cur.month == 12:
            m_end = date(cur.year, 12, 31)
        else:
            m_end = (cur.replace(month=cur.month + 1, day=1) - timedelta(days=1))
        m_end = min(m_end, end)
        yield m_start, m_end
        # Sang tháng tiếp
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = cur.replace(month=cur.month + 1)


def download_intermagnet(station: str, force: bool = False) -> list[Path]:
    """
    Tải dữ liệu INTERMAGNET 1 phút (Definitive) từ BGS HAPI API.
    Tải từng tháng → lưu file CSV trong data/raw/intermagnet/.

    Endpoint: https://imag-data.bgs.ac.uk/GIN_V1/hapi/data
    Dataset: {station_lower}/definitive/PT1M/xyzf

    ĐÃ XÁC NHẬN:
      - PHU definitive: 1996-01-01 → 2019-12-31
      - DLT definitive: 2012-01-01 → 2018-12-31
      - Khoảng 2014–2018 đủ Definitive cho cả 2 trạm (kiểm tra 2026-10-05)
    """
    out_dir = cfg.DATA_RAW / "intermagnet"
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []

    dataset = cfg.INTERMAGNET_HAPI_DATASET.format(station_lower=station.lower())

    for m_start, m_end in _month_ranges(cfg.DATE_START, cfg.DATE_END):
        # HAPI stop là exclusive – cần stop = ngày đầu tiên của tháng tiếp
        if m_end.month == 12:
            next_day = date(m_end.year + 1, 1, 1)
        else:
            next_day = date(m_end.year, m_end.month + 1, 1)

        # Tên file: slug từ loại dữ liệu ("quasi-def" hoặc "definitive")
        dtype_slug = "quasi-def" if "quasi" in cfg.DATA_TYPE else "definitive"
        fname = (
            f"intermagnet_{station}_{dtype_slug}_1min_"
            f"{m_start.strftime('%Y%m%d')}_{m_end.strftime('%Y%m%d')}.csv"
        )
        out_path = out_dir / fname

        if out_path.exists() and not force:
            print(f"  ⏭  Đã có: {fname}")
            downloaded.append(out_path)
            continue

        params = {
            "dataset": dataset,
            "start":   f"{m_start.isoformat()}T00:00:00Z",
            "stop":    f"{next_day.isoformat()}T00:00:00Z",
            "format":  "csv",
        }
        url = f"{cfg.INTERMAGNET_HAPI_BASE}/data"

        print(f"  ⬇  Tải {fname} ...", end=" ", flush=True)
        try:
            resp = safe_get(url, params)
        except RuntimeError as e:
            print(f"\n  ❌ Lỗi: {e}")
            log_download({
                "source": "INTERMAGNET_HAPI", "station": station,
                "url": url, "local_file": "", "file_size_bytes": 0, "sha256": "",
                "downloaded_at": datetime.now(tz=timezone.utc).isoformat(),
                "note": str(e),
            })
            continue

        content = resp.content

        # Kiểm tra lỗi HAPI (JSON error)
        if content.strip().startswith(b"{"):
            try:
                err = json.loads(content)
                code = err.get("status", {}).get("code", 0)
                msg  = err.get("status", {}).get("message", "")
                print(f"⚠  HAPI error {code}: {msg}")
                log_download({
                    "source": "INTERMAGNET_HAPI", "station": station,
                    "url": resp.url, "local_file": "", "file_size_bytes": 0,
                    "sha256": "", "downloaded_at": datetime.now(tz=timezone.utc).isoformat(),
                    "note": f"HAPI {code}: {msg}",
                })
                continue
            except Exception:
                pass

        out_path.write_bytes(content)
        ck   = sha256(out_path)
        size = out_path.stat().st_size
        print(f"OK ({size:,} bytes, sha256={ck[:12]}…)")

        log_download({
            "source": "INTERMAGNET_HAPI", "station": station,
            "url": resp.url, "local_file": str(out_path.relative_to(cfg.PROJECT_ROOT)),
            "file_size_bytes": size, "sha256": ck,
            "downloaded_at": datetime.now(tz=timezone.utc).isoformat(),
            "note": f"Definitive, 1min, dataset={dataset}",
        })
        downloaded.append(out_path)
        time.sleep(1)  # Lịch sự với server

    return downloaded


# ── USGS ───────────────────────────────────────────────────────────────────

def download_usgs_csv(force: bool = False) -> Path | None:
    """
    Tải earthquake catalog từ USGS FDSN Web Service → CSV.
    Chia thành các batch 1 năm (giới hạn API ~20,000 sự kiện/query).
    File lưu: data/raw/usgs/usgs_earthquake_YYYYMMDD_YYYYMMDD.csv
    """
    out_dir = cfg.DATA_RAW / "usgs"
    out_dir.mkdir(parents=True, exist_ok=True)
    all_records = []

    start_y = cfg.DATE_START.year
    end_y   = cfg.DATE_END.year

    for year in range(start_y, end_y + 1):
        y_start = max(cfg.DATE_START, date(year, 1, 1))
        y_end   = min(cfg.DATE_END,   date(year, 12, 31))

        fname = f"usgs_earthquake_{y_start.strftime('%Y%m%d')}_{y_end.strftime('%Y%m%d')}.csv"
        out_path = out_dir / fname

        if out_path.exists() and not force:
            print(f"  ⏭  Đã có: {fname}")
            continue

        params = {
            "format": "csv",
            "starttime": y_start.isoformat(),
            "endtime":   y_end.isoformat(),
            "minmagnitude": cfg.USGS_MIN_MAG,
            **cfg.USGS_BBOX,
            "orderby": "time",
        }
        url = cfg.USGS_API_BASE

        print(f"  ⬇  Tải USGS CSV {year} ...", end=" ", flush=True)
        try:
            resp = safe_get(url, params, timeout=120)
        except RuntimeError as e:
            print(f"\n  ❌ {e}")
            log_download({
                "source": "USGS", "station": "N/A", "url": url,
                "local_file": "", "file_size_bytes": 0, "sha256": "",
                "downloaded_at": datetime.now(tz=timezone.utc).isoformat(), "note": str(e),
            })
            continue

        out_path.write_bytes(resp.content)
        ck  = sha256(out_path)
        size = out_path.stat().st_size
        print(f"OK ({size:,} bytes, sha256={ck[:12]}…)")

        log_download({
            "source": "USGS", "station": "N/A",
            "url": resp.url,
            "local_file": str(out_path.relative_to(cfg.PROJECT_ROOT)),
            "file_size_bytes": size, "sha256": ck,
            "downloaded_at": datetime.now(tz=timezone.utc).isoformat(),
            "note": f"mag≥{cfg.USGS_MIN_MAG}, bbox={cfg.USGS_BBOX}",
        })
        time.sleep(2)

    return out_dir


def download_usgs_geojson(force: bool = False) -> Path | None:
    """
    Tải earthquake catalog từ USGS FDSN Web Service → GeoJSON.
    Lưu: data/raw/usgs/usgs_earthquake_YYYYMMDD_YYYYMMDD.geojson
    """
    out_dir = cfg.DATA_RAW / "usgs"
    out_dir.mkdir(parents=True, exist_ok=True)

    start_y = cfg.DATE_START.year
    end_y   = cfg.DATE_END.year

    for year in range(start_y, end_y + 1):
        y_start = max(cfg.DATE_START, date(year, 1, 1))
        y_end   = min(cfg.DATE_END,   date(year, 12, 31))

        fname = f"usgs_earthquake_{y_start.strftime('%Y%m%d')}_{y_end.strftime('%Y%m%d')}.geojson"
        out_path = out_dir / fname

        if out_path.exists() and not force:
            print(f"  ⏭  Đã có: {fname}")
            continue

        params = {
            "format": "geojson",
            "starttime": y_start.isoformat(),
            "endtime":   y_end.isoformat(),
            "minmagnitude": cfg.USGS_MIN_MAG,
            **cfg.USGS_BBOX,
            "orderby": "time",
        }

        print(f"  ⬇  Tải USGS GeoJSON {year} ...", end=" ", flush=True)
        try:
            resp = safe_get(cfg.USGS_API_BASE, params, timeout=120)
        except RuntimeError as e:
            print(f"\n  ❌ {e}")
            continue

        out_path.write_bytes(resp.content)
        ck   = sha256(out_path)
        size = out_path.stat().st_size
        print(f"OK ({size:,} bytes, sha256={ck[:12]}…)")

        log_download({
            "source": "USGS_GeoJSON", "station": "N/A",
            "url": resp.url,
            "local_file": str(out_path.relative_to(cfg.PROJECT_ROOT)),
            "file_size_bytes": size, "sha256": ck,
            "downloaded_at": datetime.now(tz=timezone.utc).isoformat(),
            "note": f"GeoJSON, mag≥{cfg.USGS_MIN_MAG}",
        })
        time.sleep(2)

    return out_dir


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Tải dữ liệu thô SOP-01")
    parser.add_argument(
        "--source", choices=["intermagnet", "usgs", "all"], default="all",
        help="Nguồn dữ liệu cần tải (mặc định: all)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Tải lại dù file đã tồn tại"
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  SOP-01 – Download Data")
    print(f"  Khoảng thời gian: {cfg.DATE_START} → {cfg.DATE_END}")
    print(f"  Nguồn: {args.source.upper()}")
    print(f"{'='*60}\n")

    if args.source in ("intermagnet", "all"):
        for station in cfg.STATIONS:
            print(f"\n── INTERMAGNET / {station} ──")
            files = download_intermagnet(station, force=args.force)
            print(f"  → {len(files)} file đã xử lý cho {station}")

    if args.source in ("usgs", "all"):
        print(f"\n── USGS Earthquake CSV ──")
        download_usgs_csv(force=args.force)

        print(f"\n── USGS Earthquake GeoJSON ──")
        download_usgs_geojson(force=args.force)

    print(f"\n✅ Hoàn tất. Log: {cfg.LOGS_DIR / 'download_log.csv'}")
    print(f"   Dữ liệu thô: {cfg.DATA_RAW}\n")


if __name__ == "__main__":
    main()
