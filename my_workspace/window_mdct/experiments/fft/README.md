# FFT gốc và radix-2 trong encoder AAC-LC

Bộ khảo sát dùng encoder/decoder FDK thật. Hai mode ORIGINAL_FFT và RADIX2_ONLY thay kernel FFT trong forward MDCT; cùng WAV, AAC-LC 64 kb/s, Afterburner và SINE_ONLY.
Giữ window cố định để tách ảnh hưởng FFT khỏi policy chọn shape.
Native DEFAULT của snapshot vẫn có lỗi bảng Block Switching đã ghi ở phần 3; không dùng DEFAULT làm chuẩn LC upstream.

## Thành phần

- tools/validate_fft.cpp: so sánh kernel, exponent và DFT độc lập trên N=64/512, gồm PRE lấy từ encoder.
- tools/fdk_fft_experiment.cpp: encode/decode, trace và profiling native.
- scripts/run_fft_experiments.py: điều phối build, validation gate, benchmark, phép đo và xuất kết quả.
- scripts/measure_distortion.py: dùng lại phép đo của phần Window.
- scripts/plot_fft_results.py: vẽ CSV đo được.
- ../../tests/fft_experiments/: kiểm tra kernel, codec, pipeline và các đường lỗi.

Hook/runtime FFT đã có trong libFDK/ từ phần 1. Source của phần này được sao chép nguyên byte.
Không mang theo kết quả cũ, patch baseline, ZIP, binary hoặc cache.

## Chạy toàn bộ

Từ gốc AAC-LC-23021839_Huong, cần CMake, Ninja, compiler C++17, Python và requirements.txt:

~~~bash
python -m pip install -r requirements.txt
python my_workspace/window_mdct/experiments/fft/scripts/run_fft_experiments.py --input my_workspace/INPUT/data/abc_votay.wav --output-dir output/fft_experiments --build-dir build/fft_experiments --bitrate 64000 --runs 10
~~~

Script tự build FFT runner và một MDCT trace build riêng để lấy PRE thật.
Input cần tạo được SHORT để thu PRE cho tám FFT64. Nếu input không có SHORT, truyền cả --pre-long và --pre-short từ trace native hợp lệ.
Không dùng FFT NumPy trong encoder. NumPy dùng cho alignment, metric và biểu đồ.

Mỗi mode có benchmark encode không profiling và các lượt profiling riêng.
Validation fail thì không benchmark AAC. Hai output giống byte là kết quả có thể xảy ra khi radix-2 giữ đúng lịch truncation/scaling của FFT gốc.
Không suy luận tốc độ từ hai bản build khác chế độ tối ưu hay từ thời gian có chèn profiling.

## Build và test riêng

~~~bash
cmake -S . -B build/fft_experiments -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DFFT_EXPERIMENT=ON -DWINDOW_EXPERIMENT=ON -DBUILD_TESTING=ON
cmake --build build/fft_experiments --target fdk_fft_validate fdk_fft_experiment fdk_window_experiment --parallel 4
~~~

Các test cũ dùng hai đường dẫn PRE mặc định. Tạo chúng bằng runner phần 4 trước khi chạy CTest:

~~~bash
./build/mdct_debug/fdk_mdct_trace --input my_workspace/INPUT/data/abc_votay.wav --output-dir my_workspace/window_mdct/output --frame auto --channel 0
./build/mdct_debug/fdk_mdct_trace --input my_workspace/INPUT/data/abc_votay.wav --output-dir my_workspace/window_mdct/output/mdct_short_example --frame 24 --channel 0
ctest --test-dir build/fft_experiments --output-on-failure
~~~

Frame 24 là SHORT của abc_votay.wav trong snapshot này; kiểm tra stage_metadata.json khi đổi input.
CTests gồm hai nhóm FFT và ba nhóm Window do FFT_EXPERIMENT cần WINDOW_EXPERIMENT.
Nếu CMake tìm nhầm Python, truyền -DFFT_EXPERIMENT_PYTHON=/duong/dan/python và -DWINDOW_EXPERIMENT_PYTHON=/duong/dan/python.
Windows thêm .exe vào binary; Visual Studio có thể cần Release/.

## Kết quả và giới hạn

Output có encoded/, decoded/, logs/, runs/, results/ và plots/.
results/fft_validation.json ghi validation; fft_window_comparison.csv ghi metric; fft_runs.csv và fft_profile.csv tách timing benchmark/profiling.
Xem ../../docs/part5_verification.md để biết kết quả vừa chạy và phần chưa thực thi.
