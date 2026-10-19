# Kiểm chứng phần 6: Psy-model và bộ khảo sát

Ngày 2026-10-19. Build/chạy trên Windows với GCC 16.1.0, CMake 4.3.2, Ninja 1.13.2.
Python 3.12.13; NumPy 2.5.4, Matplotlib 3.11.2, Pandas 3.0.6, SciPy 1.18.1, SoundFile 0.14.0.
Dependency bổ sung được cài riêng ngoài gói bàn giao; không mang venv/package/binary sang.

## Build và test

Ba cấu hình Release/static đạt: trace debug, normal không hook, experiment.
Bản normal build cả fdk_psy_trace và fdk_psy_experiment; các cờ research khác OFF.

| Nhóm | Kết quả |
|---|---|
| Trace data/unit | 9/9 PASS |
| Native trace regression | 5/5 PASS |
| Native Tonality/TNS controls | 2/2 PASS |
| MSE/SNR/NRMSE/alignment | 5/5 PASS |
| Publication/error handling | 2/2 PASS |
| Input signal preparation | 2/2 PASS |
| Extended input preparation/validation | 6/6 PASS |

Tổng 31/31 ca khác nhau đạt.
Publication tests chủ động gây lỗi preflight/copy và yêu cầu xóa trạng thái PASS cũ; thông báo ERROR trong các ca này là dữ liệu test.
Một bản sao runtime byte-identical của source/tool được dùng cho test cần đường build mặc định; binary là binary build từ bản bàn giao.
Không sửa codec/reference/test để ép đạt.

Native trace regression bao gồm 6 cấu hình silence/tone/noise/transient, mono/stereo, 44.1/48 kHz và các bitrate.
Tổng 144 frame/channel được kiểm tra; AAC debug ON/OFF trùng byte ở cả 6 cấu hình.
Noise mono 48 kHz/32 kb/s có 100 lượt band PNS được chọn trong range test; đây là quan sát native, không phải PNS toggle.

## Trace WAV thật, 32 kb/s

abc_votay.wav, mono 48 kHz; trace frame [0,120), channel 0:
- validation valid=true; 56595 record, 120 frame/channel, 4024 energy-shift checks.
- Tổng trong range: 46 TNS filters, 206 lượt band PNS.
- AAC debug/normal trùng byte, SHA-256 49531060805ff5dc1eb4dc79cdd3ac5818892ebe53557cf622e7f18bf76b4f4e.
- Đã sinh 13 PNG cho SHORT frame 24/window 3 và 13 PNG cho LONG frame 5/window 0.
- LONG frame 5 có 5 band PNS được chọn; đã xem plot PNS và overview SHORT.
- SHORT bỏ qua tonality và không có band PNS là nhánh native hợp lệ.

## Campaign output AAC, 64 kb/s

6 WAV đã bàn giao: abc_votay và năm bản ghi ngoài 30 s.
4 mode/input, tổng 24/24 cấu hình PASS.
abc: 40 lượt encode chính, 40 lượt profiling riêng.
Bộ năm input ngoài: 20/20 case, 200 lượt encode chính, 20 lượt profiling riêng.
Tổng 240 lượt encode chính và 60 lượt profiling, không gồm warmup/preflight.

Mọi case so đủ mẫu đầu vào; Window/MDCT và cấu hình PNS giống nhau giữa các mode.
PNS native tắt trong cả sáu cấu hình mono 48 kHz/64 kb/s này.

Ví dụ abc_votay:

| Mode | AAC (byte) | SNR (dB) | TNS filters encoder/decoder |
|---|---:|---:|---:|
| Tonality ON, TNS ON | 77823 | 18,386 | 114/114 |
| Tonality ON, TNS OFF | 77833 | 18,589 | 0/0 |
| Tonality OFF, TNS ON | 77823 | 18,386 | 114/114 |
| Tonality OFF, TNS OFF | 77833 | 18,589 | 0/0 |

Tonality ON thực thi trên 424 frame/channel; OFF không thực thi.
Cặp ON/OFF Tonality giữ cùng TNS trùng byte trên cả sáu input, phù hợp với việc PNS đang tắt.
Bật/tắt TNS làm AAC khác byte trên cả sáu input.
Đã sinh báo cáo/plot của campaign và xem overview abc.
Các số đo này xác nhận tool chạy và can thiệp đúng phạm vi; không đủ để tuyên bố nên bỏ Tonality/TNS/PNS hay đánh giá chất lượng cảm nhận chỉ bằng SNR.

## Giới hạn PNS và RTL

Bộ controls hiện là Tonality/TNS 2x2, không có PNS toggle độc lập.
--expected-pns chỉ assert. Với native PNS bật, case OFF không tách phụ thuộc được sẽ báo UNSUPPORTED; native test đã kiểm tra nhánh này.

Oracle RTL native compile/chạy đạt, tạo 3 file vector primitives/frontend/masking không rỗng.
Chưa có GHDL trên PATH nên chưa mô phỏng ba testbench VHDL trong lần bàn giao này.
Chưa synthesis/timing/Vivado, chưa chạy FPGA/ARM/Linux.
RTL Psy chỉ có frontend SFB/energy và masking riêng; chưa có scheduler/full PSY_OUT, Tonality/TNS/PNS/grouping/stereo đầy đủ.
Không tải lại bộ 15 WAV mới trong bước này; các hàm chuẩn bị/kiểm tra input được kiểm chứng bằng dữ liệu test.

## Lỗi source được bảo lưu

Block Switching DUT-REF phần 3 vẫn FAIL vì bảng window shape thiếu hàng LD.
Nguồn hiện tại được giữ nguyên theo lựa chọn người dùng; các PASS Psy không xóa lỗi đó.
Kết quả là của snapshot nghiên cứu hiện tại, không được coi là kiểm chứng một bản FDK upstream sạch.

## Đóng gói

Phần 6 thêm 39 file nguyên byte: tool/test/RTL, sáu tài liệu thuật toán và manifest source-ID cần cho generator.
Thêm bảy file hướng dẫn/dependency hiện hành.
WAV tập trung trong my_workspace/INPUT; không nhân đôi WAV, output, plot, vector, cache, binary hay môi trường Python.
Bằng chứng phát triển: fdk-aac/build/teacher_review/AAC-LC-23021839_Huong_stage6/
Các thư mục chính: trace_debug/, normal/, experiment/, abc_trace_32k/, abc_controls/, external_campaign/, oracle_vectors/, runtime_source/.
