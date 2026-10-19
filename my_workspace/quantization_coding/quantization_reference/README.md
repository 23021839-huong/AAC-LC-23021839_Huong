# Reference cho spectral quantizer

Đây là model riêng cho spectral kernel: SFB traversal, 3/4 companding, gain/rounding, khôi phục dấu, quantized spectrum và max magnitude/SFB.
Outer QC gồm PE, threshold/rate control, scalefactor search và Huffman/sectioning vẫn là integration boundary; chưa phải standalone bit-exact port toàn bộ QC.

## Thành phần

cpp_ref/: model C++20, CLI và bảng ROM.
python_ref/: model float, fixed-point và utility.
tools/: sinh ba case deterministic, trích ROM và adapter gọi kernel FDK.
verification/: comparator và runner.
docs/, references/: phân tích thuật toán/contract/hardware.

## Build

Từ gốc dự án:

~~~bash
cmake -S my_workspace/quantization_coding/quantization_reference/cpp_ref -B build/quant-reference -DCMAKE_BUILD_TYPE=Release
cmake --build build/quant-reference --parallel 4
~~~

Hai target: quantization_ref_cli (độc lập) và fdk_quant_harness (compile kernel/ROM native để đối chiếu).
Windows thêm .exe; với Visual Studio thêm --config Release và thư mục Release/ cho executable.

## Kiểm chứng

~~~bash
PYTHONPATH=my_workspace/quantization_coding/quantization_reference python -m unittest discover -s my_workspace/quantization_coding/quantization_reference/tests -v
python my_workspace/quantization_coding/quantization_reference/verification/run_regression.py --cpp build/quant-reference/quantization_ref_cli --fdk build/quant-reference/fdk_quant_harness
~~~

PowerShell đặt $env:PYTHONPATH tới thư mục quantization_reference trước khi chạy unittest.
Runner sinh mới ba case zero_long, smoke_long, grouped_short_deadzone vào vectors/.
Python fixed là đối chiếu exact; float dùng đối chiếu sai số; C++/native kernel phải đạt 0 mismatch.
Input case và output CLI là hai đối số thư mục; xem các manifest vừa sinh để biết gain/SFB/dead-zone/prefill.
Vector được sinh khi chạy, không đóng gói output cũ.

## ROM

tools/extract_fdk_tables.py tái tạo python_ref/fdk_tables.py và cpp_ref/fdk_quant_tables.inc từ common/aacEnc_rom.cpp.
Chỉ chạy trong bản staging hoặc khi chủ động cập nhật ROM, vì tool ghi vào hai file bảng.
Lần bàn giao đã chạy trong staging và xác nhận cả hai bảng trùng byte.

CMake, runner regression và extractor được sửa đường dẫn theo bố cục src đã nhóm.
Chi tiết/hash: ../docs/packaging_changes.json. Thuật toán model và kernel giữ nguyên.
