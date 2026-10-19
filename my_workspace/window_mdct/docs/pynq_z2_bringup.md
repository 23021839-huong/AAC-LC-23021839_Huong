# Build và chạy thử MDCT trên PYNQ-Z2

Gói gồm RTL, AXI4-Lite adapter, constraint, Tcl và driver.
Không kèm bitstream/HWH đã build. Kết quả host test không phải bằng chứng đã chạy board.
Trạng thái kiểm chứng lần bàn giao xem part5_verification.md.

## Chuẩn bị

Cần Vivado có board files PYNQ-Z2, part xc7z020clg400-1, cùng PS7/AXI IP.
Cần PYNQ trên board và bit/hwh cùng một build; Python host chỉ cần các package ở requirements.txt.
Sinh golden và chạy mô phỏng theo rtl_workflow.md trước khi build board.

## Vivado

Từ gốc dự án:

~~~bash
vivado -mode batch -source my_workspace/window_mdct/synth/vivado_pynq_z2_bitstream.tcl
~~~

Tcl mặc định FCLK 50 MHz, AXI base 0x43C00000.
Có thể đặt MDCT_FCLK_MHZ và VIVADO_JOBS trước khi chạy.
Script yêu cầu board part hợp lệ, kiểm tra timing/coverage rồi mới export.
Đọc build_info.txt và reports của chính build vừa chạy; không dùng số timing trong tài liệu cũ làm kết quả build hiện tại.

## Đóng gói cặp bit/hwh

~~~bash
python my_workspace/window_mdct/tools/pack_pynq_z2.py --overlay-dir my_workspace/window_mdct/build/pynq_z2/BUILD_ID --output output/mdct_pynq_z2_bundle.zip
~~~

Thay BUILD_ID bằng thư mục export thực tế.
Tool chỉ đóng gói khi có bit, hwh, build_info hợp lệ và golden đã kiểm checksum.
ZIP chứa driver, golden, hướng dẫn và hash; không lấy bit/hwh từ các build khác nhau.

## Chạy trên board

Giải nén bundle vào board, chạy từ thư mục mdct_pynq_z2:

~~~bash
python run_mdct_board.py --bitfile mdct_pynq_z2.bit --golden golden --repeat 1 --compare-float
~~~

summary.json ghi hardware_tested, số frame đạt/thất bại, sai số LSB và thời gian host gồm MMIO/polling.
Chỉ công bố kết quả board sau khi lệnh này chạy trên phần cứng thật và dữ liệu được đọc lại.
--validate-only chỉ kiểm tra dữ liệu golden, không truy cập phần cứng.
