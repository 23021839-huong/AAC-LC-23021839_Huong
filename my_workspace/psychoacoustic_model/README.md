# Psychoacoustic Model AAC-LC

1. gioi thieu tong quan
2. tinh trang du an
3. Cấu trúc và nhiệm vụ

~~~text
psychoacoustic_model/
  README.md
  requirements.txt
  requirements-inputs.txt
  run_psy_analysis.sh
  tools/                    trace, đọc fixed-point, export và vẽ
  experiments/psy/
    tools/                  native encode/decode experiment
    scripts/                2x2 campaign, input suite, metric, plot/report, chuẩn bị WAV
    README.md
  tests/
    psy_analysis/           unit và native trace regression
    psy_experiments/        controls, metric, publication và chuẩn bị input
    rtl/                    native helper oracle
  rtl/                      SFB/energy frontend, log2 và masking
  tb/                       ba testbench VHDL
  input/psy_external/
    manifest.json           metadata loại nguồn trùng cho generator mở rộng
  docs/                     thuật toán, giao tiếp QC, đề xuất PL và kiểm chứng
~~~

WAV thực nằm tại my_workspace/INPUT/data/; không nhân đôi chúng ở đây.
Manifest trong input/psy_external/ chỉ phục vụ generator loại nguồn đã dùng.
Khi chạy campaign, truyền manifest tại my_workspace/INPUT/data/psy_external/manifest.json.

4. Cài dependency và chạy

Từ gốc AAC-LC-23021839_Huong:

~~~bash
python -m pip install -r my_workspace/psychoacoustic_model/requirements.txt
python my_workspace/psychoacoustic_model/tools/run_psy_analysis.py --wav my_workspace/INPUT/data/abc_votay.wav --frames 0:120 --channel 0 --bitrate 32000 --output-dir output/psy_32k --plots-dir plots/psy_32k --verify-bitstream
~~~

Cần CMake, compiler C++17 và generator Ninja/Makefiles thích hợp.
Chi tiết trace/build/test: docs/psy_analysis.md.
Bốn mode Tonality/TNS và campaign nhiều WAV: experiments/psy/README.md.
Source RTL và phần chưa thực hiện: docs/rtl_status.md.
Kết quả kiểm chứng vừa chạy: docs/part6_verification.md.

## Phạm vi điều khiển

Bộ hiện tại bật/tắt Tonality và TNS theo ma trận 2x2.
PNS được giữ theo native baseline, ghi pns_enabled/pns_used; chưa có công tắc PNS độc lập.
--stages chỉ chọn dữ liệu debug được ghi; --expected-pns chỉ kiểm tra cấu hình, không bật/tắt PNS.
RTL hiện chưa tạo được PSY_OUT hoàn chỉnh; proposal full-PL là thiết kế mục tiêu.

## Ánh xạ đọc source

| Chức năng | Source hiện tại trong libAACenc/src/ |
|---|---|
| Điều phối encoder | encoder/aacenc.cpp |
| SFB, energy, masking, TNS/PNS, stereo | psy_model/psy_main.cpp |
| Cấu hình SFB và bảng | psy_model/psy_configuration.cpp, common/aacEnc_rom.cpp |
| Energy, spreading, pre-echo | psy_model/band_nrg.cpp, spreading.cpp, pre_echo_control.cpp |
| Tonality, TNS, PNS | psy_model/tonality.cpp, aacenc_tns.cpp, aacenc_pns.cpp |
| Hook quan sát/điều khiển | psy_model/psy_debug.cpp, psy_experiment.cpp |
| QC phía sau Psy | quantization/ |

Một số tài liệu thuật toán giữ đường dẫn flat cũ; dùng bảng trên để tìm file đã nhóm.
Lỗi bảng window shape của Block Switching vẫn được bảo lưu theo lựa chọn người dùng; xem ../block_switch/docs/verification.md.
