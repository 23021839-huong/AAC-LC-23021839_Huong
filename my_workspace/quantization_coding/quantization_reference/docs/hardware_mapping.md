# Bước 4 — Định hướng hardware cho spectral quantizer

## Interface tối thiểu

Một transaction line cần `valid`, `last`, `mdct_q31[31:0]`, `qss` và cờ dead-zone. Output gồm `valid`, `q[15:0]`, cờ `range_violation`; metadata SFB/group đi song song hoặc được bộ điều khiển tạo từ offset RAM. Max magnitude được reduce và chốt ở cuối SFB.

## Datapath golden đề xuất

```text
abs/sign -> ROM gain-Q -> MUL32x16 -> CLZ32 -> normalize
         -> ROM pow3/4 -> ROM gain-E -> MUL16x16 -> shift
         -> add rounding -> >>15 -> restore sign -> max/SFB
```

Một kiến trúc pipeline dễ kiểm chứng có 7–9 stage, throughput một hệ số/clock sau khi đầy pipeline. Hai multiplier có thể dùng hai DSP để giữ throughput, hoặc time-multiplex một DSP nếu chấp nhận hai chu kỳ/line. LUT 512×16 chỉ khoảng 8 Kibit và phù hợp một BRAM nhỏ hoặc distributed ROM; hai bảng 4 phần tử nên dùng logic hằng.

## Width và quy tắc bắt buộc

- Input và accumulator gain: signed 32 bit.
- ROM `3/4`, ROM Q/E: signed-positive 16 bit.
- Tích LUT: 32 bit.
- CLZ và shift count cần giữ signed vì `total_shift_before` có thể âm.
- Right shift là arithmetic ở những đường signed.
- Không saturate output trong golden profile; phát cờ khi `abs(q)>8191`.
- Dấu phải đi cùng latency của datapath.

## Controller SFB

Controller đọc `sfb_offsets[sfb]..sfb_offsets[sfb+1]`, tính `qss = global_gain - scalefactor[sfb]`, bỏ qua các SFB từ `max_sfb_per_group` đến `sfb_per_group-1` trong từng group, và reset max accumulator ở đầu SFB. `active_line_mask` trong vector là oracle cho chính logic enable này.

## Golden và approximation

Profile `golden` dùng nguyên ROM/truncation FDK và yêu cầu bit-exact. Các thay đổi như nội suy LUT, piecewise polynomial, log/exp hay giảm width phải nằm ở profile `approx`; regression phải báo mismatch count, max error, mean absolute error và vị trí theo SFB/line. Chưa có approximation nào được đưa vào source hiện tại.

Nghiên cứu về complexity scaling của AAC rate–distortion loop được dùng để định hướng tách mức độ phức tạp của control loop, không dùng để thay công thức kernel hoặc ROM. Do đó kết quả C++/Python hiện tại vẫn bám trực tiếp FDK.
