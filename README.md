# AAC-LC-23021839_Huong

Bản bàn giao nghiên cứu AAC-LC để đọc source, build và chạy lại thí nghiệm.

## Trạng thái bàn giao

Phần 1: codec FDK, hệ thống build và các chương trình native cơ bản.
Phần 2: sáu WAV mẫu, thông tin nguồn và tool input đã được đưa sang. Xem my_workspace/INPUT/README.md. Phần 3: đã đưa Block Switching sang; giữ nguyên source theo lựa chọn của người dùng và ghi rõ bài DUT-REF FAIL do bảng window shape thiếu hàng LD. Xem my_workspace/block_switch/docs/verification.md và my_workspace/block_switch/README.md. Phần 4: đã đưa tool Window/MDCT, bốn policy window và bộ kiểm chứng sang; xem my_workspace/window_mdct/README.md. Phần 5: đã đưa FFT experiment, FFT/MDCT RTL, testbench, reference và flow PYNQ; xem my_workspace/window_mdct/experiments/fft/README.md và my_workspace/window_mdct/docs/rtl_workflow.md. Phần mềm được kiểm tra; mô phỏng GHDL/Vivado và chạy FPGA chưa thực thi. Phần 6: đã đưa Psy trace, khảo sát Tonality/TNS với PNS giữ native, input tools và RTL Psy hiện có; xem my_workspace/psychoacoustic_model/README.md. Đã kiểm chứng phần mềm; RTL Psy chưa đầy đủ và chưa mô phỏng GHDL trong lần này. Phần 7: đã đưa Quantization/Coding trace, spectral quantizer reference và profiling; xem my_workspace/quantization_coding/README.md. Native codec/model arithmetic giữ nguyên, bốn cấu hình/script được chỉnh đường dẫn có ghi hash trước/sau. Giao diện run.py và hướng dẫn tổng hợp sẽ được bàn giao ở phần cuối.

Source lấy từ workspace fdk-aac hiện tại, đã có cách nhóm file và hook nghiên cứu.
Đây là snapshot của workspace, không phải bản upstream nguyên thủy.
Source codec và CMake gốc giữ nguyên từng byte; các cấu hình/script hiệu chỉnh đường dẫn được ghi riêng trong adapted_files của manifest.

## Cấu trúc

- libAACenc/: encoder. include/ chứa API công khai; src/ chứa implementation.
- libAACdec/: decoder dùng cho kiểm chứng đầu ra.
- libFDK/: toán fixed-point, FFT/DCT/MDCT, LPC và các tiện ích DSP dùng chung.
- libMpegTPEnc/, libMpegTPDec/: ghi/đọc transport và cấu trúc bitstream.
- libPCMutils/: tiện ích PCM.
- libSYS/: kiểu dữ liệu, bộ nhớ và hỗ trợ nền tảng.
- libArithCoding/, libDRCdec/, libSACenc/, libSACdec/, libSBRenc/, libSBRdec/: các phụ thuộc được CMake hiện tại sử dụng.
- win32/getopt.h: hỗ trợ tham số dòng lệnh khi build trên Windows/MSVC.
- CMakeLists.txt và các file fdk-aac*: cấu hình build, export và cài đặt thư viện.
- aac-enc.c, wavreader.c, wavreader.h: chương trình đọc WAV và mã hóa AAC.
- test-encode-decode.c, sha1.c, sha1.h: kiểm tra encode/decode và hash.
- NOTICE, MODULE_LICENSE_FRAUNHOFER, ChangeLog: thông tin nguồn, giấy phép và lịch sử đi kèm.
- source_manifest.json: danh sách file đã sao chép, kích thước và SHA-256.
- CHANGES_RESEARCH.md: phạm vi bản bàn giao và thay đổi khi đóng gói.

## Nhóm chức năng trong libAACenc/src

| Thư mục | Nội dung |
|---|---|
| encoder/ | API, khởi tạo và điều phối encoder |
| block_switch/ | Block switching và điều khiển window |
| filterbank/ | Biến đổi phổ/MDCT của encoder |
| psy_model/ | SFB, năng lượng, masking, Tonality, TNS, PNS và stereo |
| quantization/ | QC, threshold adjustment, scalefactor và lượng tử hóa |
| coding/ | Bit counting, sectioning, Huffman và ghi bitstream |
| common/ | Bảng, bộ nhớ và tiện ích encoder dùng chung |
| extensions/ | Metadata và các phần mở rộng có trong FDK |
| profiling/ | Hỗ trợ profiling encoder |

Các header nội bộ hiện được giữ trực tiếp tại libAACenc/src/ để giữ nguyên include và CMake.

## Build cơ bản

Cần CMake và compiler C/C++. Các runner nghiên cứu ở phần sau cần C++17.
Ví dụ cho terminal có toolchain trên PATH:

~~~bash
cmake -S . -B build/codec -DBUILD_SHARED_LIBS=OFF -DBUILD_PROGRAMS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/codec --parallel 4
~~~

Với Visual Studio, thêm --config Release vào lệnh build; binary có thể nằm trong build/codec/Release/.
Với Ninja hoặc Makefiles, binary thường nằm trực tiếp trong build/codec/.
Trên Windows, tên chương trình có hậu tố .exe.

## Chạy AAC-LC

Input là WAV PCM16. WAV mặc định: my_workspace/INPUT/data/abc_votay.wav; năm WAV ngoài nằm trong my_workspace/INPUT/data/psy_external/.

~~~bash
./build/codec/aac-enc -t 2 -r 64000 -a 1 -d my_workspace/INPUT/data/abc_votay.wav output.aac
~~~

-t 2 chọn AAC-LC; -r là bitrate mục tiêu theo bit/s; -a 1 bật Afterburner.
Chương trình test-encode-decode nhận một WAV và thử nhiều cấu hình native FDK; nó không chỉ giới hạn ở AAC-LC.

## Cờ nghiên cứu

Các cờ nghiên cứu giữ mặc định OFF trong CMake.
Ở phần 1, dùng BUILD_PROGRAMS=ON và BUILD_SHARED_LIBS=OFF.
Tool MDCT/Window và FFT đã có trong my_workspace/window_mdct/; build và chạy theo README tương ứng. Tool Psy đã có trong my_workspace/psychoacoustic_model/; cài requirements của module và chạy theo README. Tool Quant đã có trong my_workspace/quantization_coding/; chạy theo README của module, dùng build directory riêng.
Không bật các cờ đó trước khi nhận đúng phần tương ứng.

## Kiểm chứng và cập nhật

Đối chiếu từng file được sao chép với source_manifest.json bằng SHA-256.
Build và smoke test được thực hiện riêng; không đưa cache, binary hoặc output test vào bản source.
Kết quả thực tế và giới hạn kiểm chứng được ghi trong CHANGES_RESEARCH.md. Bài test nhiều AOT có một trường hợp AAC-ELD/SBR vượt ngưỡng với file mưa; các cấu hình AAC-LC phần 2 đạt 48/48.
