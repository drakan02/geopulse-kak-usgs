# CV3 - Enhancement SNR Comparison

## 1. Các phương pháp

CV3 triển khai các phương pháp lọc tín hiệu:

- Median Filter
- Butterworth Band-pass
- Wavelet Denoising
- Kalman Smoothing

Ngoài ra có bổ sung Butterworth Lowpass để so sánh hiệu quả khử nhiễu.

## 2. SNR Benchmark

Benchmark sử dụng dữ liệu kênh X của trạm KAK trong 1 ngày.

Tín hiệu được loại bỏ mean, sau đó thêm Gaussian noise có kiểm soát để tính SNR trước và sau lọc.

| Phương pháp | SNR trước | SNR sau | Cải thiện |
|---|---:|---:|---:|
| Median | 9.27 dB | 14.58 dB | +5.31 dB |
| Butterworth Lowpass | 9.27 dB | 18.92 dB | +9.65 dB |
| Butterworth Bandpass | 9.27 dB | 0.11 dB | -9.16 dB |
| Wavelet | 9.27 dB | 13.25 dB | +3.98 dB |
| Kalman | 9.27 dB | 15.33 dB | +6.06 dB |

Butterworth Lowpass cho mức cải thiện SNR cao nhất trong benchmark.

Butterworth Bandpass loại bỏ thành phần DC và các tần số ngoài dải nên không phù hợp để đánh giá trực tiếp bằng RMSE hoặc SNR theo cùng cách với các phương pháp denoising khác.

## 3. Thử nghiệm thực tế

Các bộ lọc được chạy trên dữ liệu tháng 01/2024 của 4 kênh:

- X
- Y
- Z
- F

Mỗi kênh có 44.640 mẫu.

Tổng cộng:

- 4 kênh
- 5 phương pháp
- 20 runs
- 892.800 điểm filtered

Kết quả chi tiết được lưu tại:

`cv3/results/filter_metrics.csv`

và:

`cv3/results/snr_comparison.csv`

## 4. Kết luận

Median giữ tín hiệu gốc tốt.

Butterworth Lowpass cho khả năng giảm nhiễu tốt nhất trong benchmark SNR.

Kalman và Wavelet cho khả năng làm mượt tốt trong khi vẫn giữ correlation cao với tín hiệu ban đầu.

Butterworth Bandpass nên được đánh giá riêng bằng phân tích miền tần số.