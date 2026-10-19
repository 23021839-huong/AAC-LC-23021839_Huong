# Kiểm chứng phần 4: Window/MDCT

Ngày: 2026-10-19.
Source được build trực tiếp từ AAC-LC-23021839_Huong; source/tool gốc giữ nguyên.
Kết quả này chỉ áp dụng cho các phép kiểm tra được liệt kê dưới đây.

## Môi trường đã thực thi

Windows, MinGW GCC 16.1.0, CMake 4.3.2, Ninja 1.13.2.
Python 3.12.13, NumPy 2.5.4, Matplotlib 3.11.2.
Release, static library; các cấu hình trace, baseline và window có build directory riêng.
Chưa thực thi trên Linux. Lệnh Linux trong README là hướng dẫn chạy, không phải bằng chứng đã chạy.

## Kết quả

| Phạm vi | Kết quả |
|---|---|
| Configure/build MDCT_DEBUG=ON, baseline OFF và WINDOW_EXPERIMENT=ON | 3/3 PASS |
| CTest MDCT | 2/2 nhóm PASS |
| CTest Window | 3/3 nhóm PASS |
| Native MDCT chạy trực tiếp với --baseline | 9/9 ca PASS, không skip |
| Plot/đọc trace MDCT | 6/6 ca PASS |
| Native window policy | 3/3 ca PASS |
| Measurement units | 7/7 ca PASS |
| Pipeline/case lỗi | 3/3 ca PASS |

Tổng cộng 28 ca khác nhau đã được chạy và đạt.
CTest MDCT mặc định skip một ca đối chiếu baseline vì không truyền --baseline; ca đó đã được chạy bổ sung bằng lệnh trực tiếp.
Các ca bao gồm SHORT với tám transform độc lập, chọn kênh stereo, dữ liệu PCM24, từ chối float NaN/WAV hỏng/trace cũ, số học metric và công bố output thất bại.

## Chạy trên WAV thật

Input my_workspace/INPUT/data/abc_votay.wav: PCM16 mono, 48 kHz, 462.848 mẫu, 9,642667 s.

MDCT trace:
- Auto chọn native transform frame 92, channel 0, LONG, shape SINE.
- 2048 mẫu PCM -> 1024 fold -> 512 complex pre -> 512 complex FFT -> 1024 MDCT.
- 454 ADTS packet; encoder delay 2048 mẫu.
- AAC của debug ON và baseline OFF trùng toàn bộ byte.
- SHA-256: 777a613968fd9073981bda80aa3fa66b57e3a8c92c32a6749b3ea74dbf29ebc1.
- Plotter xuất 10 PNG và stage_statistics.json; đã xem biểu đồ pipeline tổng quan.

Window campaign: bốn policy, mỗi policy một warmup và năm lần encode đo.
Tất cả hàng có status=ok; shape trong ICS được xác nhận, chuỗi sequence giống nhau, so sánh đủ 462.848 mẫu/kênh.
Mỗi policy có 376 LONG, 24 START, 30 SHORT, 24 STOP.

| Policy | ADTS bitrate (kb/s) | SNR (dB) | AAC (byte) |
|---|---:|---:|---:|
| SINE_ONLY | 64,281 | 18,386 | 77.823 |
| KBD_ONLY | 64,225 | 17,955 | 77.755 |
| SINE_LONG_KBD_SHORT | 64,275 | 18,189 | 77.815 |
| KBD_LONG_SINE_SHORT | 64,233 | 18,084 | 77.765 |

Bốn hash AAC khác nhau; EXP01 trùng baseline hiện tại.
Năm PNG của window campaign đã được sinh; đã xem biểu đồ tổng quan.
Bảng này xác nhận tool chạy và phép đo hoạt động; một WAV và SNR không đủ kết luận chính sách tốt nhất cho mọi input.

## Lỗi nguồn vẫn được giữ nguyên

Bài Block Switching DUT-REF ở phần 3 vẫn FAIL do blockType2windowShape thiếu hàng LD.
Người dùng đã chọn giữ nguyên source. Không sửa codec, reference hoặc ngưỡng để làm bài test đó đạt.
Các kiểm tra phần 4 đạt không xóa hay phủ nhận lỗi phần 3.
Bốn policy tường minh được kiểm tra độc lập; native DEFAULT hiện tại không phải policy LC chuẩn của FDK 2.0.3 gốc.

## Bằng chứng và phạm vi đóng gói

Trên máy phát triển, artifact được giữ ngoài bản bàn giao:
fdk-aac/build/teacher_review/AAC-LC-23021839_Huong_stage4/

Các thư mục con: mdct_debug/, mdct_baseline/, window/, abc_mdct/, abc_baseline/, abc_window/.
Log CTest và test có --baseline nằm cùng thư mục stage4.
Không mang binary, cache, AAC, WAV giải mã, CSV hay plot kết quả này sang gói source.
Manifest gốc ghi danh sách file tool/test và SHA-256 để đối chiếu với workspace.
