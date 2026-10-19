# Bước 2 — Công thức và quy ước số

## 1. Ranh giới chuẩn và ranh giới encoder

AAC truyền `global_gain`, chênh lệch scalefactor, codebook/section và các chỉ số phổ. Decoder dùng phép nghịch lượng tử hóa lũy thừa `4/3`. Chuẩn hóa bitstream và phép nghịch lượng tử hóa là phần phải tương thích; cách encoder tìm gain, ngưỡng nhiễu và số vòng lặp rate–distortion không bị chuẩn ép dùng một thuật toán duy nhất.

Trong project này có hai oracle:

- `quantization_float.py`: công thức số thực để đọc, phân tích sai số và thử gain.
- `quantization_fixed.py` cùng C++: hành vi fixed-point của FDK trên cấu hình `ARCH_PREFER_MULT_32x16`; đây là golden oracle cho RTL.

## 2. Forward quantization

Với một hệ số MDCT thực `x`, `QSS = globalGain - scalefactor[sfb]` và offset `k`:

```text
q = sign(x) · floor(|x|^(3/4) · 2^(-3·QSS/16) + k)
```

`k = 0.4054` cho AAC-LC thông thường. FDK chỉ bật lựa chọn dead-zone `k = 0.23` cho cấu hình low-delay thỏa điều kiện bitrate; vector dead-zone vẫn được giữ để kiểm tra nhánh phần cứng.

Không có hệ số `4096` trong công thức trên. Khi `mdctSpectrum` Q1.31 đã được đổi thành `x = raw / 2^31`, scale fixed-point đã bị loại bỏ. Thêm `2^12` ở đây sẽ đếm scale hai lần.

## 3. Inverse quantization

Quan hệ số thực dùng để kiểm tra là:

```text
x_hat = sign(q) · |q|^(4/3) · 2^(QSS/4)
```

Hàm inverse nội bộ trong encoder FDK trả kết quả bằng một nửa miền Q1.31 để tránh overflow. Vì vậy phép tính distortion của FDK so sánh kết quả này với `mdctSpectrum >> 1`; không được so trực tiếp với full-scale Q1.31.

## 4. Ánh xạ gain/scalefactor

Tại kernel:

```text
QSS[sfb] = globalGain_internal - scalefactor_internal[sfb]
```

Khi ghi bitstream, FDK bù scalefactor đầu tiên, hằng số syntax và `mdctScale`. Vì thế không nên đưa `globalGain_internal` thẳng ra bitstream. Adapter bitstream nằm ngoài spectral core; input của core luôn là QSS nội bộ hoặc cặp `globalGain_internal/scalefactor_internal`.

## 5. Các tầng fixed-point FDK

| Tầng | Phép toán | Miền/width |
|---|---|---|
| Gain residue | `fMultDiv2(Q1.31, Q1.15)` | tích dịch phải 16, signed 32-bit |
| Normalize | CLZ rồi dịch trái | mantissa chuẩn hóa Q1.31 |
| `3/4` | LUT 512×16 | địa chỉ 9 bit |
| Exponent residue | LUT 4×16 và nhân 16×16 | signed 32-bit |
| Exponent integer | dịch phải arithmetic | lượng dịch tính từ QSS và CLZ |
| Rounding | cộng `13284` hoặc `7536`, rồi `>>15` | signed 32-bit |
| Output | thu hẹp sang `SHORT` | signed 16-bit; hợp lệ nếu `|q| ≤ 8191` |

ROM được sinh bởi `tools/extract_fdk_tables.py` trực tiếp từ `aacEnc_rom.cpp`. Không dùng lại `pow()` trong golden model fixed/C++.

## 6. Rounding, overflow và range gate

- Dịch phải số âm được hiểu là arithmetic shift; Python và C++ reference khóa rõ hành vi này.
- Dấu được tách trước phần lũy thừa và khôi phục sau cùng, nên `Q(-x) = -Q(x)`.
- Kernel gốc thu hẹp sang 16 bit, không saturate từng line.
- `qc_main.cpp` kiểm tra max magnitude theo SFB với giới hạn `MAX_QUANT = 8191`; nếu vi phạm, outer loop tăng gain rồi lượng tử hóa lại.
- Reference mặc định ném lỗi khi max vượt giới hạn. Cờ cho phép out-of-range chỉ dùng để chẩn đoán, không phải trạng thái AAC hợp lệ.

## 7. Sai số dự kiến

Float và fixed thường trùng, nhưng có thể lệch một đơn vị gần ngưỡng do LUT và truncation. Python fixed và C++ phải trùng tuyệt đối ở output và mọi intermediate field. RTL golden mode cũng phải trùng tuyệt đối; approximation chỉ được đánh giá ở một profile riêng với báo cáo max/mean error và vị trí sai theo SFB/line.
