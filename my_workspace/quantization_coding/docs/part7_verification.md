# Kiểm chứng phần 7: Quantization/Coding

Ngày 2026-10-19. Windows, GCC 16.1.0, CMake 4.3.2, Ninja 1.13.2; Python 3.12.13, NumPy 2.5.4, Matplotlib 3.11.2.
Native runner C++17; reference C++20.

## Build và sửa đường dẫn đóng gói

Build Release/static đạt cho Quant debug, Quant normal và encoder profiler.
Reference CMake build đạt cả quantization_ref_cli và fdk_quant_harness.

Đã tái hiện ba lỗi trên staging trước sửa: CMake trỏ source flat không tồn tại, regression gọi sai generator, extractor tìm ROM ở đường dẫn flat.
Bốn file được sửa tối thiểu:
- quantization_reference/cpp_ref/CMakeLists.txt: quantization/quantize.cpp và common/aacEnc_rom.cpp.
- quantization_reference/verification/run_regression.py: generator ở tools/generate_test_vectors.py.
- quantization_reference/tools/extract_fdk_tables.py: ROM ở common/aacEnc_rom.cpp.
- my_workspace/pynq_z2/sw/scripts/run_qc_step0.sh: ROM path và bỏ Makefile.am không có trong gói export khỏi danh sách inventory.

Source gốc trong workspace không bị sửa. Mã codec/model arithmetic giữ nguyên.
Hash trước/sau và các replacement có trong packaging_changes.json; manifest tách adapted_files khỏi copied_files.

## Test

| Nhóm | Kết quả |
|---|---|
| Native Quant integration | 10/10 PASS |
| Parser/export/plot/Psy-audit/CLI | 18/18 PASS |
| Reference model units | 5/5 PASS |

Tổng 33/33 ca khác nhau đạt, không skip.
Harness cần đường output cố định được chạy trên runtime snapshot riêng với trace mới sinh.
Native tests kiểm tra debug invariance, mono/stereo, 44.1/48 kHz, stage/iteration/line selection, writer TNS compression và decoder acceptance.

## Cross-model và ROM

Sinh mới zero_long, smoke_long, grouped_short_deadzone.
C++ và native FDKaacEnc_QuantizeSpectrum đều khớp Python fixed: 0 mismatch ở cả ba case.
Hình học gồm tổng 288 spectral slots; active mask và max magnitude/SFB là dữ liệu kiểm tra đi kèm.
Float cũng có 0 mismatch trên ba case này; không suy rộng rằng float luôn bit-exact.
Native harness không xuất intermediate trace từng phép toán, nên không công bố bit-exact mọi intermediate của native kernel.
Hai file bảng ROM tái sinh trong staging khớp byte với bảng bàn giao.

## WAV thật và audit Psy -> QC

abc_votay.wav: mono PCM16, 48 kHz, 462848 mẫu; AAC-LC 64 kb/s, Afterburner ON.
Trace frame [10,26), channel 0:
- 16 frame/channel, 36738 record, validation valid=true.
- 614 native-max checks.
- Audit Psy/QC khớp 21624 giá trị raw và xác nhận hash trace Psy.
- Chỉ các trường được liệt kê trong checked_fields được xác nhận; common_window mono và writer-only tns_coef_compress có giới hạn producer như manifest ghi.
- 454 ADTS packet, 454 packet decode-check đạt.
- Debug có trace, cùng debug binary không ghi trace, normal không debug: AAC trùng toàn bộ byte.
- Profiler build cũng tạo cùng AAC.
- AAC 77823 byte, SHA-256 777a613968fd9073981bda80aa3fa66b57e3a8c92c32a6749b3ea74dbf29ebc1.
- Đã sinh 15 PNG và xem quantization_overview.png.

Reference spectral kernel chưa phải standalone port toàn bộ QC/rate control/Huffman; audit không phải full-state replay.

## Profiling và gate

Native profiler Windows xuất encoder_profile.csv, profile_frames.csv, profile_band_trials.csv.
Có 18614 dòng per-frame event, 454 frame_total/454 frame khác nhau, 17333 dòng per-band trial.
Đây là smoke instrumentation trên host; không công bố số đo Cortex-A9 hoặc PL.

generate_corpus.py tạo tám WAV 1 s để smoke; cả tám đúng mono PCM16/48 kHz/48000 mẫu.
Bash syntax của run_quant_analysis.sh và run_qc_step0.sh đạt.
analyze_step0.py trên artifact rỗng giữ status=PENDING, các gate thiếu chứng cứ đều false.
Chưa đóng gate Step-0, chưa chạy campaign Linux/ARM, DMA, Vivado/timing hay FPGA.
Chưa có RTL/QMAX hoặc AXI wrapper Quantization/Coding riêng trong source được bàn giao.
Runner board yêu cầu Git checkout hợp lệ và các công cụ Linux được ghi trong profiling/README.md.

## Lỗi và phạm vi vẫn bảo lưu

Block Switching DUT-REF phần 3 vẫn FAIL do bảng window shape thiếu hàng LD, giữ nguyên theo lựa chọn người dùng.
Các PASS ở đây không phủ nhận lỗi đó hoặc chứng minh snapshot là upstream sạch.
Bản bàn giao không có output/cache/binary/vector cũ; WAV dùng chung tại INPUT.

Bằng chứng phát triển nằm ngoài gói:
fdk-aac/build/teacher_review/AAC-LC-23021839_Huong_stage7/
Gồm debug/, normal/, profile/, reference/, runtime_source/, path_probe/, quant_plots/, host_profile/, profile_corpus_smoke/, empty_step0/ và log.
