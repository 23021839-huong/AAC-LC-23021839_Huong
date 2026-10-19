# Block Switching: input, output và thuật toán

## Source đối chiếu

- [DUT implementation](../../../libAACenc/src/block_switch/block_switch.cpp).
- [Trạng thái và API](../../../libAACenc/src/block_switch.h).
- [Enum cửa sổ](../../../libAACenc/src/psy_const.h).
- [Nơi điều phối trong Psy](../../../libAACenc/src/psy_model/psy_main.cpp).
- [Probe native](../tb/probe_block_switch.cpp).
- [Reference model](../ref/ref_block_switch.cpp).

## Input

AAC-LC mono: 1024 mẫu PCM16 liên tiếp mỗi lần gọi, granuleLength=1024, isLFE=0.
BLOCK_SWITCHING_CONTROL giữ lịch sử bộ lọc, năng lượng và window sequence; chỉ khởi tạo một lần cho chuỗi frame.

## Output

Control trong BLOCK_SWITCHING_CONTROL:
- attack, attackIndex và lịch sử attack.
- lastWindowSequence: LONG, START, SHORT hoặc STOP trong luồng AAC-LC.
- windowShape: SINE hoặc KBD theo bảng ánh xạ hiện có.
- noOfGroups và groupLen[]: grouping của short windows sau đồng bộ.
- windowNrg, windowNrgF, accWindowNrg và iirStates: trạng thái phục vụ phân tích/kiểm chứng.

Đây là metadata điều khiển filterbank và các bước sau; khối đọc PCM để phân tích.

## Luồng xử lý

PCM -> năng lượng tám sub-window 128 mẫu / nhánh lọc thông cao
    -> so năng lượng với nền tích lũy
    -> quyết định attack và vị trí
    -> lịch sử và chuyển window sequence
    -> chọn shape/grouping
    -> SyncBlockSwitching
    -> control cuối.

FDKaacEnc_InitBlockSwitching() khởi tạo cấu hình/trạng thái.
FDKaacEnc_BlockSwitching() cập nhật năng lượng, attack và sequence theo từng frame.
FDKaacEnc_SyncBlockSwitching() hoàn thiện grouping/đồng bộ theo số kênh.
Probe gọi lần lượt ba API này theo luồng mono và ghi before_sync/after_sync.

Các bảng/hằng số và phép toán fixed-point giữ trong source FDK; bước bàn giao không thay hệ số hoặc ngưỡng.
Bộ đệm thời gian của Window/MDCT thuộc phần input/filterbank, được chuẩn bị riêng.
Không dùng số frame của probe để suy ra trực tiếp số access unit AAC: encoder còn có priming, buffering và flush.
