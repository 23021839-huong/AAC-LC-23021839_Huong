# Kiểm chứng phần 5: FFT và bộ source RTL liên quan

Ngày 2026-10-19. Kiểm tra phần mềm trên Windows, GCC 16.1.0, CMake 4.3.2, Ninja 1.13.2; Python 3.12.13, NumPy 2.5.4, Matplotlib 3.11.2.
Source codec, RTL và tool/test được sao chép nguyên byte; tài liệu đóng gói được bổ sung riêng.

## Kết quả đã thực thi

| Hạng mục | Kết quả |
|---|---|
| Configure/build fdk_fft_validate, fdk_fft_experiment, fdk_window_experiment | PASS |
| Native FFT tests | 4/4 PASS |
| FFT pipeline tests | 4/4 PASS |
| Host driver/golden/package tests | 14/14 PASS |
| Numerical gate hai kernel FFT64/512 | 33 trường hợp PASS, bit-exact |
| Reference C++ đối chiếu mdct_block()/dct_IV() với dit_fft của FDK | 6144 output, 0 LSB |
| C++ kiểm golden Python | 18 frame, 39 subtransform, 92160 scalar checks, 0 LSB |
| Model radix-2 đối chiếu port dit_fft | 18432 bin, 0 LSB |
| FFT C++/Python với vector mới sinh | 12 frame, 2560 complex record, 0 LSB |
| Tái sinh ROM/header | 5/5 file trùng byte |
| Driver --validate-only | 18 frame, 18432 bin; checksum PASS |

Native runner được build trực tiếp từ thư mục bàn giao.
Một bản sao runtime byte-identical được tạo ngoài gói để sinh PRE/golden và chạy các harness có đường dữ liệu cố định.
Native FFT test nhận PRE bằng tham số; pipeline test dùng PRE mặc định trong bản runtime; host test thêm tools vào PYTHONPATH.
Không sao chép PRE/golden từ output cũ. Không sửa test/reference/codec để làm bài test đạt.
Không công bố CTest mặc định trên source sạch là đã chạy: hai nhóm FFT của CTest cần sinh PRE trước theo experiments/fft/README.md.

## WAV thực tế

abc_votay.wav: PCM16 mono 48 kHz, 462848 mẫu, 9,642667 s.
PRE được thu mới từ native MDCT: LONG frame 92 và SHORT frame 24.
Cấu hình chung: AAC-LC 64 kb/s, Afterburner, SINE_ONLY.
Mỗi mode có 10 lượt encode không profiling và 10 lượt profiling riêng, cùng warmup.

| Mode | ADTS bitrate (kb/s) | SNR (dB) | AAC (byte) |
|---|---:|---:|---:|
| ORIGINAL_FFT | 64,281 | 18,386 | 77823 |
| RADIX2_ONLY | 64,281 | 18,386 | 77823 |

Hai AAC trùng toàn bộ byte:
SHA-256 777a613968fd9073981bda80aa3fa66b57e3a8c92c32a6749b3ea74dbf29ebc1.
Cả hai phép đo phủ đủ 462848 mẫu; shape trong ICS được xác nhận và sequence giống nhau.
Mỗi lượt profiling ghi 240 lần FFT64 và 424 lần FFT512.
Sáu PNG đã được sinh; đã xem overview.

Timing một đợt chạy này: encode mean 58,005 ms (gốc), 64,938 ms (radix-2); tổng FFT trong lượt profiling riêng 3,145 ms và 13,958 ms.
Đây là số đo trên máy hiện tại, không phải latency RTL hoặc kết luận tốc độ chung trên mọi nền tảng.
Output giống byte phù hợp với mục tiêu giữ lịch truncation/scaling; thay cấu trúc tính toán không bắt buộc làm AAC khác đi.

## Chưa thực thi

- GHDL không có trên PATH và các vị trí đã kiểm tra: chưa compile/mô phỏng các testbench VHDL trong lần bàn giao này.
- Chưa chạy Vivado synthesis/implementation/timing và chưa tạo bit/hwh mới.
- Chưa nạp hoặc kiểm tra trên FPGA PYNQ-Z2 thật.
- Chưa build/chạy trên Linux.

14 ca host dùng FakeMMIO và artifact giả giới hạn trong test để kiểm tra driver/gate đóng gói; không chứng minh RTL/FPGA đúng.
Không lấy kết quả RTL/timing lịch sử trong các tài liệu source làm bằng chứng cho gói hiện tại.

## Lỗi source vẫn bảo lưu

Bài Block Switching DUT-REF phần 3 vẫn FAIL vì blockType2windowShape thiếu hàng LD.
Người dùng chọn giữ nguyên source. Bài reference transform chỉ định trực tiếp type/shape và bài FFT cố định SINE_ONLY không kiểm tra bảng chọn shape đó.
Các PASS ở đây không thay đổi trạng thái FAIL của phần 3.

## Phạm vi đóng gói và bằng chứng

Phần 5 thêm 63 file giữ nguyên từ workspace: tool/test FFT, 19 file RTL FFT/MDCT, AXI wrapper, reference, testbench, driver, Tcl/constraint và ba tài liệu kỹ thuật.
Thêm năm tài liệu hiện hành; cập nhật README/CHANGES/.gitignore và manifest.
Không kèm output cũ, vector sinh sẵn, bit/hwh, binary, cache, ZIP hoặc patch baseline.

Artifact trên máy phát triển nằm ngoài gói:
fdk-aac/build/teacher_review/AAC-LC-23021839_Huong_stage5/
Gồm fft/, runtime_source/, abc_fft/, fft_vectors/, cpp_mdct_vectors/, rom_regen/ và các log/report.
