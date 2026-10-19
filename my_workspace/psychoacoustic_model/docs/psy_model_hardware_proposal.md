# Kiến trúc đưa toàn bộ psy-model lên PL

Cập nhật ngày 07/10/2026 theo yêu cầu người dùng. Ranh giới theo [diagram đã thống nhất](psy_model_definition.md): **spectrum sau filterbank -> toàn bộ psy-model trên PL -> PSY_OUT cho QC trên PS**.

Đây là đề xuất kiến trúc đầy đủ, thay thế phương án chia datapath Psy trên PL và quyết định công cụ trên ARM. Chưa triển khai RTL/HAL hoặc đo synthesis, utilization, timing cho core Psy.

## 1. Phạm vi toàn bộ Psy trên PL

**PL tự thực hiện toàn bộ xử lý theo frame: SFB/energy, chọn scale, log, masking/pre-echo, tonality, TNS detection/decision/filtering, PNS, short grouping, MS/Intensity Stereo và tạo output.**

PS thực hiện host control: nạp cấu hình/bảng khi init, gửi descriptor, quản lý buffer/DMA, nhận kết quả và chạy QC/coding. Descriptor không chứa các kết quả mà Psy phải tự quyết định như finalShift, tonality, hệ số/quyết định TNS, cờ PNS/MS/Intensity.

~~~text
Block Switching / window metadata (PS)
             |
filterbank (PL hoặc SW baseline)
             |
spectrum + exponent + metadata
             |
psy_core: toàn bộ Psy (PL)
             |
PSY_OUT packet: phổ + energy/threshold + tool metadata
             |
QCMainPrepare -> QCMain -> coding (PS)
~~~

Phạm vi hoàn chỉnh: AAC-LC, granule 1024, một hoặc hai channel mỗi element, LONG/START/SHORT/STOP và đường LFE. Sample rate/bitrate/bandwidth chọn qua config image đã khóa. Kiểm chứng đầu dùng mono 48 kHz, CBR 64 kb/s, afterburner bật theo [scope_v1.json](../../quantization_coding/profiling/scope_v1.json). **Mono là mốc bring-up; stereo thuộc phạm vi nghiệm thu toàn bộ khối.** LD/ELD cần đặc tả mở rộng riêng.

## 2. Phân rã module và code dự án

| Module đề xuất | Chức năng hoàn toàn trên PL | Code tham chiếu |
|---|---|---|
| psy_config | Chọn bảng long/short, cấp offsets/hệ số, kiểm tra config | [psy_configuration.cpp:534](D:/A-lab/AAC/fdk-aac/libAACenc/src/psy_configuration.cpp:534), [psy_configuration.h:120](D:/A-lab/AAC/fdk-aac/libAACenc/src/psy_configuration.h:120) |
| psy_energy | Low-pass/zero detection, headroom, energy/log, chọn finalShift và rescale các channel/window | [psy_main.cpp:589](D:/A-lab/AAC/fdk-aac/libAACenc/src/psy_main.cpp:589), [psy_main.cpp:636](D:/A-lab/AAC/fdk-aac/libAACenc/src/psy_main.cpp:636), [band_nrg.cpp:111](D:/A-lab/AAC/fdk-aac/libAACenc/src/band_nrg.cpp:111) |
| psy_tonality | Chaos measure, smoothing, tổng theo SFB và chỉ số tonality | [chaosmeasure.cpp:112](D:/A-lab/AAC/fdk-aac/libAACenc/src/chaosmeasure.cpp:112), [tonality.cpp:121](D:/A-lab/AAC/fdk-aac/libAACenc/src/tonality.cpp:121), [tonality.cpp:175](D:/A-lab/AAC/fdk-aac/libAACenc/src/tonality.cpp:175) |
| psy_tns | Quarter scaling/ACF, normalization, Schur/ParCor, lượng tử hệ số, quyết định/merge/sync, LPC và FIR | [aacenc_tns.cpp:619](D:/A-lab/AAC/fdk-aac/libAACenc/src/aacenc_tns.cpp:619), [aacenc_tns.cpp:766](D:/A-lab/AAC/fdk-aac/libAACenc/src/aacenc_tns.cpp:766), [aacenc_tns.cpp:1051](D:/A-lab/AAC/fdk-aac/libAACenc/src/aacenc_tns.cpp:1051), [FDK_lpc.cpp:431](D:/A-lab/AAC/fdk-aac/libFDK/src/FDK_lpc.cpp:431) |
| psy_masking | C_RATIO, clip, spreading hai lượt, PCM floor, pre-echo và spread energy | [psy_main.cpp:708](D:/A-lab/AAC/fdk-aac/libAACenc/src/psy_main.cpp:708), [psy_main.cpp:933](D:/A-lab/AAC/fdk-aac/libAACenc/src/psy_main.cpp:933), [spreading.cpp:105](D:/A-lab/AAC/fdk-aac/libAACenc/src/spreading.cpp:105), [pre_echo_control.cpp:117](D:/A-lab/AAC/fdk-aac/libAACenc/src/pre_echo_control.cpp:117) |
| psy_grouping | Grouped offsets/min-SNR, cộng có saturation, rearrange spectrum, maxSfb và grouping mask | [grp_data.cpp:118](D:/A-lab/AAC/fdk-aac/libAACenc/src/grp_data.cpp:118), [psy_main.cpp:1053](D:/A-lab/AAC/fdk-aac/libAACenc/src/psy_main.cpp:1053) |
| psy_pns | Noise/fuzzy decisions, gap filling, tránh band đơn, noise energy, PNS pair và cập nhật threshold | [noisedet.cpp:150](D:/A-lab/AAC/fdk-aac/libAACenc/src/noisedet.cpp:150), [aacenc_pns.cpp:173](D:/A-lab/AAC/fdk-aac/libAACenc/src/aacenc_pns.cpp:173), [aacenc_pns.cpp:381](D:/A-lab/AAC/fdk-aac/libAACenc/src/aacenc_pns.cpp:381), [aacenc_pns.cpp:441](D:/A-lab/AAC/fdk-aac/libAACenc/src/aacenc_pns.cpp:441) |
| psy_stereo | Energy M/S, quyết định MS/Intensity, đổi phổ, cập nhật band/tool data | [ms_stereo.cpp:109](D:/A-lab/AAC/fdk-aac/libAACenc/src/ms_stereo.cpp:109), [intensity.cpp:258](D:/A-lab/AAC/fdk-aac/libAACenc/src/intensity.cpp:258), [intensity.cpp:614](D:/A-lab/AAC/fdk-aac/libAACenc/src/intensity.cpp:614) |
| psy_state | Threshold history, history scale, calcPreEcho và context theo stream/channel | [psy_data.h:141](D:/A-lab/AAC/fdk-aac/libAACenc/src/psy_data.h:141), [pre_echo_control.cpp:106](D:/A-lab/AAC/fdk-aac/libAACenc/src/pre_echo_control.cpp:106) |
| psy_math | Fixed-point/LZC/shift, log/exp, sqrt/invSqrt, division và reciprocal tables | [common_fix.h:238](D:/A-lab/AAC/fdk-aac/libFDK/include/common_fix.h:238), [fixpoint_math.cpp](../../../libFDK/src/fixpoint_math.cpp), [fixpoint_math.h](../../../libFDK/include/fixpoint_math.h) |
| psy_control / psy_output | Lịch nhiều lượt trên RAM, metadata, result packet và status | [psy_main.cpp:1263](D:/A-lab/AAC/fdk-aac/libAACenc/src/psy_main.cpp:1263), [interface.h:121](D:/A-lab/AAC/fdk-aac/libAACenc/src/interface.h:121) |

Các module là phân rã chức năng; chúng có thể chia sẻ arithmetic engine/RAM theo lịch phần cứng. Nạp config image lúc init không thực hiện quyết định Psy theo tín hiệu frame trên ARM.

~~~mermaid
flowchart LR
    FB["Filterbank output"] --> I["Spectrum + exponent + metadata"]
    subgraph PL["Toàn bộ psy-model trên PL"]
        I --> C["psy_control: lịch thực thi FDK"]
        C --> R["Spectrum / band / scratch RAM"]
        C --> E["Energy + scale"]
        C --> T["Tonality + toàn bộ TNS"]
        C --> M["Masking + pre-echo"]
        C --> G["Grouping + PNS + stereo"]
        E <--> A["MAC + special-math dùng chung"]
        T <--> A
        M <--> A
        G <--> A
        S["Context/state RAM"] <--> C
        R --> O["PSY_OUT packet"]
    end
    O --> Q["QC/coding trên PS"]
    PS["PS host control"] -->|"config / start / buffer control"| C
~~~

## 3. Special-math và quyết định công cụ

Full core dùng **FSM/vi chương trình phần cứng**, tự điều phối các phép toán và nhánh quyết định. Cụm MAC phục vụ energy/ACF/FIR; special-math engine bổ sung:

| Phép toán | Nơi sử dụng | Cách triển khai đề xuất |
|---|---|---|
| fLog2/CalcLdData, LdDataVector | Energy, masking, tonality, MS/PNS | Port thuật toán/bảng, sentinel và rounding của FDK |
| CalcInvLdData | Tương quan PNS channel pair | Exp2/table engine với scale của source |
| invSqrtNorm2 | Normalization ACF TNS | ROM và các bước số nguyên theo baseline |
| sqrtFixp, sqrt lồng nhau | Intensity loudness/scale | Engine sqrt theo FDK, dùng lại tuần tự |
| schur_div, fDivNorm, fDivNormSigned | Schur/LPC, prediction gain, Intensity | Divider normalized, số bước/bit đúng từng primitive |
| GetInvInt | Intensity/normalization | ROM chứa reciprocal của source |

Cần kiểm toán call graph và nhánh compile-time ARM trước khi chốt primitive. Các hàm chỉ tạo bảng lúc init như TNS ACF window có thể thành config image/ROM sinh trước; mọi phép toán phụ thuộc tín hiệu frame chạy trên PL.

Schur/LPC trong psy_tns phải bao gồm cả phép chia và cập nhật hệ số:

~~~cpp
tmp = (FIXP_DBL)((LONG)schur_div(tmp, acorr[0], FRACT_BITS) ^ (~sign));

reflCoeff[i] = FX_DBL2FX_LPC(tmp);

for (j = numOfCoeff - i - 1; j >= 0; j--) {
  FIXP_DBL accu1 = fMult(tmp, acorr[j]);
  FIXP_DBL accu2 = fMult(tmp, workBuffer[j]);
  workBuffer[j] += accu1;
  acorr[j] += accu2;
}
~~~

Nguồn: [FDK_lpc.cpp:461](D:/A-lab/AAC/fdk-aac/libFDK/src/FDK_lpc.cpp:461), dòng 461–470. Prediction gain còn dùng fDivNormSigned tại dòng 480 và đi vào quyết định TNS.

Tonality gồm phép log và các nhánh giới hạn, không chỉ cộng energy:

~~~cpp
chaosMeasureSfbLD64 = CalcLdData((chaosMeasureSfb)) - sfbEnergyLD64[i];
chaosMeasureSfbLD64 += FL2FXCONST_DBL(3.0f / 64) -
                       ((FIXP_DBL)(shiftBits) << (DFRACT_BITS - 6));
~~~

Nguồn: [tonality.cpp:202](D:/A-lab/AAC/fdk-aac/libAACenc/src/tonality.cpp:202), dòng 202–204; nhánh tonal/noise-like ở dòng 206–217 cũng thuộc PL. PNS/Intensity cần logic quyết định, gap filling, tương quan và sửa spectrum/threshold như source.

## 4. Lịch xử lý tự trị của một element

1. **LOAD:** nhận đủ spectrum 1/2 channel, exponent, metadata window/grouping và config/context ID; kiểm tra frame/sequence.
2. **SFB_ANALYSIS:** low-pass, zero detection, headroom, energy/log, chọn finalShift theo cả channel/window như source, rescale và threshold ban đầu.
3. **TONALITY:** tính long-window tonality theo cờ PNS; giữ kết quả cho PNS sau TNS.
4. **TNS_DETECT:** quarter scaling/ACF, normalize/window/merge, Schur, prediction gain, quantize ParCor, quyết định filter/order/merge; stereo thực hiện TNS sync trước lọc.
5. **TNS_APPLY:** Index2Parcor, ParcorToLpc, shift bảo vệ và FIR; tính lại headroom/energy/log, chọn tnsSpecShift và scale các channel đúng nhánh long/short.
6. **MASKING:** clip, spreading, PCM floor, pre-echo với history scale; spread energy bằng bộ hệ số riêng.
7. **GROUP_AND_LOG:** energy M/S khi stereo; short grouping hoặc tìm maxSfb long; grouped energy/threshold log, offsets và min-SNR.
8. **TOOLS:** PNS detection; stereo long chạy PNS pair preprocessing -> Intensity -> MS -> PNS pair postprocessing; short chạy Intensity -> MS; sau đó CodePnsChannel.
9. **PACK_RESULT:** tạo toàn bộ fields của PSY_OUT, result packet và state/status cuối.

Lịch bám theo [psy_main.cpp](../../../libAACenc/src/psy_main.cpp), dòng 589–1307: threshold ban đầu xuất hiện trước TNS, threshold hoàn chỉnh sau TNS. Cần giữ các phụ thuộc này khi chia engine.

Một command **PROCESS_ELEMENT** chạy từ LOAD tới PACK_RESULT. PS không gửi quyết định finalShift/LPC/PNS ở giữa job. Core chạy nhiều lượt nội bộ trên RAM, không giả định đọc spectrum đúng một lần. Lịch và API chi tiết được khóa trong đặc tả triển khai.

## 5. Memory, state và tài nguyên

| Vùng logic | Dự trù ban đầu | Ghi chú |
|---|---:|---|
| Spectrum L/R, 2x1024x32 | 8 KiB | Giữ tới lúc output xử lý xong |
| Temporary TNS spectrum | 4 KiB | Dùng lại theo channel |
| Grouping/output scratch L/R | 8 KiB | Kiểm tra lifetime khi chia sẻ |
| Chaos-measure temporary | 4 KiB | Có thể dùng lại sau tonality |
| Band/ACF/LPC/PNS/Intensity scratch | Tính từ từng source array | Short trước grouping: 8x15 slot/channel; grouped tối đa 60 |
| Pre-echo history | Khoảng 212 byte/channel cho 51 threshold word + scale + flag, chưa gồm metadata quản lý | Tách theo stream/channel |
| Config, math ROM, packet buffers | Theo config image/mapping | Không đồng nhất dung lượng logic với BRAM vật lý |

Budget exploration cho toàn core, chưa gồm filterbank/DMA: **32–64 DSP48E1 và 24–40 BRAM36**; LUT/FF lấy từ synthesis. Đây là mục tiêu thiết kế chưa có utilization chứng minh. Cần kiểm tra overlay tích hợp, điều chỉnh lane/time-multiplexing và banking để đáp ứng tài nguyên.

Tham số hóa **4/8 logical MAC lanes**, cùng special-math engine dùng chung. Một DSP48E1 có multiplier 25x18 và accumulator 48 bit; lane 32x32 cần partial products hoặc nhiều chu kỳ. Nhóm 8 lane tổng quát dự trù khoảng 32 DSP, sau đó tổng hợp thêm math/control để chốt số thật. [AMD DSP48E1](https://docs.amd.com/r/2024.1-English/ug953-vivado-7series-libraries/DSP48E1).

Bring-up ở **50 MHz** theo flow board đã ghi. Target 100 MHz cần pipeline/CDC và post-route timing riêng; tài liệu MDCT ghi target 100 MHz hiện chưa đạt WNS. [Nguồn timing](../../window_mdct/docs/huong_dan_trien_khai_mdct_pynq_z2.md), dòng 777–843. Cycle/latency full Psy còn phụ thuộc divider/log/sqrt, Schur/Intensity/PNS, RAM và stereo, nên phải đo trên RTL/corpus.

psy_state giữ sfbThresholdnm1, mdctScalenm1, calcPreEcho theo channel/context. Reset tái tạo InitPreEchoControl: threshold từ PCM floor, history scale theo PCM_QUANT_THR_SCALE >> 1 và calcPreEcho = 1. SHORT cập nhật history từng cửa sổ; START/STOP theo source. Job cùng context chạy đúng thứ tự, có quy tắc commit/error/abort để tránh xử lý lại frame đã commit. State snapshot cho debug/recovery là giao tiếp quản lý, không phải PS tính thuật toán Psy.

## 6. Giao diện filterbank -> Psy -> QC

| Hướng | Dữ liệu |
|---|---|
| Config/init | ID/version/checksum; SFB long/short; masking/min-SNR/PCM floor; TNS/PNS/Intensity tables, cờ công cụ |
| Input mỗi element | Job/frame/context/channel IDs; 1/2 spectrum; exponent mỗi channel; sequence/shape; groupLen/noOfGroups; commonWindow/isLFE |
| Output mỗi channel | Spectrum cuối/mdctScale; sfbCnt/sfbPerGroup/maxSfbPerGroup; offsets/groupLen/groupingMask/window; energy, energy log, threshold log, min-SNR log, spread energy; tnsInfo/noiseNrg/isBook/isScale |
| Output mỗi element | commonWindow/msMask/msDigest, status và độ dài packet |

**Xuất PSY_OUT dạng packet có layout/version xác định**, không DMA nguyên struct C chứa pointer. HAL giải packet, đặt dữ liệu vào buffer QC; HAL không tính lại energy/threshold hay chọn tool. Fields: [interface.h:121](D:/A-lab/AAC/fdk-aac/libAACenc/src/interface.h:121); buffer ownership: [aacenc.cpp:805](D:/A-lab/AAC/fdk-aac/libAACenc/src/aacenc.cpp:805).

SW filterbank cần gửi 4 KiB spectrum mono hoặc 8 KiB stereo. Output vẫn gồm toàn spectrum và mảng band/tool cho QC. Full core không yêu cầu snapshot trung gian về ARM để tính tonality/TNS/PNS. Khi filterbank ở PL, bổ sung handoff/arbitration spectrum RAM hoặc stream adapter; wrapper hiện tại chưa có sẵn đường stream/DMA này.

AXI4-Lite cho config/start/status; payload qua bulk stream/DMA hoặc giao diện memory đã chọn. DMA output cần TLAST đúng packet và driver xử lý buffer/cache tương ứng. [PYNQ DMA](https://pynq.readthedocs.io/en/latest/pynq_libraries/dma.html).

## 7. Tích hợp FDK và nghiệm thu

FDKaacEnc_psyMain hiện điều phối Block Switching, transform, low-pass và Psy. Full-PL path cần tách trách nhiệm:

- Input/filterbank chuẩn bị **raw spectrum trước low-pass** của toàn element và exponent riêng từng channel; Block Switching, window metadata và rotate/copy PCM history vẫn ở phía input/filterbank.
- psy_core tự xử lý các vòng low-pass/energy/TNS/masking/grouping/tools/output.
- HAL trả fields vào buffer Psy/QC rồi gọi QCMainPrepare; production full-PL path không chạy lại các bước Psy trên PS.

Các điểm source: [transform tại psy_main.cpp:576](D:/A-lab/AAC/fdk-aac/libAACenc/src/psy_main.cpp:576), [PCM history tại psy_main.cpp:623](D:/A-lab/AAC/fdk-aac/libAACenc/src/psy_main.cpp:623). Nhánh SW/SHADOW dùng làm oracle và phải tách rõ khỏi backend nghiệm thu.

| Mốc phát triển | Phần hoàn thành trên PL | Kiểm chứng |
|---|---|---|
| 1 | Arithmetic/special-math, config/RAM/controller | Golden ARM cho log/exp, sqrt/invSqrt, divider, shift/LZC, truncation/wrap/saturation |
| 2 | SFB/energy/scale/masking/pre-echo | Energy/log/threshold/history; silence, START/STOP và SHORT |
| 3 | Tonality và toàn bộ TNS | Chaos/tonality, ACF/ParCor/LPC, decisions, FIR và scale |
| 4 | Grouping/PNS/output mono đầy đủ | PSY_OUT mono và encode qua QC gốc |
| 5 | MS/Intensity/PNS pair/TNS sync | PSY_OUT stereo, L=R/L=-R, noise và transient một channel |
| 6 | HAL full-PL và overlay tích hợp | SW/SHADOW/PL; AAC bytes, DMA/context, post-route timing/resource |

Các mốc thuộc phương án full-PL; qua mốc mono chưa hoàn tất toàn khối có stereo. Emulator trên PS dùng trong bring-up không được tính là runtime PL hoàn chỉnh.

Baseline bit-exact lấy từ cùng ARM source/build/macros. Giữ primitive fixed-point, signed shift, bảng/sentinel, rounding và state. Mục tiêu **0 LSB** ở checkpoint và các fields có ý nghĩa của PSY_OUT; unused/padding chỉ so khi đã định nghĩa khởi tạo packet. Cuối cùng so AAC bytes với cùng encoder/config/transport và decode toàn stream. Xem [verification_plan.md](verification_plan.md) và [code gắn từng mô tả](psy_model_definition.md).

Artifact cũ [encoder_profile.csv](../../pynq_z2/output/z2_profile/encoder_profile.csv) cho Psy residual 221.970 µs/frame, 15.749% frame CPU time; loại bỏ lý tưởng residual cho giới hạn toàn encoder 1.187x. Đây là mốc lịch sử một input, không phải latency/speedup PL. Mục tiêu full-PL còn là chuyển toàn xử lý cảm nhận khỏi CPU; báo riêng cycle/latency core, CPU load và wall time tích hợp. Budget hệ thống gồm transfer/Psy/QC và chu kỳ frame 21.333 ms tại 48 kHz.
