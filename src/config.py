"""
config.py – Cấu hình trung tâm cho toàn bộ Geophysical Data Pipeline.
Thay đổi các giá trị ở đây thay vì sửa trực tiếp trong các script xử lý.

Phạm vi cấu hình (2026-10-05):
  - KAK (INTERMAGNET): Quasi-definitive 1min (2023-01-01 → 2026-03-31)
  - USGS (Earthquake): M ≥ 4.0, lat 24–46°N, lon 122–150°E (2023-01-01 → 2026-03-31)
"""

from pathlib import Path
from datetime import date

# ── Đường dẫn gốc project ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW       = PROJECT_ROOT / "data" / "raw"
DATA_INTERIM   = PROJECT_ROOT / "data" / "interim"
DATA_CLEAN     = PROJECT_ROOT / "data" / "clean"
LOGS_DIR       = PROJECT_ROOT / "logs"
DOCS_DIR       = PROJECT_ROOT / "docs"

# ── Phạm vi thời gian (xác nhận 2026-10-05) ───────────────────────────────
DATE_START = date(2023, 1, 1)
DATE_END   = date(2026, 3, 31)   # Tháng 04/2026 valid 90.00% – chờ xác nhận

# ── Trạm INTERMAGNET ───────────────────────────────────────────────────────
# Chỉ KAK. Giữ list để thêm trạm sau không cần đổi schema.
STATIONS    = ["KAK"]
DATA_TYPE   = "quasi-definitive"   # KHÔNG đổi sang loại khác nếu không có xác nhận
SAMPLE_FREQ = "1min"
PANDAS_FREQ = "1min"

# ── INTERMAGNET download (BGS HAPI API) ────────────────────────────────────
# Dataset xác nhận: kak/quasi-def/PT1M/xyzf
#   startDate : 2013-01-01T00:00:00Z
#   stopDate  : 2026-04-30T23:59:00Z
#   sentinel  : 99999.0
# KHÔNG dùng best-avail, KHÔNG dùng reported, KHÔNG trộn loại.
INTERMAGNET_HAPI_BASE    = "https://imag-data.bgs.ac.uk/GIN_V1/hapi"
INTERMAGNET_HAPI_DATASET = "{station_lower}/quasi-def/PT1M/xyzf"

# ── USGS Earthquake catalog ────────────────────────────────────────────────
# Vùng Nhật Bản và lân cận (xác nhận 2026-10-05, có thể chỉnh sau xem bản đồ)
USGS_BBOX = {
    "minlatitude":  24.0,
    "maxlatitude":  46.0,
    "minlongitude": 122.0,
    "maxlongitude": 150.0,
}
USGS_MIN_MAG    = 4.0
USGS_EVENT_TYPE = "earthquake"
USGS_API_BASE   = "https://earthquake.usgs.gov/fdsnws/event/1/query"
USGS_COUNT_URL  = "https://earthquake.usgs.gov/fdsnws/event/1/count"  # endpoint riêng
USGS_MAX_LIMIT  = 20_000   # giới hạn USGS mỗi query; chia nhỏ nếu count vượt
USGS_TAG        = "JP"     # tiền tố trong tên file


# ── Ngưỡng kiểm tra chất lượng ────────────────────────────────────────────
# Sentinel HAPI: fill=99999.0 (xác nhận từ HAPI info endpoint, 2026-10-05)
SENTINEL_VALUES = [99999.0, 88888.0]

# Khoảng vật lý hợp lệ cho từng thành phần (nT)
# Nguồn: INTERMAGNET guide + WMM khu vực KAK (~36.2°N, 140.2°E, Nhật Bản)
# KAK nằm ở vĩ độ trung bình, trường từ mạnh hơn vùng nhiệt đới
PHYSICAL_BOUNDS = {
    "x_nt": (20_000, 50_000),    # X (North) – KAK ~29 kNT
    "y_nt": (-5_000, 10_000),    # Y (East)
    "z_nt": (20_000, 60_000),    # Z (Vertical, down) – KAK ~35 kNT
    "f_nt": (35_000, 65_000),    # F (Total intensity) – KAK ~46 kNT
    "h_nt": (20_000, 50_000),    # H (Horizontal)
    "d_nt": (-5_000,  5_000),    # D (Declination)
    "i_nt": (-5_000,  5_000),    # I (Inclination)
}

# Ngưỡng spike: |diff| > SPIKE_K × std(diff)  [chỉ trên dữ liệu đã loại sentinel]
SPIKE_K = 5.0

# Ngưỡng flatline: chuỗi hằng số liên tiếp ≥ N điểm
FLATLINE_N = 10

# Gap ngắn tối đa được nội suy tuyến tính (đơn vị: số điểm 1-phút)
INTERP_MAX_GAP = 5

# ── Kiểu dữ liệu xuất ─────────────────────────────────────────────────────
FLOAT_DTYPE   = "float32"
FLAG_DTYPE    = "int8"
STATION_DTYPE = "category"
