# Quantization/Coding AAC-LC

Phần 7: trace QC/coding native, spectral-quantizer reference và profiling.
Thuật toán encoder vẫn nằm trong libAACenc/src/quantization/ và coding/.
Tool nghiên cứu đọc dữ liệu từ encoder thật; không thay encoder bằng mô hình.

## Cấu trúc

~~~text
quantization_coding/
  README.md
  requirements.txt
  run_quant_analysis.sh
  tools/                    native runner, parser, export, plot, orchestration
  tests/quant_analysis/     native regression, schema, audit và plot tests
  quantization_reference/
    cpp_ref/                standalone model và CMake
    python_ref/             float/fixed models và ROM
    tools/                  generator, ROM extractor, native kernel harness
    verification/           cross-model comparison
    tests/                  model unit tests
    docs/, references/      thuật toán, contract và đề xuất hardware
  profiling/                corpus, host/board analysis, DMA/resource tools
  docs/                     pipeline, source map, giao tiếp và kiểm chứng
~~~

Runner Step-0 trên Linux/ARM nằm tại my_workspace/pynq_z2/sw/scripts/run_qc_step0.sh.
WAV dùng chung từ my_workspace/INPUT/; không mang theo output, cache hay vector sinh sẵn.

## Chạy nhanh

Từ gốc AAC-LC-23021839_Huong:

~~~bash
python -m pip install -r my_workspace/quantization_coding/requirements.txt
python my_workspace/quantization_coding/tools/run_quant_analysis.py --wav my_workspace/INPUT/data/abc_votay.wav --frames 10:26 --bitrate 64000 --output-dir output/quant --plots-dir plots/quant --verify-bitstream --plot-frame 10
~~~

Cần CMake, compiler C++17 và Python 3.10+; tool tự build debug/normal ở build/quant-analysis-*.
Reference C++ riêng cần C++20; xem quantization_reference/README.md.
Profiling: profiling/README.md. Trace/audit/test: docs/quant_analysis.md.
Kết quả thực tế và giới hạn: docs/part7_verification.md.

## Ánh xạ source

| Chức năng | Source trong libAACenc/src/ |
|---|---|
| QC/rate loop và gain | quantization/qc_main.cpp |
| PE, bit allocation, threshold | quantization/adj_thr.cpp |
| Scalefactor search | quantization/sf_estim.cpp |
| Quantize/inverse/distortion | quantization/quantize.cpp |
| Sectioning, dynamic bit count | coding/dyn_bits.cpp |
| Huffman bit cost | coding/bit_cnt.cpp |
| Ghi syntax/bitstream | coding/bitenc.cpp |
| ROM dùng chung | common/aacEnc_rom.cpp |
| Quan sát QC | quantization/quant_debug.cpp |
| Profiling | profiling/aacenc_profile.cpp |

Một số tài liệu gốc dùng đường dẫn flat cũ; dùng bảng này để tìm source.
Bốn file cấu hình/script đã hiệu chỉnh đường dẫn, có hash và chi tiết trong docs/packaging_changes.json.
Mã thuật toán native và reference được giữ nguyên.
Lỗi Block Switching đã ghi ở phần 3 tiếp tục được bảo lưu.
