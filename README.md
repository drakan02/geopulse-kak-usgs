# Geophysical Data Pipeline

Pipeline xử lý dữ liệu địa vật lý (INTERMAGNET + USGS).

## Cấu trúc thư mục

```
.
├── data/
│   ├── raw/              # Dữ liệu gốc – KHÔNG SỬA
│   │   ├── intermagnet/  # File .min IAGA-2002
│   │   └── usgs/         # CSV + GeoJSON
│   ├── interim/          # Dữ liệu trung gian (QC results, raw parquet)
│   └── clean/            # Sản phẩm bàn giao (.parquet)
├── notebooks/
│   ├── 01_explore.ipynb  # Bước 1: Khảo sát cấu trúc
│   ├── 02_quality.ipynb  # Bước 2: Kiểm tra chất lượng
│   └── 03_clean.ipynb    # Bước 3–5: Xử lý, kiểm chứng, xuất
├── src/
│   ├── config.py             # Cấu hình trung tâm
│   ├── common/               # Xử lý chung & utilities
│   │   ├── parsers.py        # Parse HAPI CSV & USGS CSV/GeoJSON
│   │   ├── quality_checks.py # Hàm kiểm tra chất lượng
│   │   └── export.py         # Xuất Parquet & docs
│   ├── kak/                  # Phân đoạn INTERMAGNET KAK
│   │   ├── download_kak.py   # Tải dữ liệu KAK
│   │   ├── explore_quality.py # Khảo sát & QC KAK
│   │   ├── pipeline.py       # Core pipeline KAK
│   │   └── process.py        # Process & export KAK
│   └── usgs/                 # Phân đoạn USGS Earthquake
│       ├── download_usgs.py  # Tải dữ liệu USGS
│       ├── analyze_usgs.py   # Phân tích catalog USGS
│       ├── investigate_usgs.py # Kiểm tra chênh lệch & spikes
│       ├── clean_catalog.py  # Clean & dedup USGS catalog
│       └── daily_summary.py  # Daily summary USGS
├── docs/
│   ├── scope.md              # Phạm vi dataset
│   ├── data_dictionary.md    # Dictionary cho KAK
│   ├── data_dictionary_usgs.md # Dictionary cho USGS
│   ├── data_quality_report.md  # Quality report KAK
│   ├── usgs_quality_report.md  # Quality report USGS
│   └── handoff_TV2.md        # Tài liệu bàn giao
├── logs/
│   └── download_log.csv
└── requirements.txt
```

## Cài đặt

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Chạy pipeline

### Bước 0: Tải dữ liệu thô

```bash
source .venv/bin/activate
python src/kak/download_kak.py
python src/usgs/download_usgs.py
```

### Bước 1–5: Chạy pipeline

```bash
# KAK magnetic pipeline
python src/kak/process.py

# USGS earthquake pipeline
python src/usgs/clean_catalog.py
python src/usgs/daily_summary.py
```

## Bảng mã quality_flag

| Mã | Ý nghĩa |
| --- | --- |
| 0 | Giá trị gốc, hợp lệ |
| 1 | Nội suy tuyến tính (gap ngắn ≤ 5 điểm) |
| 2 | Thiếu dữ liệu – NaN (gap dài hoặc sentinel) |
| 3 | Spike (chỉ gắn cờ, không sửa) |
| 4 | Ngoài khoảng vật lý (chỉ gắn cờ) |
| 5 | Flatline (chỉ gắn cờ) |

## Cấu hình

Thay đổi tham số trong [`src/config.py`](src/config.py):
- `DATE_START`, `DATE_END`: khoảng thời gian
- `STATIONS`: danh sách trạm
- `SPIKE_K`: ngưỡng phát hiện spike (mặc định: 5σ)
- `FLATLINE_N`: ngưỡng flatline (mặc định: 10 điểm)
- `INTERP_MAX_GAP`: gap tối đa được nội suy (mặc định: 5 điểm)

## Sản phẩm bàn giao

- `data/clean/clean_intermagnet_{STATION}_1min_{START}_{END}.parquet`
- `docs/data_dictionary.md`
- `docs/data_quality_report.md`
