"""
daily_summary.py – Tổng hợp Daily Earthquake Summary trên lưới ngày đầy đủ (2023-01-01 → 2026-03-31).

Nguyên tắc:
  - Lưới 1,186 ngày UTC liên tục.
  - Ngày 0 sự kiện: count = 0, max_mag / dominant_magtype / mean_depth_km = NULL.
  - Kiểm chứng bằng assertions nghiêm ngặt trước khi xuất Parquet.

Thực thi:
  python src/usgs/daily_summary.py
"""

import sys
from pathlib import Path
from datetime import timezone, datetime

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg

CLEAN_DIR = cfg.DATA_CLEAN
DOCS_DIR  = cfg.DOCS_DIR / "usgs"

CLEAN_IN  = CLEAN_DIR / "clean_usgs_JP_M4_20230101_20260331.parquet"
OUT_NAME  = "clean_usgs_JP_M4_daily_20230101_20260331.parquet"
OUT_PATH  = CLEAN_DIR / OUT_NAME

GRID_START = pd.Timestamp("2023-01-01", tz="UTC")
GRID_END   = pd.Timestamp("2026-03-31", tz="UTC")


def pct(n, total): return f"{100*n/total:.4f}%"


# ─────────────────────────────────────────────────────────────────────────────
def build_daily_summary() -> pd.DataFrame:
    print("=" * 65)
    print("  GIAI ĐOẠN 3: Daily Earthquake Summary")
    print("=" * 65)

    # Nạp file clean
    df = pd.read_parquet(CLEAN_IN)
    N_EVENTS_TOTAL   = len(df)
    N_EVENTS_JAPAN   = int((df["region"] == "Japan").sum())
    N_EVENTS_M5PLUS  = int((df["mag"] >= 5.0).sum())
    print(f"\n  Nạp {N_EVENTS_TOTAL:,} sự kiện từ {CLEAN_IN.name}")
    print(f"  n_events_japan   = {N_EVENTS_JAPAN:,}")
    print(f"  n_events_m5plus  = {N_EVENTS_M5PLUS:,}")

    # Cột ngày UTC (từ time_utc)
    df["date"] = df["time_utc"].dt.normalize()   # cắt về 00:00:00 UTC

    # ── Tổng hợp theo ngày ───────────────────────────────────────────────
    def dominant_magtype(series):
        if series.empty:
            return pd.NA
        return series.value_counts().idxmax()

    agg = df.groupby("date").agg(
        n_events         = ("event_id",  "count"),
        n_events_japan   = ("region",    lambda x: (x == "Japan").sum()),
        n_events_m5plus  = ("mag",       lambda x: (x >= 5.0).sum()),
        max_mag          = ("mag",        "max"),
        dominant_magtype = ("mag_type",   dominant_magtype),
        mean_depth_km    = ("depth_km",   "mean"),
    ).reset_index()

    # ── Lưới ngày đầy đủ ─────────────────────────────────────────────────
    full_grid = pd.DataFrame({
        "date": pd.date_range(GRID_START, GRID_END, freq="D", tz="UTC")
    })
    N_DAYS_EXPECTED = len(full_grid)
    print(f"\n  Lưới ngày: {GRID_START.date()} → {GRID_END.date()} = {N_DAYS_EXPECTED:,} ngày")

    summary = full_grid.merge(agg, on="date", how="left")

    # Ngày không có sự kiện: count → 0, float/str → NULL (không điền 0)
    for col in ["n_events", "n_events_japan", "n_events_m5plus"]:
        summary[col] = summary[col].fillna(0).astype("int32")
    # max_mag, dominant_magtype, mean_depth_km giữ NaN cho ngày trống
    summary["max_mag"]          = summary["max_mag"].astype("float32")
    summary["mean_depth_km"]    = summary["mean_depth_km"].astype("float32")
    summary["dominant_magtype"] = summary["dominant_magtype"].astype(object)
    # Đổi pd.NA về None (compatible với Parquet)
    summary["dominant_magtype"] = summary["dominant_magtype"].where(
        summary["dominant_magtype"].notna(), other=None)

    # ── Assert ────────────────────────────────────────────────────────────
    print(f"\n── Kiểm chứng (assert) ──")

    # 1. Số dòng = 1,186
    assert len(summary) == N_DAYS_EXPECTED, \
        f"❌ Số dòng {len(summary)} ≠ {N_DAYS_EXPECTED}"
    print(f"  ✅ Số dòng = {len(summary):,}")

    # 2. Ngày liên tục, không thiếu
    diffs = summary["date"].diff().dropna()
    gaps  = (diffs != pd.Timedelta("1D")).sum()
    assert gaps == 0, f"❌ Có {gaps} khoảng không phải 1 ngày"
    print(f"  ✅ Ngày liên tục, không thiếu (không gap)")

    # 3. sum(n_events) = N_EVENTS_TOTAL
    sum_n = int(summary["n_events"].sum())
    assert sum_n == N_EVENTS_TOTAL, \
        f"❌ sum(n_events)={sum_n} ≠ {N_EVENTS_TOTAL}"
    print(f"  ✅ sum(n_events) = {sum_n:,} = N_EVENTS_TOTAL")

    # 4. sum(n_events_japan) = N_EVENTS_JAPAN
    sum_jp = int(summary["n_events_japan"].sum())
    assert sum_jp == N_EVENTS_JAPAN, \
        f"❌ sum(n_events_japan)={sum_jp} ≠ {N_EVENTS_JAPAN}"
    print(f"  ✅ sum(n_events_japan) = {sum_jp:,} = N_EVENTS_JAPAN")

    # 5. sum(n_events_m5plus) = N_EVENTS_M5PLUS
    sum_m5 = int(summary["n_events_m5plus"].sum())
    assert sum_m5 == N_EVENTS_M5PLUS, \
        f"❌ sum(n_events_m5plus)={sum_m5} ≠ {N_EVENTS_M5PLUS}"
    print(f"  ✅ sum(n_events_m5plus) = {sum_m5:,} = N_EVENTS_M5PLUS")

    # 6. Ngày có 0 sự kiện: max_mag, mean_depth_km phải NULL
    zero_days   = summary[summary["n_events"] == 0]
    n_zero_days = len(zero_days)
    bad_mag     = zero_days["max_mag"].notna().sum()
    bad_depth   = zero_days["mean_depth_km"].notna().sum()
    bad_magtype = zero_days["dominant_magtype"].notna().sum()
    assert bad_mag == 0,     f"❌ {bad_mag} ngày 0 sự kiện có max_mag khác NULL"
    assert bad_depth == 0,   f"❌ {bad_depth} ngày 0 sự kiện có mean_depth_km khác NULL"
    assert bad_magtype == 0, f"❌ {bad_magtype} ngày 0 sự kiện có dominant_magtype khác NULL"
    print(f"  ✅ {n_zero_days:,} ngày 0 sự kiện: max_mag / mean_depth_km / dominant_magtype = NULL")

    print(f"\n  ✅ Tất cả assert PASSED")

    # ── Thống kê ──────────────────────────────────────────────────────────
    print(f"\n── Thống kê daily summary ──")
    print(f"  Số ngày có sự kiện   : {int((summary['n_events'] > 0).sum()):,}")
    print(f"  Số ngày 0 sự kiện    : {n_zero_days:,}")
    print(f"  Max n_events trong 1 ngày: {int(summary['n_events'].max())}")

    top5 = summary.nlargest(5, "n_events")[
        ["date", "n_events", "max_mag", "dominant_magtype"]
    ]
    print(f"\n  Top 5 ngày có nhiều sự kiện nhất:")
    print(f"  {'Ngày':<14} {'n_events':>9} {'max_mag':>8}  dominant_magtype")
    print("  " + "─" * 50)
    for _, r in top5.iterrows():
        print(f"  {str(r['date'].date()):<14} {int(r['n_events']):>9,} "
              f"{r['max_mag']:>8.1f}  {r['dominant_magtype']}")

    print(f"\n  Phân phối n_events:")
    bins = [0, 1, 5, 10, 20, 50, 200]
    labels = ["0", "1–4", "5–9", "10–19", "20–49", "≥50"]
    cuts = pd.cut(summary["n_events"], bins=bins,
                  labels=labels, right=False, include_lowest=True)
    for lbl, cnt in cuts.value_counts().sort_index().items():
        print(f"    {lbl:>8} SĐ/ngày: {cnt:>5,} ngày")

    return summary, {
        "N_DAYS": N_DAYS_EXPECTED,
        "N_EVENTS": N_EVENTS_TOTAL,
        "N_JAPAN": N_EVENTS_JAPAN,
        "N_M5PLUS": N_EVENTS_M5PLUS,
        "N_ZERO_DAYS": n_zero_days,
        "MAX_DAY_EVENTS": int(summary["n_events"].max()),
        "TOP5": top5.to_dict("records"),
    }


# ─────────────────────────────────────────────────────────────────────────────
def export_parquet(summary: pd.DataFrame):
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_parquet(OUT_PATH, index=False, engine="pyarrow", compression="snappy")
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"\n  💾 Parquet: {OUT_NAME}  ({size_kb:.1f} KB)")
    print(f"     {len(summary):,} ngày × {len(summary.columns)} cột")


# ─────────────────────────────────────────────────────────────────────────────
def update_data_dictionary(stats: dict):
    """Cập nhật data_dictionary.md: thêm phần daily summary + đánh dấu cột thô."""
    dd_path = DOCS_DIR / "data_dictionary.md"
    today   = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    dd_text = dd_path.read_text(encoding="utf-8")

    # Thêm section daily summary vào cuối (trước --- cuối)
    daily_section = f"""
## File daily summary

`data/clean/clean_usgs_JP_M4_daily_20230101_20260331.parquet`

### Schema cột daily summary

| Cột | Kiểu | Đơn vị | Mô tả | Ngày trống |
|---|---|---|---|---|
| `date` | `datetime64[us, UTC]` | – | Ngày UTC (00:00:00Z) | – |
| `n_events` | `int32` | – | Số sự kiện trong ngày | `0` |
| `n_events_japan` | `int32` | – | Sự kiện thuộc region=Japan | `0` |
| `n_events_m5plus` | `int32` | – | Sự kiện M ≥ 5.0 | `0` |
| `max_mag` | `float32` | – | Magnitude lớn nhất trong ngày | `NULL` |
| `dominant_magtype` | `object` | – | magType phổ biến nhất (mode) | `NULL` |
| `mean_depth_km` | `float32` | km | Độ sâu trung bình | `NULL` |

> ⚠️ `max_mag` và `dominant_magtype` trộn nhiều thang đo (mb, mww, mwr…). 
> Không so sánh tuyệt đối giữa các ngày có `dominant_magtype` khác nhau.
> Ngày có dư chấn sau trận lớn **không bị xoá**; n_events đột biến là thực tế địa chấn.

### Thông số lưới

| Thuộc tính | Giá trị |
|---|---|
| Số ngày (lưới đầy đủ) | {stats['N_DAYS']:,} |
| sum(n_events) | {stats['N_EVENTS']:,} (= tổng sự kiện file clean) |
| sum(n_events_japan) | {stats['N_JAPAN']:,} |
| sum(n_events_m5plus) | {stats['N_M5PLUS']:,} (sự kiện M≥5.0) |
| Ngày 0 sự kiện | {stats['N_ZERO_DAYS']:,} |
| Ngày nhiều nhất | {stats['MAX_DAY_EVENTS']} sự kiện |
| Ngày tải | {today} |

## Cột thô USGS (ít dùng trực tiếp)

Các cột sau được giữ nguyên từ CSV gốc USGS để phục vụ phân tích chuyên sâu.
Phần lớn không dùng trong dashboard Power BI thông thường:

| Cột | Ghi chú |
|---|---|
| `nst` | Số trạm định vị – chỉ số tin cậy vị trí |
| `gap_deg` | Góc azimuth trạm – chỉ số tin cậy vị trí |
| `dmin_deg` | Khoảng cách tới trạm gần nhất |
| `rms` | Residual định vị – chỉ số tin cậy vị trí |
| `net` | Mạng lưới báo cáo sự kiện (us, pt, …) |
| `horizontal_error_km` | Sai số ngang định vị |
| `depth_error_km` | Sai số độ sâu |
| `mag_error` | Sai số magnitude |
| `mag_nst` | Số trạm tính magnitude |
| `location_source` | Mạng lưới cung cấp định vị |
| `mag_source` | Mạng lưới cung cấp magnitude |
| `event_type` | Luôn = `earthquake` (đã lọc khi tải; cột hằng số) |
| `updated_utc` | Timestamp cập nhật cuối – dùng để dedup, không cần cho analysis |

---
*Cập nhật: {today}*
"""
    # Chèn trước --- cuối cùng hoặc thêm vào cuối
    marker = "\n---\n*Cập nhật:"
    if marker in dd_text:
        dd_text = dd_text[:dd_text.rfind(marker)]
    dd_path.write_text(dd_text + daily_section, encoding="utf-8")
    print(f"  📄 data_dictionary.md (cập nhật)")


# ─────────────────────────────────────────────────────────────────────────────
def update_quality_report(stats: dict):
    """Thêm section daily summary vào data_quality_report.md."""
    qr_path = DOCS_DIR / "data_quality_report.md"
    today   = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    top5_rows = "\n".join(
        f"| {str(pd.Timestamp(r['date']).date())} | {int(r['n_events']):,} | "
        f"{float(r['max_mag']):.1f} | {r['dominant_magtype']} |"
        for r in stats["TOP5"]
    )

    section = f"""
## 9. Daily Summary (Giai đoạn 3)

| Thuộc tính | Giá trị |
|---|---|
| File | `{OUT_NAME}` |
| Số ngày (lưới đầy đủ) | {stats['N_DAYS']:,} |
| Assert n_events | sum = {stats['N_EVENTS']:,} ✅ |
| Assert n_events_japan | sum = {stats['N_JAPAN']:,} ✅ |
| Assert n_events_m5plus | sum = {stats['N_M5PLUS']:,} ✅ |
| Ngày 0 sự kiện | {stats['N_ZERO_DAYS']:,} (max_mag/dominant_magtype/mean_depth_km = NULL) ✅ |
| Ngày nhiều nhất | {stats['MAX_DAY_EVENTS']:,} sự kiện |
| Tạo lúc | {today} |

### Top 5 ngày nhiều sự kiện nhất

| Ngày | n_events | max_mag | dominant_magtype |
|---|---|---|---|
{top5_rows}

> Các ngày đột biến do dư chấn **không bị xoá**. Người dùng Power BI nên
> nhận biết các ngày này khi diễn giải xu hướng.

---
*Cập nhật: {today}*
"""
    text = qr_path.read_text(encoding="utf-8")
    # Bỏ --- cuối cũ rồi thêm section mới
    marker = "\n---\n*Cập nhật:"
    if marker in text:
        text = text[:text.rfind(marker)]
    qr_path.write_text(text + section, encoding="utf-8")
    print(f"  📄 data_quality_report.md (cập nhật)")


# ─────────────────────────────────────────────────────────────────────────────
def update_scope(stats: dict):
    """Cập nhật scope.md: thêm dòng daily summary."""
    scope = cfg.DOCS_DIR / "scope.md"
    text  = scope.read_text(encoding="utf-8")
    note  = (f"\n### Bảng daily summary\n\n"
             f"File: `data/clean/{OUT_NAME}`  \n"
             f"Lưới {stats['N_DAYS']:,} ngày, "
             f"{stats['N_ZERO_DAYS']:,} ngày không có sự kiện.  \n"
             f"Kiểm chứng: sum(n_events)={stats['N_EVENTS']:,}, "
             f"sum(n_events_japan)={stats['N_JAPAN']:,}, "
             f"sum(n_events_m5plus)={stats['N_M5PLUS']:,}.\n")
    if "Bảng daily summary" not in text:
        text += note
        scope.write_text(text, encoding="utf-8")
    print(f"  📄 scope.md (thêm daily summary)")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    summary, stats = build_daily_summary()
    export_parquet(summary)

    print(f"\n  Cập nhật tài liệu...")
    update_data_dictionary(stats)
    update_quality_report(stats)
    update_scope(stats)

    print(f"\n{'='*65}")
    print(f"  KẾT QUẢ GIAI ĐOẠN 3  |  DỪNG, CHỜ XÁC NHẬN")
    print(f"{'='*65}")
    print(f"  File: {OUT_NAME}")
    print(f"  Số ngày lưới  : {stats['N_DAYS']:,}")
    print(f"  sum(n_events) : {stats['N_EVENTS']:,}  ✅")
    print(f"  sum(jp)       : {stats['N_JAPAN']:,}  ✅")
    print(f"  sum(m5+)      : {stats['N_M5PLUS']:,}  ✅")
    print(f"  Ngày 0 SĐ     : {stats['N_ZERO_DAYS']:,}")
    print(f"  Ngày nhiều nhất: {stats['MAX_DAY_EVENTS']:,} SĐ")
    print(f"\n→ DỪNG. Chờ xác nhận.")


if __name__ == "__main__":
    main()
