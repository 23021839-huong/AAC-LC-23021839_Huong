# Trace QC/Coding và audit Psy -> QC

## Dữ liệu quan sát

Input gồm PSY_OUT spectrum/exponent, năng lượng/threshold/minSNR theo grouped SFB, cấu hình và trạng thái rate control.
Các tầng quan sát: form factor, PE, bit allocation, threshold adjustment, scalefactor, global gain, quantization, rate iterations và final coding.
Output cuối của encoder là AAC; vector trace chỉ là checkpoint quan sát, không tự chứa toàn bộ state để replay QC độc lập.

## Build riêng

~~~bash
cmake -S . -B build/quant-analysis-debug -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DQUANT_DEBUG=ON -DBUILD_QUANT_TRACE=ON -DPSY_DEBUG=OFF -DMDCT_DEBUG=OFF
cmake --build build/quant-analysis-debug --target fdk_quant_trace --parallel 4
cmake -S . -B build/quant-analysis-normal -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DQUANT_DEBUG=OFF -DBUILD_QUANT_TRACE=ON -DPSY_DEBUG=OFF -DMDCT_DEBUG=OFF
cmake --build build/quant-analysis-normal --target fdk_quant_trace --parallel 4
~~~

Dùng build directory riêng, các cờ experiment/profiling khác OFF.
Windows thêm .exe; Visual Studio có thể cần Release/ và --config Release.

## Chạy và đối chiếu AAC

~~~bash
python my_workspace/quantization_coding/tools/run_quant_analysis.py --wav my_workspace/INPUT/data/abc_votay.wav --frames 10:26 --bitrate 64000 --binary build/quant-analysis-debug/fdk_quant_trace --normal-binary build/quant-analysis-normal/fdk_quant_trace --skip-build --verify-bitstream --output-dir output/quant --plots-dir plots/quant --plot-frame 10
~~~

--verify-bitstream so ba AAC: QUANT_DEBUG=ON có trace, cùng binary --no-trace, và baseline QUANT_DEBUG=OFF; đồng thời decode-check packet.
--frames START:END có END loại trừ; đếm frame native gồm priming/flush.
--stages chỉ chọn payload debug. --no-iteration-log giảm dữ liệu trial; --line-trace ghi từng line khi cần.
Các tùy chọn này không phải thay thuật toán quantization.

Output gồm native_trace.jsonl, validation.json, survey_manifest.json, summary và các TXT/vector theo frame/channel.
Plot gồm 15 PNG cho form factor, PE, reservoir, threshold, scalefactor, gain/rate iterations và quantized spectrum.
Luôn chọn output/plots mới. --overwrite chỉ áp dụng campaign Quant có marker và bảo toàn bản trước trong thư mục .previous-*.

## Audit raw interface Psy/QC

Sinh Psy với cùng WAV/config/range trước:

~~~bash
python my_workspace/psychoacoustic_model/tools/run_psy_analysis.py --wav my_workspace/INPUT/data/abc_votay.wav --frames 10:26 --bitrate 64000 --output-dir output/psy_for_qc --plots-dir plots/psy_for_qc --verify-bitstream --no-plots
python my_workspace/quantization_coding/tools/run_quant_analysis.py --wav my_workspace/INPUT/data/abc_votay.wav --input output/psy_for_qc --frames 10:26 --bitrate 64000 --output-dir output/quant_audit --plots-dir plots/quant_audit --verify-bitstream
~~~

Audit kiểm WAV/config/hash, grouped geometry và raw values trong native valid mask.
Các trường unavailable được liệt kê riêng; mono common_window và writer-only tns_coef_compress không có producer Psy tương ứng.
Không gọi đây là full-state checkpoint hoặc standalone replay.

## Cách đọc số

Dùng fraction_bits/exponent/unit/bit_width/valid_indices của từng record.
Không so mantissa khác thang, không coi padding chưa khởi tạo là zero native, không bỏ quy ước half-scale của inverse quantization.
Tách loop_kind/phase/iteration/candidate để không gộp scalefactor search với rate loop.
PE là đại lượng phân bổ cảm nhận; dynamic bit cost, syntax và ADTS overhead là các thành phần khác nhau.

## Test với dữ liệu mới sinh

Hai harness Quant cần trace ở đường mặc định. Từ gốc dự án, tạo Psy và Quant với --frames 10:26 tại:
my_workspace/psychoacoustic_model/output/psy và my_workspace/quantization_coding/output/quant.
Dùng cùng bitrate 64000 và cùng WAV; không đưa kết quả cũ vào thư mục này.

~~~bash
python my_workspace/quantization_coding/tests/quant_analysis/test_native_quant.py --debug build/quant-analysis-debug/fdk_quant_trace --normal build/quant-analysis-normal/fdk_quant_trace
python my_workspace/quantization_coding/tests/quant_analysis/test_quant_analysis.py
~~~

Native test còn ghi signal_matrix.json dưới output/quant_validation.
Lần bàn giao chạy các harness trong runtime snapshot riêng để source bàn giao sạch.
