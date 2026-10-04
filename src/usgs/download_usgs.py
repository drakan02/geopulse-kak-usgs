"""
download_usgs.py – Tải dữ liệu động đất từ USGS FDSN Web Service.

Nguyên tắc:
  - Tải theo các khoảng thời gian (quý), tự động kiểm tra count trước khi query.
  - Tự động chia nhỏ khoảng nếu count >= 20,000 (tránh bị vượt giới hạn API).
  - Ghi nhật ký vào logs/usgs_download_log.csv.

Thực thi:
  python src/usgs/download_usgs.py
"""

import sys
import csv
import hashlib
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from io import StringIO

import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg

# ── Cấu hình ──────────────────────────────────────────────────────────────
OUT_DIR  = cfg.DATA_RAW / "usgs"
LOG_PATH = cfg.LOGS_DIR / "usgs_download_log.csv"
SESSION  = requests.Session()
SESSION.headers["User-Agent"] = "SOP-01-Pipeline/1.0 (research)"

LOG_FIELDS = [
    "period_start", "period_end", "url_full",
    "count_api", "actual_rows", "count_match",
    "file_path", "file_size_bytes", "sha256",
    "downloaded_at", "note",
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _base_params(start: str, end: str, fmt: str = "csv") -> dict:
    return {
        "format":       fmt,
        "starttime":    start,
        "endtime":      end,
        "minlatitude":  cfg.USGS_BBOX["minlatitude"],
        "maxlatitude":  cfg.USGS_BBOX["maxlatitude"],
        "minlongitude": cfg.USGS_BBOX["minlongitude"],
        "maxlongitude": cfg.USGS_BBOX["maxlongitude"],
        "minmagnitude": cfg.USGS_MIN_MAG,
        "eventtype":    cfg.USGS_EVENT_TYPE,
        "orderby":      "time-asc",
    }


def _count(start: str, end: str) -> int:
    """Gọi endpoint /count – endpoint riêng, khác với /query."""
    params = {
        "starttime":    start,
        "endtime":      end,
        "minlatitude":  cfg.USGS_BBOX["minlatitude"],
        "maxlatitude":  cfg.USGS_BBOX["maxlatitude"],
        "minlongitude": cfg.USGS_BBOX["minlongitude"],
        "maxlongitude": cfg.USGS_BBOX["maxlongitude"],
        "minmagnitude": cfg.USGS_MIN_MAG,
        "eventtype":    cfg.USGS_EVENT_TYPE,
    }
    r = SESSION.get(cfg.USGS_COUNT_URL, params=params, timeout=30)
    r.raise_for_status()
    return int(r.text.strip())


def _quarter_ranges(d_start: date, d_end: date):
    """Sinh list (start, end) theo quý từ d_start đến d_end."""
    ranges = []
    y, q = d_start.year, (d_start.month - 1) // 3 + 1
    while True:
        # Đầu quý
        qm_start = (q - 1) * 3 + 1
        qs = date(y, qm_start, 1)
        # Cuối quý
        qm_end = q * 3
        if qm_end == 12:
            qe = date(y, 12, 31)
        else:
            import calendar
            last_day = calendar.monthrange(y, qm_end)[1]
            qe = date(y, qm_end, last_day)
        # Clip vào [d_start, d_end]
        s = max(qs, d_start)
        e = min(qe, d_end)
        if s > d_end:
            break
        ranges.append((s, e))
        # Sang quý tiếp
        q += 1
        if q > 4:
            q = 1; y += 1
        if date(y, (q-1)*3+1, 1) > d_end:
            break
    return ranges


def _split_period(start: date, end: date, count: int):
    """
    Nếu count >= MAX_LIMIT, chia đôi khoảng thời gian đệ quy
    cho đến khi mỗi đoạn < MAX_LIMIT.
    Trả [(start, end), ...] đã chia nhỏ.
    """
    if count < cfg.USGS_MAX_LIMIT:
        return [(start, end)]
    mid = start + (end - start) / 2
    mid = mid.date() if hasattr(mid, 'date') else mid
    c1 = _count(start.isoformat(), mid.isoformat())
    c2 = _count((mid + __import__('datetime').timedelta(days=1)).isoformat(), end.isoformat())
    parts = []
    parts += _split_period(start, mid, c1)
    mid2 = mid + __import__('datetime').timedelta(days=1)
    parts += _split_period(mid2, end, c2)
    return parts


def _download_period(start: date, end: date) -> dict:
    """Tải một khoảng, lưu file, trả dict log."""
    s_str = start.strftime("%Y%m%d")
    e_str = end.strftime("%Y%m%d")
    fname = f"usgs_{cfg.USGS_TAG}_M{cfg.USGS_MIN_MAG:.0f}_{s_str}_{e_str}.csv"
    out_path = OUT_DIR / fname

    params = _base_params(start.isoformat(), end.isoformat(), fmt="csv")
    # Xây URL đầy đủ để log
    req = requests.Request("GET", cfg.USGS_API_BASE, params=params)
    prepared = SESSION.prepare_request(req)
    url_full = prepared.url

    r = SESSION.get(cfg.USGS_API_BASE, params=params, timeout=120)
    r.raise_for_status()
    content = r.content

    # Đếm dòng thực tế (trừ header)
    lines = [l for l in content.decode("utf-8", errors="replace").splitlines()
             if l.strip()]
    actual_rows = max(0, len(lines) - 1)  # -1 cho header

    out_path.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    size = out_path.stat().st_size

    return {
        "period_start":    start.isoformat(),
        "period_end":      end.isoformat(),
        "url_full":        url_full,
        "count_api":       None,  # sẽ điền sau
        "actual_rows":     actual_rows,
        "count_match":     None,
        "file_path":       str(out_path.relative_to(cfg.PROJECT_ROOT)),
        "file_size_bytes": size,
        "sha256":          sha,
        "downloaded_at":   datetime.now(tz=timezone.utc).isoformat(),
        "note":            "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print(f"  USGS Earthquake Catalog – Giai đoạn 1: Tải & Kiểm tra")
    print(f"  Vùng: lat {cfg.USGS_BBOX['minlatitude']}–{cfg.USGS_BBOX['maxlatitude']},"
          f" lon {cfg.USGS_BBOX['minlongitude']}–{cfg.USGS_BBOX['maxlongitude']}")
    print(f"  Khoảng: {cfg.DATE_START} → {cfg.DATE_END}")
    print(f"  Mag ≥ {cfg.USGS_MIN_MAG}, eventtype={cfg.USGS_EVENT_TYPE}")
    print("=" * 65)

    # ── Bước 1: Đếm tổng ──────────────────────────────────────────────────
    print(f"\n── Bước 1: Đếm tổng số sự kiện ──")
    total_count = _count(cfg.DATE_START.isoformat(), cfg.DATE_END.isoformat())
    print(f"  Tổng M≥{cfg.USGS_MIN_MAG}, {cfg.DATE_START}→{cfg.DATE_END}: {total_count:,}")

    # ── Bước 2: Count từng quý + chia nhỏ nếu vượt MAX_LIMIT ─────────────
    print(f"\n── Bước 2: Count từng quý (giới hạn {cfg.USGS_MAX_LIMIT:,}/query) ──")
    quarters = _quarter_ranges(cfg.DATE_START, cfg.DATE_END)
    all_periods = []  # list (start, end, count)

    print(f"{'Quý':<25} {'Count':>8}  Trạng thái")
    print("─" * 50)
    for qs, qe in quarters:
        c = _count(qs.isoformat(), qe.isoformat())
        if c >= cfg.USGS_MAX_LIMIT:
            print(f"  {qs} → {qe}  {c:>8,}  ⚠️ VƯỢT GIỚI HẠN – chia nhỏ...")
            sub = _split_period(qs, qe, c)
            for ss, se in sub:
                cs = _count(ss.isoformat(), se.isoformat())
                all_periods.append((ss, se, cs))
                print(f"    ↳ {ss} → {se}  {cs:>8,}  ✅")
        else:
            all_periods.append((qs, qe, c))
            st = "✅" if c < cfg.USGS_MAX_LIMIT else "⚠️"
            print(f"  {qs} → {qe}  {c:>8,}  {st}")

    total_from_quarters = sum(c for _, _, c in all_periods)
    print(f"\n  Tổng kiểm tra (sum quarters): {total_from_quarters:,}")
    print(f"  Tổng API count:               {total_count:,}")
    if total_from_quarters != total_count:
        print(f"  ⚠️ Chênh lệch: {abs(total_from_quarters - total_count):,} sự kiện")
        print(f"     (Có thể do overlap tại ranh giới quý; sẽ dedup sau khi gộp)")
    else:
        print(f"  ✅ Khớp hoàn toàn")

    # ── Bước 3: Tải từng khoảng ───────────────────────────────────────────
    print(f"\n── Bước 3: Tải {len(all_periods)} file ──")
    log_rows = []
    total_actual = 0

    for i, (start, end, cnt_api) in enumerate(all_periods, 1):
        s_str = start.strftime("%Y%m%d")
        e_str = end.strftime("%Y%m%d")
        fname = f"usgs_{cfg.USGS_TAG}_M{cfg.USGS_MIN_MAG:.0f}_{s_str}_{e_str}.csv"
        print(f"  [{i:>2}/{len(all_periods)}] {start} → {end} (count={cnt_api:,}) ...", end="", flush=True)

        out_path = OUT_DIR / fname
        if out_path.exists() and out_path.stat().st_size > 0:
            # Đọc số dòng từ file có sẵn
            with open(out_path, encoding="utf-8") as f:
                actual = sum(1 for l in f if l.strip()) - 1
            sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
            size = out_path.stat().st_size
            match = (actual == cnt_api)
            print(f" SKIP (đã có, {actual:,} dòng) {'✅' if match else '⚠️ KHÔNG KHỚP'}")
        else:
            try:
                params = _base_params(start.isoformat(), end.isoformat(), fmt="csv")
                req_obj = requests.Request("GET", cfg.USGS_API_BASE, params=params)
                url_full = SESSION.prepare_request(req_obj).url
                r = SESSION.get(cfg.USGS_API_BASE, params=params, timeout=120)
                r.raise_for_status()
                content = r.content
                lines = [l for l in content.decode("utf-8", errors="replace").splitlines()
                         if l.strip()]
                actual = max(0, len(lines) - 1)
                out_path.write_bytes(content)
                sha = hashlib.sha256(content).hexdigest()
                size = out_path.stat().st_size
                match = (actual == cnt_api)
                print(f" OK ({actual:,} dòng, {size:,} bytes) {'✅' if match else '⚠️ KHÔNG KHỚP'}")
                time.sleep(0.5)  # lịch sự với USGS API
            except Exception as e:
                print(f" ❌ LỖI: {e}")
                log_rows.append({
                    "period_start": start.isoformat(), "period_end": end.isoformat(),
                    "url_full": "", "count_api": cnt_api, "actual_rows": 0,
                    "count_match": False, "file_path": fname,
                    "file_size_bytes": 0, "sha256": "",
                    "downloaded_at": datetime.now(tz=timezone.utc).isoformat(),
                    "note": f"ERROR: {e}"
                })
                continue

        total_actual += actual
        log_rows.append({
            "period_start":    start.isoformat(),
            "period_end":      end.isoformat(),
            "url_full":        (url_full if 'url_full' in dir() else ""),
            "count_api":       cnt_api,
            "actual_rows":     actual,
            "count_match":     match,
            "file_path":       str(out_path.relative_to(cfg.PROJECT_ROOT)),
            "file_size_bytes": size,
            "sha256":          sha,
            "downloaded_at":   datetime.now(tz=timezone.utc).isoformat(),
            "note":            "" if match else f"COUNT MISMATCH: api={cnt_api} actual={actual}",
        })

    # ── Bước 4: Ghi log ───────────────────────────────────────────────────
    write_header = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(log_rows)

    print(f"\n── Kết quả tải ──")
    print(f"  File đã tải  : {len(log_rows)}")
    print(f"  Tổng dòng    : {total_actual:,}")
    print(f"  Count API    : {total_count:,}")
    print(f"  Log          : {LOG_PATH}")

    mismatches = [r for r in log_rows if not r["count_match"]]
    if mismatches:
        print(f"\n  ⚠️ {len(mismatches)} file KHÔNG KHỚP count/actual:")
        for m in mismatches:
            print(f"     {m['period_start']} → {m['period_end']}: {m['note']}")
    else:
        print(f"  ✅ Tất cả count API = số dòng thực tế")

    print(f"\n→ Tải xong. Chạy tiếp: python src/analyze_usgs.py")


if __name__ == "__main__":
    main()
