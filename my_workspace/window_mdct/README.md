# Window/MDCT trong AAC-LC

Phần 4 của bản bàn giao: quan sát pipeline native và khảo sát bốn chính sách window.
Các source/tool/test được sao chép nguyên byte từ workspace nghiên cứu.
Kết quả chạy, binary, cache và môi trường Python không nằm trong thư mục này.

## Cấu trúc

~~~text
window_mdct/
  README.md
  tools/
    fdk_mdct_trace.cpp
    plot_mdct_stages.py
  experiments/
    tools/fdk_window_experiment.cpp
    scripts/
      run_window_experiments.py
      measure_distortion.py
      plot_results.py
  tests/
    mdct_trace/
      test_mdct_trace.py
      test_plot_mdct_stages.py
    window_experiments/
      test_native_window.py
      test_measurements.py
      test_pipeline.py
  docs/
    native_pipeline.md
    window_experiments.md
    verification.md
~~~

- tools/: runner gọi encoder FDK để lấy các tầng Window/Fold, pre-processing, FFT, post-processing và MDCT; Python đọc trace và vẽ.
- experiments/: encode/decode thực với bốn policy SINE/KBD; đọc ICS trong ADTS, đo bitrate, thời gian, kích thước và sai số PCM sau căn trễ.
- tests/: kiểm tra trace, fixed-point/exponent, mono/stereo, policy trong bitstream, phép đo và xử lý run thất bại.
- docs/: nguyên lý, lệnh chạy và kết quả kiểm chứng thực tế.

Source DSP nằm trong libAACenc/src/filterbank/ và libFDK/ ở gốc dự án.
Header/hook nghiên cứu đã được chuyển cùng codec ở phần 1; CMake gốc được giữ nguyên.
Thư mục này chứa bộ khảo sát phần mềm. Phần 5 đã bổ sung bộ thí nghiệm FFT, FFT/MDCT RTL, testbench, reference, driver và flow PYNQ.

## Điều kiện chạy

Chạy các lệnh dưới đây từ gốc AAC-LC-23021839_Huong.
Cần CMake, compiler C++17, Python 3.10+ và các package trong requirements.txt:

~~~bash
python -m pip install -r requirements.txt
~~~

Các ví dụ dùng đường dẫn binary kiểu Ninja/Makefiles trên Linux.
Trên Windows thêm .exe; với Visual Studio có thể cần thêm Release/ và --config Release.
Luôn truyền --binary cho script thí nghiệm vì giá trị mặc định của script cũ có hậu tố .exe.
Luôn truyền thư mục output để kết quả không trộn vào source/tool.

## Quan sát MDCT native

~~~bash
cmake -S . -B build/mdct_debug -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DMDCT_DEBUG=ON -DBUILD_MDCT_TRACE=ON -DBUILD_TESTING=ON
cmake --build build/mdct_debug --target fdk_mdct_trace --parallel 4
./build/mdct_debug/fdk_mdct_trace --input my_workspace/INPUT/data/abc_votay.wav --output-dir output/mdct_trace --frame auto --channel 0
python my_workspace/window_mdct/tools/plot_mdct_stages.py --data-dir output/mdct_trace --plot-dir output/mdct_trace/plots
~~~

--frame đếm frame transform native từ 0, có priming/flush; --frame auto chọn snapshot có RMS PCM lớn nhất.
Xem docs/native_pipeline.md về kích thước, exponent và ý nghĩa dữ liệu.

## Thí nghiệm window

~~~bash
cmake -S . -B build/window -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DWINDOW_EXPERIMENT=ON -DBUILD_TESTING=ON
cmake --build build/window --target fdk_window_experiment --parallel 4
python my_workspace/window_mdct/experiments/scripts/run_window_experiments.py --input my_workspace/INPUT/data/abc_votay.wav --binary build/window/fdk_window_experiment --output-dir output/window_experiments --runs 5
~~~

Dùng build directory riêng cho MDCT_DEBUG, WINDOW_EXPERIMENT và baseline; các cờ nghiên cứu khác để OFF.
Xem docs/window_experiments.md về các mode, metric và kiểm chứng bitstream.

## Lỗi source đã biết

blockType2windowShape trong libAACenc/src/block_switch/block_switch.cpp thiếu hàng LD.
Native DEFAULT của snapshot này vì vậy chọn SINE cho AAC-LC; không được mô tả nó là policy LC của FDK 2.0.3 gốc.
Người dùng đã chọn giữ nguyên source và ghi nhận bài Block Switching DUT-REF FAIL.
Bốn mode thí nghiệm đặt policy tường minh; EXP04 KBD_LONG_SINE_SHORT không đồng nghĩa DEFAULT hiện tại.
Xem ../block_switch/docs/verification.md và docs/verification.md.

## Phần 5 đã bổ sung

- experiments/fft/: hai runner C++, ba script và README so sánh FFT trong encoder.
- fft_radix2_core/: 7 RTL, reference C++/Python, testbench, generator/comparator và tài liệu.
- rtl/: 12 RTL Window/Fold, pre/post, control, ROM/RAM và mdct_core.
- ref/: model MDCT C++/Python.
- tb/: testbench MDCT/AXI, generator C++ và harness đối chiếu FDK.
- board/pynq_z2/, sw/, synth/: AXI wrapper, driver và flow Vivado.
- tools/: thêm generator vector/ROM, comparator, runner mô phỏng và packager.
- tests/fft_experiments/, tests/test_bringup.py: test FFT và host driver/package.

Xem experiments/fft/README.md, fft_radix2_core/README.md, docs/rtl_workflow.md và docs/pynq_z2_bringup.md.
Trạng thái thực thi và phần chưa kiểm chứng: docs/part5_verification.md.
