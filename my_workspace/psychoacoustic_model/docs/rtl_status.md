# Phạm vi RTL Psy đang bàn giao

rtl/ có bốn file:
- psy_pkg.vhd: kiểu dữ liệu/hằng số/toán fixed-point dùng chung.
- psy_log2.vhd: phép log dùng trong các tầng hỗ trợ.
- psy_sfb_frontend.vhd: spectrum -> low-pass -> headroom/energy/log theo SFB -> rescale.
- psy_masking.vhd: engine một window sau TNS: clipping, spreading, PCM floor, pre-echo, energy spreading và threshold log.

Frontend và masking là các tầng riêng; chưa có scheduler full-Psy ghép chúng thành PSY_OUT.
Chưa có RTL hoàn chỉnh cho Tonality/TNS/PNS, grouping/stereo hoặc top full-PL.
psy_model_hardware_proposal.md là đề xuất mục tiêu, không phải xác nhận đã triển khai toàn bộ.

## Bộ kiểm chứng

tb/ gồm tb_psy_math, tb_psy_sfb_frontend, tb_psy_masking.
tests/rtl/fdk_psy_rtl_oracle.cpp gọi helper native FDK để tạo vector; nó không phải oracle ARM hoặc full encoder.

Từ gốc dự án, khi có compiler C++17 và GHDL:

~~~bash
python my_workspace/psychoacoustic_model/tools/run_psy_rtl_tests.py --cxx g++ --ghdl ghdl --build-dir build/psy_rtl
~~~

Runner compile oracle, sinh vector mới, compile VHDL-2008 và chạy ba testbench.
Báo cáo có source/vector hash và ghi rõ full_psy=false, arm_verified=false.
Lần bàn giao này chỉ build/chạy oracle; chưa mô phỏng GHDL, synthesis/timing hay FPGA.
Xem part6_verification.md để phân biệt bằng chứng phần mềm và phần chưa thực thi.
