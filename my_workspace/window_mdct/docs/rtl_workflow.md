# Chạy lại reference và RTL Window/MDCT

## Phạm vi source

- rtl/: 12 file MDCT gồm window/fold, pre/post DCT-IV, control, ROM và RAM.
- fft_radix2_core/rtl/: 7 file FFT phụ thuộc.
- ref/: C++ và Python fixed-point model.
- tb/: testbench core/AXI, generator C++ và harness đối chiếu mdct_block().
- tools/: sinh vector/ROM, mô phỏng, đối chiếu float và đóng gói board.
- board/pynq_z2/: AXI4-Lite wrapper và constraint.
- sw/, synth/: driver và flow Vivado.

Input MDCT: snapshot 2048 PCM signed16, block type LONG/START/SHORT/STOP, right shape SINE/KBD, trạng thái trái.
Output: 1024 hệ số Q31, exponent 12 cho LONG/START/STOP hoặc 9 cho SHORT.
SHORT gồm tám FFT64; các loại khác một FFT512.
Bộ RTL này nhận type/shape từ bên ngoài; chưa ghép RTL Block Switching vào top.

Tài liệu thiết kế và reference gốc được giữ ở window_mdct_design_spec.md và window_mdct_reference_model.md.
Chúng mô tả profile kỹ thuật; trạng thái test hiện tại chỉ lấy từ part5_verification.md.

## Sinh dữ liệu kiểm chứng

Từ gốc dự án:

~~~bash
python my_workspace/window_mdct/tools/gen_mdct_vectors.py --suite baseline
python my_workspace/window_mdct/sw/run_mdct_board.py --validate-only
~~~

Tool parse bảng literal trong libFDK/src/FDK_tools_rom.cpp và tính golden bằng integer model.
NumPy float64 là phép đối chiếu riêng, không dùng để tạo giá trị hex bit-exact.
Baseline gồm 18 frame; --suite extended tạo bộ stress 100 frame ở thư mục build/golden riêng.
Golden là dữ liệu test được sinh lúc chạy; không được sao chép từ output cũ vào gói bàn giao.

## Mô phỏng core và AXI

~~~bash
python my_workspace/window_mdct/tools/run_bringup_sim.py --ghdl ghdl --build-dir build/rtl_bringup
~~~

Runner dùng golden mặc định my_workspace/window_mdct/golden/radix2_q31_v1, cần sinh trước.
Thứ tự compile: hai package -> FFT -> MDCT -> AXI wrapper -> hai testbench.
Dùng VHDL-2008 và -frelaxed-rules cho template RAM shared variable.
Testbench core kiểm tra fold/pre/từng stage FFT/post/output; testbench AXI kiểm tra đường điều khiển và đọc/ghi.

## Kiểm tra driver trên host

Linux, từ gốc dự án:

~~~bash
PYTHONPATH=my_workspace/window_mdct/tools python my_workspace/window_mdct/tests/test_bringup.py
~~~

PowerShell:

~~~powershell
$env:PYTHONPATH=(Resolve-Path my_workspace/window_mdct/tools).Path
python my_workspace/window_mdct/tests/test_bringup.py
~~~

PYTHONPATH bổ sung đường import tools cho harness được giữ nguyên từ workspace.
Các ca FakeMMIO kiểm tra driver/protocol và xử lý lỗi; chúng không lập trình FPGA hoặc chứng minh phần cứng chạy đúng.

## Reference C++ và FDK

tb/gen_mdct_golden.cpp có lệnh build trong phần comment đầu file.
tb/verify_mdct_fdk.cpp gọi mdct_block()/dct_IV() với FFT dispatcher giới hạn N=64/512, dùng dit_fft của FDK.
Bài này kiểm tra transform khi type/shape được chỉ định; không kiểm tra bảng chọn shape trong Block Switching.
Lỗi Block Switching phần 3 vẫn được giữ nguyên dù reference transform có đạt.

Kết quả chạy, công cụ còn thiếu và giới hạn: part5_verification.md.

## Lệnh C++ có thể chạy lại

Từ gốc dự án, trước tiên build thư viện static với MDCT_DEBUG=OFF và FFT_EXPERIMENT=OFF theo README gốc (build/codec).
Thêm .exe cho binary Windows nếu cần.

~~~bash
c++ -std=c++17 -O2 -IlibFDK/include -IlibSYS/include my_workspace/window_mdct/ref/fixed_mdct_radix2.cpp my_workspace/window_mdct/tb/verify_mdct_fdk.cpp build/codec/libfdk-aac.a -o build/verify_mdct_fdk
./build/verify_mdct_fdk
c++ -std=c++17 -O2 -IlibFDK/include -IlibSYS/include my_workspace/window_mdct/ref/fixed_mdct_radix2.cpp my_workspace/window_mdct/tb/gen_mdct_golden.cpp libFDK/src/FDK_tools_rom.cpp -o build/gen_mdct_golden
./build/gen_mdct_golden --verify-python my_workspace/window_mdct/golden/radix2_q31_v1
~~~
