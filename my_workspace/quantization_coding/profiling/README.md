# Profiling QC và gate Step-0

## Native profiler trên host

Từ gốc dự án:

~~~bash
cmake -S . -B build/encoder-profile -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DBUILD_PROGRAMS=ON -DFDK_ENABLE_ENCODER_PROFILING=ON
cmake --build build/encoder-profile --target aac-enc --parallel 4
mkdir -p output/profile
FDK_PROFILE_CSV=output/profile/encoder_profile.csv FDK_PROFILE_FRAMES_CSV=output/profile/profile_frames.csv FDK_PROFILE_BANDS_CSV=output/profile/profile_band_trials.csv ./build/encoder-profile/aac-enc -t 2 -r 64000 -a 1 -d my_workspace/INPUT/data/abc_votay.wav output/profile/encoded.aac
~~~

Các cờ debug/experiment khác OFF. PowerShell đặt ba biến $env:FDK_PROFILE_* tương ứng, binary có .exe.
CSV aggregate, per-frame và per-band giúp xác định workload/trials; timing host không đại diện timing Cortex-A9/PL.

## Tool đi kèm

- generate_corpus.py: tạo tám tín hiệu PCM16 mono 48 kHz deterministic.
- analyze_step0.py: phân phối p50/p95/p99, overhead, workload và gate.
- dma_microbenchmark.py: đo DMA trên overlay loopback phù hợp; cần PYNQ và board thật.
- extract_overlay_budget.py: đọc report Vivado và kiểm budget tài nguyên.
- scope_v1.json: cấu hình, corpus và artifact mà gate yêu cầu.

~~~bash
python my_workspace/quantization_coding/profiling/generate_corpus.py --output output/qc_corpus
python my_workspace/quantization_coding/profiling/analyze_step0.py output/qc_step0 --output output/qc_step0_summary
~~~

Artifact thiếu thì gate phải PENDING; exit code của analyzer không tự đồng nghĩa gate PASS.
Corpus tổng hợp không thay thế speech/music thật mà scope yêu cầu.

## Campaign Linux/ARMv7

~~~bash
bash my_workspace/pynq_z2/sw/scripts/run_qc_step0.sh output/qc_corpus output/qc_step0
~~~

Runner cần Linux ARMv7/PYNQ-Z2, Git checkout có revision, CMake/GCC, Python3, sha256sum, taskset và GNU time.
Với bản export chưa có .git, tạo Git snapshot hoặc đưa source vào repository trước khi dùng runner này; source_manifest.json vẫn ghi nguồn export.
Native profiler ở phần trên chạy độc lập với Git.
REPEATS tối thiểu 3; script không tự đổi CPU governor.
DMA, bus counters và resource report phải là artifact thật; không dùng kết quả giả để đóng gate.

## Trạng thái

Lần bàn giao đã smoke profiler Windows và tạo CSV thật, AAC trùng baseline.
Bash syntax của runner đã kiểm tra; chưa chạy campaign Linux/ARM, DMA hay FPGA.
Chưa có RTL/QMAX và AXI wrapper riêng cho Quantization/Coding trong bộ source hiện tại.
Gate Step-0 hiện chưa được chấp nhận; xem ../docs/part7_verification.md.
