# Khảo sát chính sách window

## Mục đích và điểm can thiệp

Giữ nguyên thuật toán block switching chọn sequence, thay shape theo policy tường minh rồi encode/decode AAC-LC native.
Hook nằm trong libAACenc/src/block_switch/window_experiment.cpp và được biên dịch khi WINDOW_EXPERIMENT=ON.
FDKwindowExperimentShape(sequence, native_shape) trả shape theo bảng; DEFAULT trả native_shape.
Observer ghi sequence, shape, shape trước đó và sườn trái/phải thực sự được dùng.

Mã sequence: LONG=0, START=1, SHORT=2, STOP=3.
Mã shape: SINE=0, KBD=1.

| ID | Mode | LONG | START | SHORT | STOP |
|---|---|---|---|---|---|
| EXP01 | SINE_ONLY | SINE | SINE | SINE | SINE |
| EXP02 | KBD_ONLY | KBD | KBD | KBD | KBD |
| EXP03 | SINE_LONG_KBD_SHORT | SINE | SINE | KBD | SINE |
| EXP04 | KBD_LONG_SINE_SHORT | KBD | KBD | SINE | KBD |

Đây là bốn chính sách khảo sát. Kết quả của chúng không tự chứng minh chính sách nào tối ưu cho mọi âm thanh.
DEFAULT trong source bàn giao bị ảnh hưởng bởi lỗi bảng đã ghi ở phần Block Switching; không gộp DEFAULT với EXP04.

## Quy trình chạy

~~~text
WAV cố định + policy
        |
        v
[Encoder AAC-LC native] -> AAC + trace sequence/shape + thời gian
        |                         |
        v                         v
[Decoder FDK]              [Đọc ICS trong ADTS]
        |                         |
        v                         v
[Căn trễ PCM, giữ đủ mẫu]   [Xác nhận shape thật]
        |                         |
        +------------+------------+
                     v
 [MSE / SNR / NRMSE / bitrate / size / mean, SD thời gian]
                     |
                     v
           [CSV + trạng thái + plots]
~~~

Mỗi policy có một lượt warmup, sau đó ít nhất năm lần encode để đo thời gian.
Script kiểm tra sequence giống nhau giữa bốn mode; kiểm tra trace khớp policy, lịch sử sườn trái và shape trong bitstream.
Mỗi run dùng trạng thái encoder mới. AAC/PCM lấy từ các phép encode/decode native; Python chỉ điều phối, đọc bitstream và đo.

## Lệnh chạy

Từ gốc dự án, sau khi build theo README:

~~~bash
python my_workspace/window_mdct/experiments/scripts/run_window_experiments.py --input my_workspace/INPUT/data/abc_votay.wav --binary build/window/fdk_window_experiment --output-dir output/window_experiments --runs 5
~~~

Thay --input bằng WAV trong my_workspace/INPUT/data/psy_external/ để khảo sát thêm.
Luôn truyền --binary; Windows dùng đường dẫn .exe tương ứng.
Native runner cũng chạy riêng được:

~~~bash
./build/window/fdk_window_experiment --input my_workspace/INPUT/data/abc_votay.wav --output-dir output/window_default --mode DEFAULT --runs 5
~~~

## Cách đo và giới hạn

measure_distortion.py đọc PCM thành float64 theo full scale trước khi trừ/bình phương.
Tìm delay bằng tương quan quanh tổng delay encoder/decoder, sau đó so sánh toàn bộ N mẫu/kênh đầu vào.
Không chỉnh gain hoặc resample. Alignment yếu/không rõ, WAV thiếu đuôi hay bitstream không hợp lệ làm run báo error; không xuất metric giả.

- MSE = sum((x-y)^2) / tổng số mẫu scalar; đơn vị full-scale squared.
- SNR = 10 log10(sum(x^2) / sum((x-y)^2)), dB.
- NRMSE = 100 sqrt(sum((x-y)^2) / sum(x^2)), %.
- Bitrate ADTS được tính từ kích thước và thời lượng mã hóa; CSV có bitrate tính theo thời lượng source và thông tin overhead.
- Thời gian mean/SD là phép đo trên máy đang chạy; không đại diện cho số chu kỳ phần cứng.

SNR đo độ gần PCM sau căn trễ, không thay thế đánh giá cảm nhận.
Các chỉ số có thể chưa xác định với tín hiệu im lặng hoặc căn trễ mơ hồ; script ghi rõ thay vì ép thành số hợp lệ.
Bài đọc ICS hiện hỗ trợ mono và stereo có common_window=1; không phải parser AAC tổng quát.

## Output được tạo khi chạy

- encoded/: bốn AAC.
- decoded/: bốn WAV giải mã.
- logs/: trace native, ICS trace, metadata, alignment và process log.
- runs/: dữ liệu làm việc từng lượt/chế độ.
- results/window_comparison.csv: một hàng/policy với metric và status.
- results/window_runs.csv: thời gian từng lần encode.
- results/pipeline_status.json: trạng thái hoàn thành.
- results/: các biểu đồ bitrate, thời gian, distortion, kích thước và tổng quan.

Các output này không được chép vào source bàn giao.

## Kiểm chứng

~~~bash
ctest --test-dir build/window --output-on-failure
~~~

Ba nhóm: window_native_integration, window_measurement_units, window_pipeline_integration.
Nếu CMake tìm nhầm Python, configure lại với -DWINDOW_EXPERIMENT_PYTHON=/duong/dan/python.
Nhóm MDCT tương tự dùng -DMDCT_TRACE_PYTHON=/duong/dan/python.
