# Nguồn tham chiếu

## Baseline bắt buộc

1. **ISO/IEC 14496-3:2019, Information technology — Coding of audio-visual objects — Part 3: Audio.** Ấn bản 5, ISO/IEC JTC 1/SC 29. Trang catalog chính thức: <https://www.iso.org/standard/76383.html>.
   - Ý tưởng dùng: syntax/semantics AAC, inverse quantization và scalefactor/global-gain phía decoder.
   - Mức độ áp dụng: là chuẩn để đối chiếu Bước 2; chuẩn không quy định toàn bộ thuật toán tìm scalefactor/rate-control phía encoder.

2. **Fraunhofer FDK AAC Codec Library for Android**, source cục bộ tại commit `35f9c13cb6df0c5d4e7ba958ef2d251c48b8d1d9`, remote <https://github.com/mstorsjo/fdk-aac>.
   - Ý tưởng dùng: baseline hành vi fixed-point và control-flow của encoder.
   - Mức độ áp dụng: trực tiếp cho C/C++ reference và fixed-point Python model.
   - Provenance: repository cục bộ là mirror của gói FDK-AAC Android; AOSP công bố source tại <https://android.googlesource.com/platform/external/aac/>.

## File source đã dùng trong Bước 1

| Source | Vai trò đã dùng |
|---|---|
| [`libAACenc/src/aacenc.cpp`](../../../../libAACenc/src/aacenc.cpp) | Thứ tự xử lý frame, alias buffer Psy/QC, cấu hình Afterburner. |
| [`libAACenc/src/qc_main.cpp`](../../../../libAACenc/src/qc_main.cpp) | Bit distribution, outer quantization/rate loop, range check, gain update. |
| [`libAACenc/src/sf_estim.cpp`](../../../../libAACenc/src/sf_estim.cpp) | Form factor, scalefactor estimate, analysis-by-synthesis, global-gain transform. |
| [`libAACenc/src/quantize.cpp`](../../../../libAACenc/src/quantize.cpp) | Forward/inverse quantizer và SFB distortion. |
| [`libAACenc/src/aacEnc_rom.cpp`](../../../../libAACenc/src/aacEnc_rom.cpp) | LUT `3/4`, gain residue và exponent. |
| [`libAACenc/src/adj_thr.cpp`](../../../../libAACenc/src/adj_thr.cpp) | PE, threshold adaptation, bit allocation. |
| [`libAACenc/src/dyn_bits.cpp`](../../../../libAACenc/src/dyn_bits.cpp) | Codebook-cost, section merge, dynamic-bit count. |
| [`libAACenc/src/bit_cnt.cpp`](../../../../libAACenc/src/bit_cnt.cpp) | Huffman bit cost và spectral code emission. |
| [`libAACenc/src/bitenc.cpp`](../../../../libAACenc/src/bitenc.cpp) | Mapping internal gain/scalefactor/mdctScale sang bitstream syntax. |
| [`libAACenc/src/interface.h`](../../../../libAACenc/src/interface.h) | `PSY_OUT_CHANNEL` và interface Psy→QC. |
| [`libAACenc/src/qc_data.h`](../../../../libAACenc/src/qc_data.h) | `QC_OUT_CHANNEL`, `QC_STATE`, kích thước buffer. |
| [`libFDK/include/common_fix.h`](../../../../libFDK/include/common_fix.h) | Kiểu fixed-point, width và conversion constant. |
| [`libFDK/include/fixmul.h`](../../../../libFDK/include/fixmul.h) | Semantics chính xác của các phép nhân 32×16, 16×16 và 32×32. |
| [`libAACdec/src/block.cpp`](../../../../libAACdec/src/block.cpp) | Đối chiếu inverse quantization và gain/scalefactor phía decoder. |

## Nghiên cứu bổ sung

3. **P. Delgado và M. Lohwasser, “Complexity scaling of audio algorithms: Parametrizing the MPEG advanced audio coding rate-distortion loop,” DAFx 2016.** Trang công bố của Fraunhofer: <https://publica.fraunhofer.de/entities/publication/ec2ba63f-5ef2-4d1e-8c97-6b070d71585e>.
   - Ý tưởng dùng: rate–distortion loop có thể được tách thành các mức complexity và điều khiển theo workload.
   - Lý do dùng: củng cố quyết định giữ outer loop là control environment độc lập với streaming spectral kernel.
   - Mức áp dụng: chỉ định hướng kiến trúc/roadmap; không áp dụng phép xấp xỉ hay sửa golden datapath.

Chưa dùng bài báo FPGA/ASIC hoặc approximation `3/4`, `4/3`, log/exp để thay đổi baseline. Mọi approximation sau này phải nằm trong profile hardware riêng, không thay thế golden model.
