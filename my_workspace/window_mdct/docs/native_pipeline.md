# Pipeline Window/MDCT native

## Input và output

Input runner: WAV mono/stereo, sample rate lấy từ header; encoder được cấu hình AAC-LC, frame length 1024, ADTS và Afterburner.
Reader dùng chung ở my_workspace/fdk_model_testing/tools/wav_pcm.cpp chuyển dữ liệu hỗ trợ về PCM16; không resample hoặc chuẩn hóa peak.
Các WAV bàn giao đều PCM16 mono 48 kHz.

Input transform gồm PCM có lịch sử, window sequence, window shape và trạng thái MDCT từ lần trước.
Ở long/start/stop: một MDCT 1024 hệ số; ở short: tám MDCT 128 hệ số.
Tổng output mỗi frame/kênh là 1024 mantissa fixed-point kèm exponent.

## Luồng xử lý

~~~text
PCM + lịch sử + sequence/shape
              |
              v
 [Window + Fold theo trạng thái trái/phải]
              | 1024 số thực/frame
              v
       [DCT-IV pre-processing]
              | 512 cặp phức/frame
              v
       [FFT native fixed-point]
              | 512 cặp phức/frame
              v
       [DCT-IV post-processing]
              | 1024 mantissa + exponent
              v
        [MDCT spectrum -> Psy]
~~~

Ở SHORT, 512 cặp là tám khối 64 điểm độc lập; không diễn giải thành một FFT 512 điểm.

## Liên hệ source

- libAACenc/src/filterbank/transform.cpp, FDKaacEnc_Transform_Real(): chọn nSpec=8, tl=frameLength/8 cho SHORT; các sequence khác nSpec=1, tl=frameLength. START/SHORT dùng sườn phải ngắn, LONG/STOP dùng sườn phải dài.
- libFDK/src/mdct.cpp, mdct_block(): lấy sườn trái từ trạng thái trước, sườn phải từ shape hiện tại; thực hiện window/fold, gọi dct_IV(), lưu exponent và cập nhật lịch sử sườn phải.
- libFDK/src/dct.cpp và libFDK/src/fft.cpp: phép biến đổi native mà encoder thực sự dùng.
- libFDK/include/mdct_debug.h và libFDK/src/mdct_debug.cpp: hook quan sát, lưu snapshot và metadata khi MDCT_DEBUG=ON.
- tools/fdk_mdct_trace.cpp: gọi API aacEncEncode(), lấy trace từ hook và ghi AAC.
- tools/plot_mdct_stages.py: đọc số nguyên đã dump và metadata, không thay phép FFT/MDCT bằng NumPy.

Phần fold trong mdct_block() ghép các đoạn thời gian thành (-D-Cr, A-Br), sử dụng phép nhân fixed-point fMultDiv2/fMultSubDiv2/fMultAddDiv2.
Trạng thái prev_wrs/prev_fr quyết định sườn trái; không được tính từng frame độc lập rồi bỏ lịch sử.

## Trace được xuất

| File | Số dòng mỗi frame chọn | Nội dung |
|---|---:|---|
| 00_pcm_input.txt | 2048 | index, PCM16 |
| 01_window_fold.txt | 1024 | index, giá trị fold Q31 |
| 02_preprocessing.txt | 512 | index, real, imaginary |
| 03_fft.txt | 512 | index, real, imaginary |
| 04_postprocessing.txt | 1024 | index, mantissa |
| 05_mdct_output.txt | 1024 | index, mantissa MDCT |
| 05_mdct_exponents.txt | 1024 | index, exponent tương ứng |

stage_metadata.json ghi frame/kênh, sequence/shape, từng subtransform và thang số.
input_info.json mô tả WAV và chuyển đổi; run_status.json xác nhận run hoàn tất.
encoded.aac là bitstream thật từ cùng lần encode.

Theo quy ước trace, giá trị phục hồi là stored_integer / 2^31 * 2^exponent.
Phải dùng exponent đúng tầng/subtransform; so sánh trực tiếp mantissa khác thang có thể gây kết luận sai.
Plot xuất cả raw và giá trị MDCT đã phục hồi; không chuẩn hóa peak riêng từng tầng.
04_postprocessing và 05_mdct_output được kiểm tra bằng nhau vì là hai điểm quan sát cùng output transform.

Nếu run thất bại hoặc MDCT_DEBUG=OFF, plotter từ chối coi dump cũ là trace hiện tại.

## Đối chiếu trace không làm thay đổi AAC

Build baseline không có hook:

~~~bash
cmake -S . -B build/mdct_baseline -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DMDCT_DEBUG=OFF -DBUILD_MDCT_TRACE=ON
cmake --build build/mdct_baseline --target fdk_mdct_trace --parallel 4
python my_workspace/window_mdct/tests/mdct_trace/test_mdct_trace.py --binary build/mdct_debug/fdk_mdct_trace --baseline build/mdct_baseline/fdk_mdct_trace
python my_workspace/window_mdct/tests/mdct_trace/test_plot_mdct_stages.py
~~~

Đối số --baseline cần thiết để test byte-identical AAC thực sự được chạy.
CTest mặc định không truyền baseline nên trường hợp đó bị skip; các test khác vẫn chạy.
