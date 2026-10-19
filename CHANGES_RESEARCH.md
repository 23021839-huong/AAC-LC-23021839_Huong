# Phạm vi cập nhật nghiên cứu

## Phần 1: codec và build

- Nguồn: workspace fdk-aac của dự án AAC-LC.
- Giữ nguyên source codec, header, bảng và cấu hình CMake được sao chép.
- Giữ bố trí các nhóm chức năng trong libAACenc/src/.
- Mang theo CLI aac-enc và chương trình test-encode-decode cùng các phụ thuộc trực tiếp.
- Thêm README.md, .gitignore, tài liệu này và source_manifest.json cho bản bàn giao.
- Chưa đưa input, tool nghiên cứu, RTL/testbench hoặc kết quả cũ sang.
- Manifest chứng minh việc sao chép từ workspace hiện tại; không đại diện diff đầy đủ so với upstream FDK nguyên thủy.

## Kiểm chứng

- Configure và build Release/static thành công bằng CMake 4.3.2, Ninja 1.13.2, GCC 16.1.0 trên Windows.
- aac-enc mã hóa WAV PCM16 mono 48 kHz thành AAC-LC ADTS: 454 frame, 77.823 byte; exit code 0.
- test-encode-decode chạy 11 cấu hình native trên WAV thử: 0 failures, exit code 0.
- Đối chiếu SHA-256 của 453 file đã sao chép với workspace nguồn: khớp toàn bộ.
- GCC có cảnh báo stringop-overflow tại libSACdec/src/sac_bitdec.cpp; không thay codec trong bước đóng gói.
- Chưa chạy build trên Linux; README cung cấp lệnh CMake độc lập với đường dẫn máy phát triển.
- Binary, cache, WAV đầu vào và AAC thử nghiệm được giữ ngoài bản bàn giao phần 1.

## Phần 2: input và tiện ích dùng chung

- Thêm abc_votay.wav nguyên gốc của dự án và năm WAV bên ngoài dài 30 s: engine, birds, bells, clapping, rain.
- Sáu WAV đều PCM16 mono 48 kHz. Bộ năm WAV, manifest, SOURCES và metadata nguồn đặt tại my_workspace/INPUT/data/psy_external/.
- Giữ nguyên byte dữ liệu và thông tin nguồn đã có; không mang raw download, ZIP, output hoặc environment Python sang.
- Sao chép input_pipeline_ref.cpp, wav_to_fft_input.py và wav_pcm.cpp/.h; giữ nguyên source các công cụ này.
- Thêm README và chỉ mục input để thầy dùng đường dẫn tương đối.
- Đối chiếu SHA-256 tổng cộng 467 file được sao chép: khớp workspace nguồn.
- Reader WAV dùng chung khớp toàn bộ mẫu PCM của cả sáu WAV.
- Kiểm tra 3 frame buffer/input trên mỗi WAV: khớp ánh xạ mẫu và padding.
- Kiểm tra stimulus FFT trên mỗi WAV: 11 transform, 2.048 cặp phức Q1.23; khớp công thức ghép PCM.
- AAC-LC: sáu file đều tạo ADTS hợp lệ; 48/48 cấu hình encode/decode native đạt trên Windows.
- Bài test native rộng gồm 66 cấu hình có 1 trường hợp vượt ngưỡng sai số: b05_rain_noise.wav, AAC-ELD AOT39, SBR bật, 64 kb/s; avg_diff=366 > 300. Đã tái hiện riêng cấu hình này. Không thay ngưỡng hay source codec để làm test đạt.
- Trường hợp AAC-ELD/SBR được ghi nhận ngoài phạm vi AAC-LC; không ghi toàn bộ test nhiều profile là PASS.
- Chưa thực thi trên Linux. Artifact kiểm chứng nằm ngoài thư mục bàn giao.
## Phần 3: Block Switching giữ nguyên source và ghi nhận FAIL

- Đã đưa năm source native probe/reference/verification/plot sang nguyên byte; thêm CMake riêng và hướng dẫn hiện hành.
- Build và luồng probe/vẽ chạy được, nhưng CTest DUT-REF đang FAIL vì bảng window shape của source hiện tại thiếu hàng LD.
- Gói FDK 2.0.3 gốc được đọc trực tiếp để đối chiếu: cần hàng LD trước hàng LC.
- Người dùng chọn giữ nguyên source và ghi rõ kiểm chứng thất bại; codec ở workspace gốc và bản bàn giao đều được giữ nguyên.
- Lỗi đã tồn tại trong snapshot phần 1. Các phép encode/decode phần 1-2 đã đạt trong phạm vi được ghi, nhưng không được coi là chứng minh window-shape policy khớp FDK gốc.
- Xem my_workspace/block_switch/docs/verification.md và source_manifest.json để biết trạng thái kiểm chứng hiện tại.
## Phần 4: Window/MDCT và bốn policy window

- Thêm 11 source/tool/test giữ nguyên byte; thêm bốn tài liệu hiện hành.
- CMake gốc và source codec giữ nguyên; dùng helper WAV đã có từ phần 2.
- Ba cấu hình Release/static configure/build đạt trên Windows: MDCT debug, baseline không debug và window experiment.
- CTest đạt 5/5 nhóm; tổng 28 ca khác nhau đạt sau khi chạy bổ sung MDCT với --baseline để không skip ca so sánh AAC.
- Chạy abc_votay.wav: trace native frame 92 LONG; AAC debug ON/OFF trùng byte; đã vẽ và xem pipeline.
- Bốn policy window chạy thành công, mỗi policy warmup + 5 lượt đo; xác nhận shape trong ICS, sequence giống nhau và metric bao phủ toàn bộ 462.848 mẫu.
- Output/build/cache/binary nằm ngoài bản bàn giao; chỉ source/tool/test/tài liệu được thêm.
- Lỗi Block Switching DUT-REF phần 3 vẫn giữ nguyên và được ghi rõ; kết quả phần 4 không được dùng để công bố lỗi đó đã hết.
- Chưa chạy trên Linux. Xem my_workspace/window_mdct/docs/verification.md về bằng chứng và giới hạn.

## Phần 5: FFT và source RTL Window/MDCT/PYNQ

- Thêm 63 file giữ nguyên byte; năm tài liệu đóng gói hiện hành.
- Build ba target FFT/window đạt; 8/8 ca FFT và 14/14 ca host driver/package đạt.
- Numerical gate đạt 33 trường hợp; reference C++/Python khớp 0 LSB trên 18 frame, 39 subtransform.
- Reference transform đối chiếu FDK đạt 6144 output; FFT C++/Python đạt 2560 complex record; tái sinh ROM/header 5/5 file trùng byte.
- Chạy abc_votay.wav với FFT gốc/radix-2, 10 benchmark và 10 profiling riêng mỗi mode: AAC trùng byte, metric bao phủ toàn bộ mẫu.
- Sinh PRE/golden mới trong bản runtime biệt lập, không phụ thuộc output cũ và không đưa kết quả sinh ra vào bản source.
- Chưa mô phỏng VHDL do không có GHDL trên PATH; chưa chạy Vivado, FPGA hoặc Linux.
- Lỗi Block Switching DUT-REF phần 3 vẫn được bảo lưu; không sửa codec/reference/test.
- Xem my_workspace/window_mdct/docs/part5_verification.md về số đo, phạm vi và giới hạn.

## Phần 6: Psy-model và khảo sát Tonality/TNS/PNS

- Thêm 39 file giữ nguyên byte và bảy hướng dẫn/dependency hiện hành.
- Wav giữ tập trung trong INPUT; chỉ thêm manifest source-ID tại vị trí tương thích cho generator mở rộng.
- Build ba cấu hình Psy đạt; 31/31 ca kiểm chứng đạt.
- Native trace regression 6 cấu hình có AAC debug ON/OFF trùng byte; trace WAV thật 120 frame cũng trùng byte.
- 24/24 cấu hình trên sáu WAV đạt, 240 encode benchmark và 60 profiling riêng; đã chạy export, plot và report.
- Phát hiện Pandas cần cho plot campaign và đưa vào requirements riêng; SciPy/SoundFile chỉ cần thêm cho tool chuẩn bị input.
- PNS giữ cấu hình native, chưa có toggle độc lập; case OFF không hỗ trợ khi PNS bật được ghi UNSUPPORTED.
- Oracle native cho RTL chạy được; chưa mô phỏng GHDL, synthesis, FPGA, ARM hoặc Linux. RTL Psy chưa phải full-PL.
- Giữ nguyên lỗi Block Switching DUT-REF phần 3 theo lựa chọn người dùng.
- Output/binary/cache/venv và kết quả campaign nằm ngoài gói source; xem docs/part6_verification.md của module Psy.

## Phần 7: Quantization/Coding, reference và profiling

- Thêm 39 file nguyên byte; bốn file hiệu chỉnh đường dẫn đóng gói, bảy file tài liệu/dependency/biên bản.
- Giữ nguyên mã codec và phép toán reference; workspace gốc không bị sửa.
- Tái hiện lỗi path trên staging rồi sửa CMake, generator runner, ROM extractor và inventory/ROM path của runner Step-0.
- Hash source/delivery và replacement lưu trong my_workspace/quantization_coding/docs/packaging_changes.json.
- Build Quant debug/normal/profiler và reference C++/FDK harness đạt.
- 33/33 ca test đạt; ba case cross-model đều 0 mismatch; ROM tái sinh trong staging trùng byte.
- Audit Psy/QC khớp 21624 giá trị raw; WAV thật có 454 packet decode-check đạt, debug/normal/no-trace/profiler AAC trùng byte.
- Profiler host tạo ba CSV thật; corpus generator smoke tám WAV đạt; gate thiếu artifact board giữ PENDING.
- Chưa chạy campaign Linux/ARM, DMA, synthesis/FPGA; không có RTL/QMAX riêng được công bố.
- Giữ nguyên lỗi Block Switching DUT-REF phần 3. Artifact kiểm chứng nằm ngoài gói source.
