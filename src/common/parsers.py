"""
parsers.py – Các hàm đọc dữ liệu thô (HAPI CSV từ INTERMAGNET và USGS CSV/GeoJSON).

Nguyên tắc:
  - KHÔNG sửa dữ liệu gốc, chỉ trả DataFrame với đúng schema snake_case.
  - Đọc metadata từ HAPI info endpoint.
  - Trả timestamp chuẩn ISO 8601 UTC.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg


# ─────────────────────────────────────────────────────────────────────────────
# INTERMAGNET HAPI CSV
# ─────────────────────────────────────────────────────────────────────────────

# Sentinel xác nhận từ HAPI info endpoint (fill=99999.0)
# Áp dụng cho cả Field_Vector (X,Y,Z) và Field_Magnitude (F)
HAPI_SENTINEL = 99999.0


def _get_hapi_meta(station: str) -> dict:
    """
    Lấy metadata từ HAPI info endpoint.
    Trả dict gồm: startDate, stopDate, parameters (list), sentinel_value.
    Nguồn: https://imag-data.bgs.ac.uk/GIN_V1/hapi/info
    """
    import requests
    dataset = cfg.INTERMAGNET_HAPI_DATASET.format(station_lower=station.lower())
    url = f"{cfg.INTERMAGNET_HAPI_BASE}/info"
    try:
        resp = requests.get(url, params={"dataset": dataset}, timeout=20)
        info = resp.json()
    except Exception as e:
        print(f"  ⚠  Không lấy được HAPI info: {e}")
        return {}

    # Lấy sentinel từ parameters (field "fill")
    sentinel = HAPI_SENTINEL  # mặc định; sẽ ghi đè nếu tìm thấy
    for param in info.get("parameters", []):
        if param.get("fill") is not None:
            try:
                sentinel = float(param["fill"])
                break
            except (TypeError, ValueError):
                pass

    return {
        "station_code":          station.upper(),
        "start_date":            info.get("startDate"),
        "stop_date":             info.get("stopDate"),
        "parameters":            info.get("parameters", []),
        "sentinel_values":       [sentinel],
        # Toạ độ nếu có trong additionalMetadata
        "geodetic_lat":          info.get("additionalMetadata", {}).get("latitude"),
        "geodetic_lon":          info.get("additionalMetadata", {}).get("longitude"),
        "elevation":             info.get("additionalMetadata", {}).get("elevation"),
        "reported_components":   "XYZF",
        "data_type":             "Definitive",
        "sample_period_seconds": 60,
        "source_of_data":        info.get("resourceURL", "BGS HAPI / INTERMAGNET"),
    }


def parse_hapi_csv_file(path: Path, station: str) -> tuple[pd.DataFrame, dict]:
    """
    Đọc một file HAPI CSV (.csv) của INTERMAGNET → (DataFrame, metadata_dict).

    File không có header – cột theo thứ tự xác nhận từ HAPI info:
      0: Time (ISO 8601 UTC, dạng "YYYY-MM-DDTHH:MMZ")
      1: Field_Vector_X (nT)
      2: Field_Vector_Y (nT)
      3: Field_Vector_Z (nT)
      4: Field_Magnitude = F (nT)

    Sentinel HAPI_SENTINEL (99999.0) CHƯA được thay bằng NaN ở bước này;
    giữ nguyên để Bước 2 (kiểm tra chất lượng) có thể đếm.
    """
    path = Path(path)

    # Đọc CSV – không có header, không có comment lines trong HAPI CSV
    df = pd.read_csv(
        path,
        header=None,
        names=["time_utc", "x_nt", "y_nt", "z_nt", "f_nt"],
        dtype={"x_nt": "float64", "y_nt": "float64",
               "z_nt": "float64", "f_nt": "float64"},
        comment="#",   # bỏ qua dòng comment nếu API thêm vào
    )

    # Chuyển timestamp → datetime UTC
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)

    # Thêm cột station (vị trí 1 sau time_utc)
    df.insert(1, "station", station.upper())

    # Metadata (không cần gọi API ở bước đọc file)
    # Lấy data_type từ config để ghi đúng vào metadata
    meta = {
        "station_code":          station.upper(),
        "reported_components":   "XYZF",
        "data_type":             cfg.DATA_TYPE,   # "quasi-definitive" hoặc "definitive"
        "sample_period_seconds": 60,
        "sentinel_values":       [HAPI_SENTINEL],
        "source":                "BGS HAPI / INTERMAGNET",
        "hapi_dataset":          cfg.INTERMAGNET_HAPI_DATASET.format(station_lower=station.lower()),
    }

    return df, meta


def load_all_intermagnet(station: str) -> tuple[pd.DataFrame, dict]:
    """
    Nạp tất cả file HAPI CSV của một trạm trong data/raw/intermagnet/.
    Ghép theo thời gian, trả về (DataFrame tổng hợp, metadata).

    Tên file: intermagnet_{STATION}_{datatype}_1min_{YYYYMMDD}_{YYYYMMDD}.csv
    datatype: "quasi-def" hoặc "definitive"
    """
    raw_dir = cfg.DATA_RAW / "intermagnet"
    # Tìm file theo datatype hiện tại trong config
    dtype_slug = "quasi-def" if "quasi" in cfg.DATA_TYPE else "definitive"
    files = sorted(raw_dir.glob(f"intermagnet_{station}_{dtype_slug}_1min_*.csv"))
    if not files:
        raise FileNotFoundError(
            f"Không tìm thấy file CSV cho trạm {station} trong {raw_dir}\n"
            f"  → Chạy: python src/download_data.py --source intermagnet"
        )

    dfs = []
    meta_first = None
    for f in files:
        try:
            df_part, meta = parse_hapi_csv_file(f, station)
            if meta_first is None:
                meta_first = meta
            dfs.append(df_part)
        except Exception as e:
            print(f"  ⚠  Bỏ qua {f.name}: {e}")

    if not dfs:
        raise ValueError(f"Không nạp được file nào cho trạm {station}")

    df = pd.concat(dfs, ignore_index=True)
    df = df.sort_values("time_utc").reset_index(drop=True)
    return df, meta_first


def get_station_meta(station: str) -> dict:
    """
    Lấy metadata đầy đủ từ HAPI info endpoint (cần kết nối internet).
    Dùng ở Bước 1 để báo cáo toạ độ, sentinel chính xác.
    """
    return _get_hapi_meta(station)


# ─────────────────────────────────────────────────────────────────────────────
# USGS CSV
# ─────────────────────────────────────────────────────────────────────────────

# Cột tiêu chuẩn USGS ComCat CSV → tên snake_case nội bộ
USGS_CSV_RENAME = {
    "time":            "time_utc",
    "latitude":        "latitude",
    "longitude":       "longitude",
    "depth":           "depth_km",
    "mag":             "magnitude",
    "magType":         "mag_type",
    "nst":             "n_stations",
    "gap":             "azimuthal_gap",
    "dmin":            "dist_to_nearest_station_deg",
    "rms":             "rms_residual",
    "net":             "network",
    "id":              "event_id",
    "updated":         "updated_utc",
    "place":           "place",
    "type":            "event_type",
    "horizontalError": "horizontal_error_km",
    "depthError":      "depth_error_km",
    "magError":        "mag_error",
    "magNst":          "n_stations_mag",
    "status":          "review_status",
    "locationSource":  "location_source",
    "magSource":       "mag_source",
}


def load_usgs_csv() -> pd.DataFrame:
    """
    Nạp tất cả file usgs_earthquake_*.csv trong data/raw/usgs/.
    Trả DataFrame đã chuẩn hoá: time_utc là datetime64[ns, UTC].
    Sentinel: không có sentinel rõ ràng trong USGS CSV (dùng NaN tự nhiên).
    """
    raw_dir = cfg.DATA_RAW / "usgs"
    files = sorted(raw_dir.glob("usgs_earthquake_*.csv"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy file USGS CSV trong {raw_dir}")

    dfs = []
    for f in files:
        df_part = pd.read_csv(f, low_memory=False)
        dfs.append(df_part)

    df = pd.concat(dfs, ignore_index=True)

    # Đổi tên cột
    df = df.rename(columns={k: v for k, v in USGS_CSV_RENAME.items() if k in df.columns})

    # Chuyển timestamp
    if "time_utc" in df.columns:
        df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    if "updated_utc" in df.columns:
        df["updated_utc"] = pd.to_datetime(df["updated_utc"], utc=True)

    df = df.sort_values("time_utc").reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# USGS GeoJSON
# ─────────────────────────────────────────────────────────────────────────────

def load_usgs_geojson() -> pd.DataFrame:
    """
    Nạp tất cả file usgs_earthquake_*.geojson trong data/raw/usgs/.
    Trả DataFrame phẳng với cùng schema như load_usgs_csv().
    """
    raw_dir = cfg.DATA_RAW / "usgs"
    files = sorted(raw_dir.glob("usgs_earthquake_*.geojson"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy file USGS GeoJSON trong {raw_dir}")

    records = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            gj = json.load(fh)
        for feat in gj.get("features", []):
            props  = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [None, None, None])
            rec = {
                "time_utc":      pd.Timestamp(props.get("time"), unit="ms", tz="UTC")
                                 if props.get("time") else pd.NaT,
                "updated_utc":   pd.Timestamp(props.get("updated"), unit="ms", tz="UTC")
                                 if props.get("updated") else pd.NaT,
                "longitude":     coords[0],
                "latitude":      coords[1],
                "depth_km":      coords[2],
                "magnitude":     props.get("mag"),
                "mag_type":      props.get("magType"),
                "n_stations":    props.get("nst"),
                "azimuthal_gap": props.get("gap"),
                "rms_residual":  props.get("rms"),
                "event_id":      props.get("ids", "").strip(",").split(",")[0],
                "place":         props.get("place"),
                "event_type":    props.get("type"),
                "network":       props.get("net"),
                "review_status": props.get("status"),
                "location_source": props.get("locationSource"),
                "mag_source":    props.get("magSource"),
            }
            records.append(rec)

    df = pd.DataFrame(records)
    df = df.sort_values("time_utc").reset_index(drop=True)
    return df
