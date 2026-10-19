# FFT radix-2 fixed-point cho MDCT AAC-LC

Profile FDK_AACLC_1024_Q31Q15_RAD2_V1: FFT forward exp(-j*2*pi*k*n/N), N=64 hoặc 512.
Data signed Q1.31, hệ số signed Q1.15, dịch phải số học và wrap 32 bit.
Scale mask 101111 cho FFT64 và 101111111 cho FFT512; exponent tăng 5 hoặc 8.
Input/output theo thứ tự tự nhiên.

## Cấu trúc

- rtl/: package, controller, address generator, ping-pong memory, twiddle ROM, butterfly và fft_radix2_core.
- ref/: model Python integer, reference C++, bảng twiddle và các comparator.
- tb/tb_fft_radix2_core.vhd: so sánh output, từng stage, exponent và handshake trên chuỗi FFT64/512.
- tools/: sinh vector/ROM, đối chiếu với port dit_fft và vẽ kết quả.
- docs/fft_radix2_core.md: tài liệu kỹ thuật được giữ từ workspace; trạng thái kiểm chứng hiện tại xem ../docs/part5_verification.md.

RTL nạp mẫu qua ld_en/ld_idx/ld_re/ld_im khi load_ready; start bắt đầu biến đổi.
done là xung một chu kỳ. Đọc kết quả bằng rd_en/rd_idx và lấy mẫu khi rd_valid.
size_mode=0 cho 64, =1 cho 512.

## Kiểm tra model và tạo dữ liệu

Từ gốc dự án:

~~~bash
python my_workspace/window_mdct/fft_radix2_core/tools/verify_fdk_equivalence.py --trials 32
python my_workspace/window_mdct/fft_radix2_core/tools/gen_fft_vectors.py --output-dir my_workspace/window_mdct/fft_radix2_core/vectors
c++ -std=c++17 -O2 my_workspace/window_mdct/fft_radix2_core/ref/fft_radix2_ref.cpp -o build/fft_radix2_ref
./build/fft_radix2_ref --input my_workspace/window_mdct/fft_radix2_core/vectors/input_fft.txt
~~~

Tạo build/ trước khi compile. Vector được sinh khi chạy, không có sẵn trong bản bàn giao.
Tool gen_fdk_twiddle.py tái tạo ROM/header ngay trong source tree; chỉ dùng khi chủ động cập nhật bảng, không phải bước bắt buộc để build.

## Mô phỏng FFT riêng

GHDL phải có trên PATH. Chạy từ thư mục fft_radix2_core vì testbench dùng vectors/... tương đối:

~~~bash
cd my_workspace/window_mdct/fft_radix2_core
ghdl -a --std=08 -frelaxed-rules rtl/fft_radix2_pkg.vhd rtl/fft_radix2_twiddle_rom.vhd rtl/fft_radix2_addr_gen.vhd rtl/fft_radix2_memory.vhd rtl/fft_radix2_butterfly.vhd rtl/fft_radix2_control.vhd rtl/fft_radix2_core.vhd tb/tb_fft_radix2_core.vhd
ghdl -r --std=08 -frelaxed-rules tb_fft_radix2_core --assert-level=error
~~~

RTL FFT còn được dùng trong bộ mô phỏng MDCT/AXI; xem ../docs/rtl_workflow.md.
