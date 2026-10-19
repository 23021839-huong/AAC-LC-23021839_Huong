# Bước 2–4 — Ánh xạ thuật toán sang reference model

| Ý nghĩa | FDK source | Float Python | Fixed Python/C++ | Tín hiệu RTL đề xuất |
|---|---|---|---|---|
| Chọn gain theo band | `globalGain - scalefactors[sfb]` | `gain` | `gain` | `qss_i[7:0]` signed |
| Gain residue | `quantTableQ[(-gain)&3]` | `2^(-3·gain/16)` gộp | ROM Q15, nhân 32×16 | ROM4 + multiplier |
| Chuẩn hóa biên độ | `CntLeadingZeros()-1` | không cần | CLZ32 + barrel shift | LZC + shifter |
| `|x|^(3/4)` | `mTab_3_4[tabIndex]` | `pow(abs(x), .75)` | ROM512×16 | BRAM/ROM LUT |
| Exponent residue | `quantTableE[totalShift&3]` | đã gộp | ROM4×16 + nhân 16×16 | ROM4 + multiplier |
| Exponent integer | `accu >>= totalShift` | đã gộp | arithmetic shifter | barrel/right shifter |
| Offset | `k=0.4054` hoặc `0.23` | số thực | raw `13284`/`7536` | mux constant + adder |
| Output | cast `SHORT` | signed integer | wrap int16 + range gate | `q_o[15:0]`, max reducer |
| Nghịch lượng tử | LUT `4/3` + exponent ROM | `pow(abs(q),4/3)` | fixed inverse helper | không thuộc forward core v1 |

## Luồng reference

```text
manifest + Q1.31 spectrum + SFB metadata
              |
              +--> Python float (oracle toán học)
              |
              +--> Python fixed (golden vectors + intermediate JSONL)
              |
              +--> standalone C++ (cùng ROM, không link FDK)
                              |
                              +--> compare_models.py <-- RTL dump
```

`active_line_mask.txt` giải quyết trường hợp short-window grouping: chỉ `max_sfb_per_group` band đầu mỗi group được kernel xử lý. Các slot còn lại không được coi là output hợp lệ dù buffer upstream có thể chứa dữ liệu cũ.

## Phần chưa port thành standalone core

PE/threshold adaptation, scalefactor estimation, section/Huffman cost và bit-reservoir vẫn là control environment. Chúng đã được vạch call graph ở Bước 1 và phải được nối bằng trace adapter nếu mục tiêu tiếp theo là tái tạo toàn bộ rate loop. Không nên nhét các khối này vào cùng một RTL spectral datapath.
