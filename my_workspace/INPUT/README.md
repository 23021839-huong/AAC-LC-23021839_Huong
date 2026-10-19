# Input WAV và công cụ chuẩn bị dữ liệu

## Bộ input bàn giao

Tất cả WAV là PCM16 mono 48 kHz, sao chép nguyên byte từ workspace.
Bộ này chạy offline. Sáu WAV gồm input mặc định của dự án và năm input bên ngoài.

| WAV | Thời lượng | Đặc trưng |
|---|---:|---|
| data/abc_votay.wav | 9,642667 s | Vỗ tay gốc; input mặc định |
| data/psy_external/b01_engine_low.wav | 30 s | Động cơ, âm trầm |
| data/psy_external/b02_birds_high.wav | 30 s | Chim hót, âm cao |
| data/psy_external/b03_bells_tonal.wav | 30 s | Chuông, harmonic và đuôi ngân |
| data/psy_external/b04_clapping.wav | 30 s | Transient vỗ tay |
| data/psy_external/b05_rain_noise.wav | 30 s | Nhiễu mưa liên tục |

manifest.json là chỉ mục sáu WAV: đường dẫn tương đối từ INPUT/, định dạng, số mẫu và SHA-256.
data/psy_external/manifest.json là manifest bộ năm input mà runner suite sẽ sử dụng.
Các giá trị RMS, bước resample/fade/ghép clip và nguồn từng đoạn giữ trong manifest bộ năm input.
abc_votay.wav giữ nguyên mức âm gốc; không giả định cùng RMS với bộ năm input.

## Nguồn dữ liệu

Năm input bên ngoài là montage từ các bản ghi ESC-50/Freesound, đã được xử lý trong workspace trước khi bàn giao.
Nguồn, tác giả và thay đổi dữ liệu: data/psy_external/SOURCES.md và manifest.json cùng thư mục.
Giấy phép đi kèm và commit repository: data/psy_external/source_metadata/.
abc_votay.wav được lấy từ dữ liệu dự án; workspace chưa cung cấp metadata tác giả gốc.
Bản bàn giao giữ WAV xử lý và thông tin nguồn; không cần các bản tải thô hoặc gói ZIP để chạy.

## Chạy encoder

Đứng tại gốc AAC-LC-23021839_Huong; build theo README gốc trước:

~~~bash
cmake -E make_directory output
./build/codec/aac-enc -t 2 -r 64000 -a 1 -d my_workspace/INPUT/data/abc_votay.wav output/abc_votay.aac
~~~

Có thể thay WAV bằng một trong năm file data/psy_external/.
Trên Windows thêm hậu tố .exe; binary của Visual Studio có thể ở build/codec/Release/.

## input_pipeline_ref.cpp

Reference chuẩn bị dữ liệu thời gian:
- 1024 mẫu mới cho mỗi frame Block Switching.
- Buffer 2048 mẫu cho Window/MDCT, giữ lịch sử và padding ban đầu.
- Xuất TXT/RAW, frame_map.csv và meta.txt để kiểm tra ánh xạ mẫu.

Chương trình không thực thi Block Switching hoặc MDCT. Đối chiếu với FDK native sẽ thuộc phần khảo sát tương ứng.

~~~bash
c++ -O2 -std=c++17 my_workspace/INPUT/input_pipeline_ref.cpp -o build/codec/input_pipeline_ref
./build/codec/input_pipeline_ref --wav my_workspace/INPUT/data/abc_votay.wav --out output/input_pipeline --frames 3
~~~

## wav_to_fft_input.py

Cần Python 3.10 trở lên và chỉ dùng thư viện chuẩn.
Tool ghép từng cặp PCM thành phần thực/ảo Q1.23 để tạo stimulus kiểm thử FFT-64/FFT-512.
Đây là stimulus FFT độc lập; không phải dữ liệu pre-FFT bên trong chuỗi MDCT FDK.

~~~bash
python my_workspace/INPUT/wav_to_fft_input.py --wav my_workspace/INPUT/data/abc_votay.wav --output output/input_fft.txt --layout tb-mixed
~~~

Lệnh tạo input_fft.txt, input_fft_map.csv và input_fft_meta.txt.
Layout tb-mixed dành cho testbench FFT hiện tại; default pcm-shift=7 giữ một bit headroom.

## Đọc WAV dùng chung cho các runner native

Xem ../fdk_model_testing/tools/README.md.
wav_pcm.cpp và wav_pcm.h được CMake liên kết vào các runner MDCT, Window, FFT, Psy và Quant ở những phần bàn giao sau.

## Kết quả kiểm chứng phần 2

Sáu WAV khớp SHA-256 với workspace; reader dùng chung khớp toàn bộ mẫu PCM.
Mỗi WAV được kiểm tra 3 frame lịch sử và 11 transform stimulus FFT.
48/48 cấu hình AAC-LC encode/decode đạt trên Windows.

Chương trình test-encode-decode ở gốc chạy cả các AOT ngoài AAC-LC.
Với b05_rain_noise.wav, cấu hình AAC-ELD AOT39 có SBR vượt ngưỡng avg_diff của harness (366 > 300), nên chương trình nhiều profile trả exit code 1.
Đã tái hiện riêng trường hợp này; source và ngưỡng kiểm tra được giữ nguyên.
Chi tiết nằm trong CHANGES_RESEARCH.md ở gốc. Chưa thực thi trên Linux.