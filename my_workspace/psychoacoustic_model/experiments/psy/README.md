# Khảo sát Tonality/TNS và quan sát PNS

## Các mode hiện có

| Mode | Tonality | TNS |
|---|---:|---:|
| PSY_TONALITY_ON_TNS_ON | ON | ON |
| PSY_TONALITY_ON_TNS_OFF | ON | OFF |
| PSY_TONALITY_OFF_TNS_ON | OFF | ON |
| PSY_TONALITY_OFF_TNS_OFF | OFF | OFF |

BASELINE giữ điều kiện native. Script đối chiếu bản không biên dịch controls với native-default của bản research trước khi đo.
Window/MDCT được kiểm hash từng frame/channel; FFT, bitrate, Afterburner và các cấu hình khác cố định.

Tonality ON điều khiển thực thi estimator ở nhánh được hỗ trợ, kể cả khi native PNS tắt; output estimator có thể không được dùng phía sau.
PNS được giữ đúng baseline. Khi native PNS bật, các case OFF không được phép tách phụ thuộc sẽ báo UNSUPPORTED.
Không tự tắt PNS hoặc tạo tonality thay thế để ép đủ bốn case.
--expected-pns chỉ assert trạng thái, chưa phải công tắc PNS độc lập.

## Chạy bốn case

Từ gốc dự án:

~~~bash
python -m pip install -r my_workspace/psychoacoustic_model/requirements.txt
python my_workspace/psychoacoustic_model/experiments/psy/scripts/run_psy_experiments.py --input my_workspace/INPUT/data/abc_votay.wav --output-dir output/psy_experiments --runs 10 --profile-runs 10
~~~

Tool tự build hai cấu hình Release/static: build/psy-experiments và build/psy-experiments-baseline.
PSY_EXPERIMENT=ON chỉ dùng cho bản research; baseline OFF nhưng BUILD_PSY_EXPERIMENT=ON để có cùng runner.
Mọi cờ PSY_DEBUG, QUANT_DEBUG, MDCT_DEBUG, WINDOW_EXPERIMENT, FFT_EXPERIMENT và encoder profiling chung phải OFF.

Có thể truyền --build-dir, --baseline-build-dir và --skip-build khi đã build.
Không dùng lại cache của thí nghiệm Window/FFT/trace.

## Chạy năm WAV ngoài đã bàn giao

~~~bash
python my_workspace/psychoacoustic_model/experiments/psy/scripts/run_psy_extended_suite.py --manifest my_workspace/INPUT/data/psy_external/manifest.json --output-dir output/psy_external --runs 10 --profile-runs 10
~~~

Runner extended chấp nhận 1..20 PCM16 mono 48 kHz, 10..300 s và kiểm SHA-256/metadata trước khi chạy.
Năm WAV hiện có đều 30 s. --input-ids chọn tập con; --validate-only chỉ kiểm input.
run_psy_input_suite.py là runner cũ giới hạn đúng năm input; luôn truyền --manifest vì dữ liệu được tập trung lại ở INPUT.

## Cách đánh giá

Benchmark chính đo aacEncEncode() với encoder mới, không gồm decode/I/O/trace/stage clock.
Profiling chạy riêng. Đọc encoder_tns_filters và decoder_tns_filters để xác nhận TNS thực sự được dùng.
Phép đo căn trễ, giữ đủ mẫu, không đổi gain hoặc resample:
MSE theo full-scale squared; SNR=10log10(signal_energy/error_energy);
NRMSE%=100sqrt(error_energy/signal_energy).

Output gồm encoded/, decoded/, logs/, runs/, results/, plots/.
CSV có status PASS/ERROR/UNSUPPORTED; metric không hợp lệ được để trống.
So SHA-256/byte AAC cùng số liệu trace trước khi kết luận tool không có tác động.
SNR hoặc một input chưa đủ kết luận chất lượng cảm nhận hay nên bỏ một tool.

## Chuẩn bị input mới

~~~bash
python -m pip install -r my_workspace/psychoacoustic_model/requirements-inputs.txt
python my_workspace/psychoacoustic_model/experiments/psy/scripts/prepare_psy_inputs.py --source my_workspace/INPUT/data/abc_votay.wav --output-dir output/input_synthetic
python my_workspace/psychoacoustic_model/experiments/psy/scripts/prepare_external_psy_inputs.py --output-dir output/input_external
python my_workspace/psychoacoustic_model/experiments/psy/scripts/prepare_extended_psy_inputs.py --output-dir output/input_extended
~~~

Hai tool external tải bản ghi bên ngoài, lưu manifest/metadata/nguồn/giấy phép.
Tool extended chuẩn bị 15 input 10..300 s; dùng metadata input/psy_external/manifest.json để loại source ID đã dùng trong năm WAV trước.
Các dữ liệu tải mới, ZIP và WAV sinh ra chỉ xuất hiện khi chủ động chạy tool; không có sẵn trong gói source.

## Test

Sau khi các binary mặc định đã build:

~~~bash
python my_workspace/psychoacoustic_model/tests/psy_experiments/test_native.py --binary build/psy-experiments/fdk_psy_experiment --baseline build/psy-experiments-baseline/fdk_psy_experiment
python my_workspace/psychoacoustic_model/tests/psy_experiments/test_measurements.py
python my_workspace/psychoacoustic_model/tests/psy_experiments/test_publication.py
python my_workspace/psychoacoustic_model/tests/psy_experiments/test_input_signals.py
python my_workspace/psychoacoustic_model/tests/psy_experiments/test_extended_inputs.py
~~~

Windows thêm .exe. Hai test input cần requirements-inputs.txt.
Xem ../../docs/part6_verification.md về kết quả thực tế, platform và giới hạn.
