# ERD của CV2

Thiết kế gồm 12 bảng: Raw (3), Clean (6), Analytics (3), chưa tính view và
continuous aggregate. PK/FK trên cùng nhiều cột là khóa ghép. Bảng schema_version
đứng độc lập vì dùng theo dõi phiên bản cấu trúc.

## Sơ đồ đầy đủ các cột

```mermaid
erDiagram
    RAW_FILE_ARCHIVE ||--o| RAW_IMPORT_BATCH : imported_as
    RAW_IMPORT_BATCH ||--o{ CLEAN_MEASUREMENT : traces
    RAW_IMPORT_BATCH ||--o{ CLEAN_EARTHQUAKE_EVENT : traces
    RAW_IMPORT_BATCH ||--o{ CLEAN_EARTHQUAKE_DAILY : traces
    CLEAN_STATION ||--o{ CLEAN_CHANNEL : has
    CLEAN_CHANNEL ||--o{ CLEAN_MEASUREMENT : measures
    CLEAN_QUALITY_FLAG ||--o{ CLEAN_MEASUREMENT : labels_channel_and_source
    CLEAN_CHANNEL ||--o{ ANALYTICS_MODEL_RUN : input_channel
    ANALYTICS_MODEL_RUN ||--o{ ANALYTICS_FILTERED_SERIES : filter_output
    ANALYTICS_MODEL_RUN ||--o{ ANALYTICS_FORECAST_RESULT : forecast_output
    CLEAN_QUALITY_FLAG ||--o{ ANALYTICS_FILTERED_SERIES : labels
    RAW_SCHEMA_VERSION {
        integer version PK
        timestamptz installed_at
    }
    RAW_FILE_ARCHIVE {
        bigint file_id PK
        text source_kind
        text source_stage
        text filename
        string sha256
        bigint byte_size
        bigint row_count
        bytea content
        timestamptz archived_at
    }
    RAW_IMPORT_BATCH {
        bigint batch_id PK
        bigint file_id FK,UK
        text target_table
        bigint imported_rows
        timestamptz imported_at
    }
    CLEAN_STATION {
        text station_code PK
        text station_name
        text country
        float latitude
        float longitude
        real elevation_m
        text data_type
        text source_dataset
    }
    CLEAN_CHANNEL {
        text station_code PK,FK
        text channel_code PK
        text description
        text unit
        interval sample_interval
    }
    CLEAN_QUALITY_FLAG {
        smallint flag PK
        text label UK
        text description
    }
    CLEAN_MEASUREMENT {
        timestamptz time_utc PK
        text station_code PK,FK
        text channel_code PK,FK
        real value
        smallint quality_flag FK
        smallint source_quality_flag FK
        bigint batch_id FK
    }
    CLEAN_EARTHQUAKE_EVENT {
        text event_id PK
        timestamptz time_utc
        timestamptz updated_utc
        real latitude
        real longitude
        real depth_km
        real mag
        text mag_type
        text place
        text event_type
        text status
        text region
        bigint nst
        bigint gap_deg
        float dmin_deg
        float rms
        text net
        float horizontal_error_km
        float depth_error_km
        float mag_error
        bigint mag_nst
        text location_source
        text mag_source
        bigint batch_id FK
    }
    CLEAN_EARTHQUAKE_DAILY {
        date date PK
        integer n_events
        integer n_events_japan
        integer n_events_m5plus
        real max_mag
        text dominant_magtype
        real mean_depth_km
        bigint batch_id FK
    }
    ANALYTICS_MODEL_RUN {
        uuid run_id PK
        text station_code FK
        text channel_code FK
        text run_kind
        text method
        text input_series
        jsonb parameters
        jsonb metrics
        timestamptz train_start
        timestamptz train_end
        timestamptz created_at
    }
    ANALYTICS_FILTERED_SERIES {
        timestamptz time_utc PK
        uuid run_id PK,FK
        text station_code FK
        text channel_code FK
        text run_kind FK
        real filtered_value
        smallint quality_flag FK
    }
    ANALYTICS_FORECAST_RESULT {
        timestamptz target_time PK
        uuid run_id PK,FK
        text station_code FK
        text channel_code FK
        text run_kind FK
        real predicted_value
        real lower_bound
        real upper_bound
    }
```

## Giải thích quan hệ

| Quan hệ | Lực lượng | Ý nghĩa |
|---|---|---|
| file_archive → import_batch | 1 → 0..1 | File lưu có thể chưa nhập; file đã nhập có tối đa một batch ở v1 |
| import_batch → measurement / earthquake_event / earthquake_daily | 1 → 0..N | Truy từng bản ghi về đợt nhập và file nguồn |
| station → channel | 1 → 0..N | Một trạm có nhiều kênh; kênh định danh bằng trạm + mã kênh |
| channel → measurement | 1 → 0..N | Một kênh có nhiều số đo theo thời gian |
| quality_flag → measurement | Hai quan hệ 1 → 0..N | Cờ riêng kênh và cờ tổng hợp nguồn cùng tham chiếu danh mục |
| channel → model_run | 1 → 0..N | Một lần chạy thuộc đúng một trạm/kênh |
| model_run → filtered_series / forecast_result | 1 → 0..N | Lưu nhiều điểm đầu ra; chỉ loại run tương ứng được ghi vào mỗi bảng |
| quality_flag → filtered_series | 1 → 0..N | Chất lượng của điểm sau lọc |

Trong mỗi quan hệ, bản ghi con bắt buộc có cha tương ứng. Các cạnh thể hiện
khả năng 0..N của phía cha, không có nghĩa mọi bản ghi cha phải có con.

## Khóa ghép và điều kiện bổ sung

- file_archive UNIQUE `(source_kind,sha256)`; không phải SHA256 duy nhất đơn lẻ.
- channel PK `(station_code,channel_code)`.
- measurement PK `(station_code,channel_code,time_utc)`; không trùng số đo cùng thời điểm.
- model_run UNIQUE `(run_id,station_code,channel_code,run_kind)` là đích của FK ghép ở kết quả.
- filtered_series PK `(run_id,time_utc)`; forecast_result PK `(run_id,target_time)`.
- run_kind ở filtered_series cố định filter; ở forecast_result cố định forecast.

## Những liên kết có chủ đích không đặt FK

Động đất là sự kiện trong vùng nghiên cứu, không phải số đo của KAK. Không
đặt FK từ earthquake_event tới station. earthquake_daily là snapshot thống kê
CV1; đối chiếu theo ngày bằng verify, không FK trực tiếp tới từng event.
Hai nguồn chỉ ghép theo ngày UTC ở view phân tích; không suy ra nhân quả.
model_run.input_series mô tả nguồn đầu vào bằng text; chưa có FK truy lineage
giữa các lần chạy. Khi mở rộng cần thiết kế thêm nếu muốn truy nguồn tự động.

## View và aggregate

clean.kak_1min dựng lại 11 cột CV1 từ measurement, không tạo bản sao vật lý.
measurement_hourly/daily là continuous aggregate; vw_daily_context ghép theo
ngày UTC. Các view không phải thực thể mới nên không vẽ như bảng ở sơ đồ này.

Chi tiết kiểu, NULL và ý nghĩa cột: [DATA_DICTIONARY.md](DATA_DICTIONARY.md).
DDL thực thi: [001_schema.sql](sql/001_schema.sql), [002_timescale.sql](sql/002_timescale.sql).
