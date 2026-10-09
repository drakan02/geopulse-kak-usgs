# Bằng chứng chạy thực tế

Thư mục 2026-10-07 là bản chụp các báo cáo từ lần kiểm thử Windows native
ngày 07/10/2026. Timestamp trong JSON là UTC; đây không phải số đo Docker.
Các lần chạy tiếp theo xuất vào reports/ và không tự ghi đè bằng chứng đã commit.

| File | Chứng minh |
|---|---|
| input_inspection.json | Schema, SHA256, grid, QC của ba file CV1 |
| verification_full.json | Đối chiếu toàn bộ giá trị/cờ, số dòng, archive và hypertable |
| verification.json | Kiểm tra số dòng và tính nhất quán bổ sung, không full roundtrip |
| contract_checks.json | PK/FK, quy tắc missing, archive và quyền reader |
| benchmark.json | 5 lần đo, median và EXPLAIN ANALYZE BUFFERS |

Các JSON đã được kiểm tra trước commit để không chứa mật khẩu cục bộ.
original_raw_files=0 là giới hạn đầu vào thực tế, không phải lỗi bị bỏ qua.

## Kiểm tra lại trước push (2026-10-08)

[verification_full.json](2026-10-08/verification_full.json) và
[contract_checks.json](2026-10-08/contract_checks.json) là lần chạy lại trên cùng
bản native trước bàn giao. Benchmark và input inspection giữ bản chụp 07/10/2026.
