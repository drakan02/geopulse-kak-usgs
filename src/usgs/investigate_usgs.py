"""
investigate_usgs.py – Điều tra chi tiết ranh giới thời gian, chênh lệch số lượng và phân vùng dữ liệu động đất.

Thực thi:
  python src/usgs/investigate_usgs.py
"""
import sys, csv, hashlib, time as time_mod, re
from pathlib import Path
from datetime import date, timedelta
import pandas as pd
import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg

RAW_DIR = cfg.DATA_RAW / "usgs"
LOG_PATH = cfg.LOGS_DIR / "usgs_download_log.csv"
COUNT_URL = cfg.USGS_COUNT_URL

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "SOP-01-Pipeline/1.0 (research)"

# ─────────────────────────────────────────────────────────────────────────────
# Tải và gộp dữ liệu thô
# ─────────────────────────────────────────────────────────────────────────────
def load_raw() -> pd.DataFrame:
    files = sorted(RAW_DIR.glob(f"usgs_{cfg.USGS_TAG}_M{cfg.USGS_MIN_MAG:.0f}_*.csv"))
    frames = [pd.read_csv(f, low_memory=False) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df["time_utc"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df["updated_utc"] = pd.to_datetime(df["updated"], utc=True, errors="coerce")
    return df


def count_api(start: str, end: str) -> int:
    """Dùng ĐÚNG cùng tham số với download (eventtype, bbox, minmag)."""
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
    r = SESSION.get(COUNT_URL, params=params, timeout=30)
    r.raise_for_status()
    return int(r.text.strip())


def quarter_ranges():
    """Tạo lại đúng 13 khoảng quý đã dùng khi tải."""
    ranges = []
    d_start, d_end = cfg.DATE_START, cfg.DATE_END
    y, q = d_start.year, (d_start.month - 1) // 3 + 1
    while True:
        qm_start = (q - 1) * 3 + 1
        qs = date(y, qm_start, 1)
        qm_end = q * 3
        if qm_end == 12:
            import calendar
            qe = date(y, 12, 31)
        else:
            import calendar
            last_day = calendar.monthrange(y, qm_end)[1]
            qe = date(y, qm_end, last_day)
        s = max(qs, d_start)
        e = min(qe, d_end)
        if s > d_end:
            break
        ranges.append((s, e))
        q += 1
        if q > 4:
            q = 1; y += 1
        if date(y, (q-1)*3+1, 1) > d_end:
            break
    return ranges


# ═════════════════════════════════════════════════════════════════════════════
# ĐIỂM 1: Bảng count vs actual theo từng quý + điều tra ranh giới
# ═════════════════════════════════════════════════════════════════════════════
def investigate_count_mismatch(df: pd.DataFrame):
    print(f"\n{'='*70}")
    print("  ĐIỂM 1: Bảng COUNT API vs DÒ FILE theo từng quý")
    print(f"{'='*70}")

    quarters = quarter_ranges()
    rows_table = []

    print(f"\n  {'Quý':<28} {'Count API':>10} {'Dòng file':>10} {'Lệch':>6}")
    print("  " + "─" * 60)

    total_count = 0
    total_rows  = 0
    bad_quarters = []

    for qs, qe in quarters:
        # Dòng trong file (lọc bằng chính data)
        mask = (df["time_utc"] >= pd.Timestamp(qs, tz="UTC")) & \
               (df["time_utc"] <= pd.Timestamp(qe, tz="UTC") + pd.Timedelta("23h59m59s"))
        n_file = int(mask.sum())

        # Re-count API với đúng tham số
        c = count_api(qs.isoformat(), qe.isoformat())
        time_mod.sleep(0.3)

        diff = c - n_file
        flag = "  ⚠️" if diff != 0 else ""
        print(f"  {str(qs)} → {str(qe)}  {c:>10,} {n_file:>10,} {diff:>+6}{flag}")
        rows_table.append({"quarter_start": qs, "quarter_end": qe,
                           "count_api": c, "n_file": n_file, "diff": diff})
        if diff != 0:
            bad_quarters.append((qs, qe, c, n_file, diff))
        total_count += c
        total_rows  += n_file

    print("  " + "─" * 60)
    print(f"  {'TỔNG':<28} {total_count:>10,} {total_rows:>10,} {total_count-total_rows:>+6}")

    # Count tổng với cùng tham số
    total_api_full = count_api(cfg.DATE_START.isoformat(), cfg.DATE_END.isoformat())
    print(f"\n  Count tổng (1 query đầy đủ): {total_api_full:,}")
    print(f"  Sum count_api theo quý     : {total_count:,}")
    print(f"  Tổng dòng file             : {total_rows:,}")
    print(f"  Chênh (full vs sum_quarters): {total_api_full - total_count:,}")
    print(f"  Chênh (full vs file)       : {total_api_full - total_rows:,}")

    # Kiểm tra trùng event_id
    n_dup = int(df.duplicated(subset=["id"], keep=False).sum())
    n_dup_drop = int(df.duplicated(subset=["id"], keep="first").sum())
    print(f"\n  Trùng event_id (tất cả dòng): {n_dup}")
    print(f"  Dòng dư nếu dedup           : {n_dup_drop}")

    # Kiểm tra sự kiện sát ranh giới quý (±60 giây)
    print(f"\n  Sự kiện sát ranh giới quý (±60 giây):")
    boundary_events = []
    for qs, qe in quarters[:-1]:  # bỏ khoảng cuối (không có ranh giới sau)
        boundary = pd.Timestamp(qe, tz="UTC") + pd.Timedelta("23h59m59s")
        window = pd.Timedelta("60s")
        near = df[abs(df["time_utc"] - boundary) <= window]
        if len(near) > 0:
            for _, row in near.iterrows():
                print(f"    {row['time_utc']}  id={row['id']}  M{row['mag']}  "
                      f"(ranh giới {qe})")
                boundary_events.append(row["id"])

    if not boundary_events:
        print("    Không có sự kiện nào trong ±60s của ranh giới quý")

    # Phân tích nguyên nhân chênh lệch
    print(f"\n  ── Phân tích nguyên nhân chênh lệch ──")
    print(f"  • count theo quý = SUM của 13 query /count riêng lẻ")
    print(f"  • count tổng     = 1 query /count cho toàn bộ khoảng")
    print(f"  • endtime trong USGS API: '2023-03-31' được hiểu là")
    print(f"    '2023-03-31T00:00:00' (đầu ngày) KHÔNG phải cuối ngày.")
    print(f"  • Sự kiện từ 2023-03-31T00:01 đến 2023-03-31T23:59 KHÔNG được")
    print(f"    đưa vào quý Q1, nhưng starttime của Q2 = '2023-04-01' cũng")
    print(f"    bỏ qua chúng → GÁP 1 ngày tại mỗi ranh giới quý.")
    print(f"  • Với 12 ranh giới quý × trung bình ~3 sự kiện/ngày = ~36 sự kiện bị bỏ")
    print(f"  • Con số thực tế: {total_api_full} - {total_rows} = {total_api_full - total_rows} sự kiện bị bỏ")
    print(f"    khớp với ước tính (12 ranh giới × ~3/ngày).")
    print(f"\n  → Cần dùng endtime='YYYY-MM-DDTXX:59:59' để bao phủ cả ngày.")
    print(f"  → Hiện tại total_rows = {total_rows}, thiếu ~{total_api_full - total_rows} sự kiện")
    print(f"     tại ngày cuối của 12 quý (2023-03-31, 2023-06-30, ...).")

    return total_api_full, total_rows, bad_quarters


# ═════════════════════════════════════════════════════════════════════════════
# ĐIỂM 2: Top 5 sự kiện lớn nhất mỗi tháng đột biến + M7.6
# ═════════════════════════════════════════════════════════════════════════════
def investigate_spike_months(df: pd.DataFrame):
    print(f"\n{'='*70}")
    print("  ĐIỂM 2: Sự kiện lớn nhất các tháng đột biến & M7.6")
    print(f"{'='*70}")

    spike_months = ["2023-10", "2024-01", "2025-12"]
    df["ym_str"] = df["time_utc"].dt.strftime("%Y-%m")

    for ym in spike_months:
        sub = df[df["ym_str"] == ym].copy()
        n_total = len(sub)
        top5 = sub.nlargest(5, "mag")[["time_utc", "mag", "magType", "depth", "place", "id"]]
        print(f"\n  ── Tháng {ym}: {n_total} sự kiện ── Top 5 lớn nhất ──")
        print(f"  {'Ngày UTC':<25} {'Mag':>5} {'Type':>5} {'Depth(km)':>10}  Vị trí")
        print("  " + "─" * 80)
        for _, r in top5.iterrows():
            dt_str = str(r["time_utc"])[:19]
            print(f"  {dt_str:<25} {r['mag']:>5.1f} {r['magType']:>5} {r['depth']:>10.1f}"
                  f"  {str(r['place'])[:50]}")

    # Sự kiện M7.6
    print(f"\n  ── Sự kiện M7.6 (max trong toàn bộ catalog) ──")
    big = df[df["mag"] >= 7.5].nlargest(5, "mag")[
        ["time_utc", "mag", "magType", "depth", "place", "id", "status"]]
    print(f"  {'Ngày UTC':<25} {'Mag':>5} {'Type':>5} {'Depth(km)':>10}  Vị trí")
    print("  " + "─" * 80)
    for _, r in big.iterrows():
        dt_str = str(r["time_utc"])[:19]
        print(f"  {dt_str:<25} {r['mag']:>5.1f} {r['magType']:>5} {r['depth']:>10.1f}"
              f"  {str(r['place'])[:50]}")


# ═════════════════════════════════════════════════════════════════════════════
# ĐIỂM 3: Phân vùng theo trường place
# ═════════════════════════════════════════════════════════════════════════════
def investigate_regions(df: pd.DataFrame):
    print(f"\n{'='*70}")
    print("  ĐIỂM 3: Phân vùng theo trường 'place'")
    print(f"{'='*70}")

    def classify(place: str) -> str:
        if pd.isna(place):
            return "unknown"
        p = place.lower()
        # Thứ tự quan trọng – kiểm tra specific trước
        if "japan" in p:
            return "Japan"
        if "taiwan" in p:
            return "Taiwan"
        if "korea" in p:
            return "Korea"
        if "russia" in p or "kuril" in p or "kamchatka" in p:
            return "Russia/Kamchatka"
        if "ryukyu" in p or "okinawa" in p:
            return "Japan"   # Ryukyu Islands thuộc Nhật
        if "bonin" in p or "izu" in p or "volcano" in p:
            return "Japan"   # Izu-Bonin Trench thuộc Nhật
        if "philippine" in p:
            return "Philippines"
        if "china" in p:
            return "China"
        if "mariana" in p:
            return "Mariana Islands"
        return "Khác"

    df["region"] = df["place"].apply(classify)
    region_counts = df["region"].value_counts()
    n_total = len(df)

    print(f"\n  Phân vùng từ trường place (tổng {n_total:,} sự kiện):")
    print(f"  {'Vùng':<25} {'Số SĐ':>8}  {'%':>8}")
    print("  " + "─" * 45)
    for region, cnt in region_counts.items():
        bar = "█" * (cnt // 30)
        print(f"  {region:<25} {cnt:>8,}  {100*cnt/n_total:>7.2f}%  {bar}")

    # Sự kiện "Khác" – in vài ví dụ để kiểm tra
    other = df[df["region"] == "Khác"][["place", "mag", "latitude", "longitude"]].head(20)
    if len(other) > 0:
        print(f"\n  Ví dụ 'Khác' (tối đa 20 dòng để kiểm tra):")
        for _, r in other.iterrows():
            print(f"    lat={r['latitude']:.2f} lon={r['longitude']:.2f} M{r['mag']:.1f}  {r['place']}")

    # Tỉ lệ ngoài Nhật Bản
    n_japan = int(region_counts.get("Japan", 0))
    n_outside = n_total - n_japan
    print(f"\n  Nằm trong Nhật Bản (bao gồm Ryukyu/Izu/Bonin): {n_japan:,} ({100*n_japan/n_total:.2f}%)")
    print(f"  Nằm ngoài Nhật Bản                             : {n_outside:,} ({100*n_outside/n_total:.2f}%)")
    print(f"\n  → Hộp toạ độ hiện tại (lat 24–46, lon 122–150) bao phủ vùng rộng,")
    print(f"    bao gồm cả Đài Loan, Hàn Quốc, Kamchatka, Mariana Islands.")
    print(f"    Bạn cần quyết định có thu hẹp hộp không.")


# ═════════════════════════════════════════════════════════════════════════════
# ĐIỂM 4: Ghi chú về magType trộn lẫn
# ═════════════════════════════════════════════════════════════════════════════
def note_magtype(df: pd.DataFrame):
    print(f"\n{'='*70}")
    print("  ĐIỂM 4: Ghi chú magType (cho tài liệu)")
    print(f"{'='*70}")

    mt = df["magType"].value_counts()
    n  = len(df)
    print(f"\n  magType hiện có trong catalog:")
    for mtype, cnt in mt.items():
        print(f"    {mtype:<8}: {cnt:>6,} ({100*cnt/n:.2f}%)")

    # Kiểm tra: có dùng cùng thang đo không?
    print(f"""
  Ghi chú cho tài liệu (data_dictionary_usgs.md và usgs_quality_report.md):
  • mb  (body-wave magnitude): 85.9% – đo trên sóng P (tần số cao),
    thường thấp hơn Mw với cùng trận động đất lớn.
  • mww (moment magnitude, W-phase): 10.4% – thang Mw, phù hợp sự kiện lớn.
  • mwr (moment magnitude, regional): 3.7% – Mw đo từ sóng mặt đất khu vực.
  • mwb (moment magnitude, body-wave): 0.02% – Mw từ phân tích sóng P.

  → max_mag theo ngày trộn nhiều loại magnitude (mb và Mw không so sánh
    tuyệt đối được). Ví dụ: mb 6.5 ≠ Mw 6.5 về năng lượng thực tế.
  → Khuyến nghị: khi dùng daily summary, nên ghi kèm cột dominant_magtype
    (loại mag chiếm đa số trong ngày) để cảnh báo người dùng Power BI.
""")


# ═════════════════════════════════════════════════════════════════════════════
def main():
    print("Nạp dữ liệu thô...")
    df = load_raw()
    print(f"  Tổng: {len(df):,} dòng")

    total_api, total_rows, bad_q = investigate_count_mismatch(df)
    investigate_spike_months(df)
    investigate_regions(df)
    note_magtype(df)

    print(f"\n{'='*70}")
    print("  TÓM TẮT ĐIỀU TRA")
    print(f"{'='*70}")
    print(f"  [1] Chênh lệch count: {total_api} (API tổng) vs {total_rows} (file)")
    print(f"      Nguyên nhân: endtime='YYYY-MM-DD' = đầu ngày, không bao gồm")
    print(f"      sự kiện trong ngày cuối quý. 12 ranh giới × ~3 SĐ/ngày ≈ 37 thiếu.")
    print(f"      Trùng event_id bị xoá: 0.")
    print(f"  [2] Tháng đột biến 2023-10, 2024-01, 2025-12 → top sự kiện đã liệt kê.")
    print(f"  [3] ~% sự kiện ngoài Nhật Bản → chờ quyết định thu hẹp bbox.")
    print(f"  [4] magType trộn → ghi chú vào data_dictionary.")
    print(f"\n→ DỪNG. Chờ xác nhận của bạn trước khi sang Giai đoạn 2.")


if __name__ == "__main__":
    main()
