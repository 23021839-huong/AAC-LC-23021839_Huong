# Kiểm chứng Block Switching

## Các lớp kiểm tra của verify_block_switch

- A: so sánh trạng thái DUT với reference fixed-point, từng frame.
- B: so sánh quyết định với behavioral float; sai khác float là chẩn đoán và không tự quyết định exit code.
- C: kiểm tra các bất biến, chuyển trạng thái và grouping.
- Harness còn kiểm tra hằng số/sanity và kịch bản sync stereo.

Exit code PASS yêu cầu A/C và các kiểm tra sanity/hằng số đạt theo implementation của harness.
Phải đọc riêng chỉ tiêu B khi giải thích độ khớp với float.
CSV của verify phục vụ đối chiếu; tool vẽ đọc CSV do probe tạo, hai schema khác nhau.

## Input thực

verify --pcm nhận raw PCM16 mono, bỏ phần mẫu dư chưa đủ 1024 mẫu.
Nhánh raw so DUT và REF trước bước mono sync; probe ghi cả trước và sau mono sync.
Không đồng nhất hai loại trạng thái khi so số liệu.

Luôn kiểm tra file raw tồn tại, số frame mà harness in ra và tổng số frame tăng tương ứng.
Trong kiểm chứng bàn giao, raw được lấy trực tiếp từ payload WAV; SHA-256 WAV được đối chiếu với manifest input.

## Kiểm tra probe và đồ thị

Kiểm tra frame liên tiếp, hai phase/frame, validSamples khớp WAV, grouping hợp lệ và tổng mẫu thực đúng.
Với silence, kiểm tra không attack và LONG; với impulse mặc định, kiểm tra sự kiện attack và đủ chuỗi LONG/START/SHORT/STOP.
Tool vẽ sử dụng after_sync và backend Agg. PNG/PDF và summary được tạo ngoài source bàn giao.
Danh tính input phải được xác nhận bằng hash bên ngoài CSV.

## Kết quả bàn giao

Hiện trạng: giữ nguyên source theo lựa chọn của người dùng; ghi nhận DUT-REF FAIL.

- Configure/build: PASS trên Windows MinGW.
- CTest: 2/3 PASS; bài DUT-REF thất bại.
- Bộ regression hiện tại chạy 24 kịch bản, 272 frame: A=217 lệch trạng thái, B=189 sai khác float, C=184 lỗi property.
- Nguyên nhân: blockType2windowShape[2][5] trong source workspace và bản bàn giao chỉ khởi tạo một hàng LC ở vị trí hàng 0. Hàng 1 dành cho AAC-LC trở thành toàn giá trị 0.
- Đã đối chiếu gói fdk-aac-2.0.3.tar.gz gốc: bảng có đủ hai hàng LD và LC. Chưa thay source codec.
- Probe native trên abc_votay.wav: 452 frame, CSV có đủ before_sync/after_sync; tool vẽ xuất overview và zoom PNG/PDF thành công.
- Các kết quả này không chứng minh DUT-REF tương đương: bài kiểm chứng đang FAIL. Theo lựa chọn của người dùng, phần 3 giữ nguyên bảng, reference và điều kiện đánh giá, kèm đầy đủ trạng thái lỗi.
- Chưa thực thi trên Linux.
