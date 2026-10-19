# Trace và phân tích Psy native

Psy theo ranh giới nghiên cứu nhận MDCT spectrum/exponent và window metadata, tạo energy/threshold, quyết định tool và PSY_OUT cho QC.
FDKaacEnc_psyMain() trong FDK còn gọi Block Switching và filterbank trước phần xử lý phổ.
Không diễn giải dump MDCT riêng thành input đầy đủ của một Psy độc lập vì còn cấu hình và lịch sử.

## Các tool

- fdk_psy_trace.cpp: gọi encoder AAC-LC thật; dump qua PSY_DEBUG.
- psy_trace_data.py: đọc JSONL, phục hồi thang số, kiểm tra schema/bounds/SFB và tính hợp lệ.
- analyze_psy_outputs.py: export raw vector và các bảng energy/threshold/tonality/TNS/PNS/output.
- plot_psy_stages.py: vẽ từ trace đã kiểm tra.
- run_psy_analysis.py và run_psy_analysis.sh: build/chạy/export/vẽ, đối chiếu bitstream.

## Build riêng

Từ gốc dự án, các cờ research khác để OFF; dùng thư mục build riêng:

~~~bash
cmake -S . -B build/psy-analysis-debug -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DPSY_DEBUG=ON -DBUILD_PSY_TRACE=ON
cmake --build build/psy-analysis-debug --target fdk_psy_trace --parallel 4
cmake -S . -B build/psy-analysis-normal -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DPSY_DEBUG=OFF -DBUILD_PSY_TRACE=ON
cmake --build build/psy-analysis-normal --target fdk_psy_trace --parallel 4
~~~

Windows thêm .exe; Visual Studio có thể cần Release/ và --config Release.
PSY_DEBUG là quan sát; không bật chung với PSY_EXPERIMENT.

## Chạy với binary đã build

~~~bash
python my_workspace/psychoacoustic_model/tools/run_psy_analysis.py --wav my_workspace/INPUT/data/abc_votay.wav --frames 0:120 --channel 0 --bitrate 32000 --output-dir output/psy_32k --plots-dir plots/psy_32k --binary build/psy-analysis-debug/fdk_psy_trace --normal-binary build/psy-analysis-normal/fdk_psy_trace --skip-build --verify-bitstream --plot-frame 24 --plot-window 3
~~~

--frames START:END có END loại trừ; frame native gồm priming/flush.
--channel all hỗ trợ trace stereo. --stages sfb,energy,masking,tonality,tns,pns chỉ lọc debug.
Không dùng --stages để can thiệp thuật toán.

## Output và thang số

native_trace.jsonl giữ raw integer, fraction_bits, exponent, frame/channel/window và nhãn tầng.
validation.json ghi kiểm tra, survey_manifest.json ghi input/config/source/binary hash và so sánh bitstream.
AAC và các TXT export là dữ liệu của cùng lần encode; plot không thay thế thuật toán native.

Giá trị linear phục hồi: raw * 2^(exponent-fraction_bits).
Dữ liệu ld64 dùng quy ước log của FDK; INT_MIN là zero sentinel.
noiseNrg của PNS là mã integer, không phải năng lượng linear; NO_NOISE_PNS không phải một band được chọn.
SHORT có tám window; không nhầm local SFB với grouped SFB của PSY_OUT.
Tonality estimator bị bỏ qua ở AAC-LC SHORT; plot trống có chú thích không phải lỗi cần bịa thêm dữ liệu.

## Kiểm chứng

~~~bash
python my_workspace/psychoacoustic_model/tests/psy_analysis/test_psy_analysis.py
python my_workspace/psychoacoustic_model/tests/psy_analysis/test_native_psy.py --debug build/psy-analysis-debug/fdk_psy_trace --normal build/psy-analysis-normal/fdk_psy_trace --report output/psy_tests/native_regression.json
~~~

Native regression tạo silence/tone/noise/transient, mono/stereo, 44.1/48 kHz và các bitrate khác nhau.
Nó kiểm tra trace và AAC debug ON/OFF trùng byte, stage selection, frame lỗi, từ chối standalone replay và baseline debug giả.
Gói bàn giao không chứa snapshot source trước khi chèn hook; manifest chỉ chứng minh bản sao khớp workspace hiện tại.
Không dùng điều đó để tuyên bố mọi thay đổi so với upstream đều đã được loại trừ.
