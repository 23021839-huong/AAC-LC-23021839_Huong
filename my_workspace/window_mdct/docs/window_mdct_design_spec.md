# Đặc tả thiết kế RTL Window/MDCT cho AAC-LC

| Thuộc tính | Nội dung |
|---|---|
| Phiên bản tài liệu | 1.0 |
| Ngày lập | 2026-10-14 |
| Loại tài liệu | Đặc tả thiết kế hiện hữu, bám RTL (as-built) |
| Numerical profile | `FDK_AACLC_1024_Q31Q15_RAD2_V1` |
| Top-level biến đổi | `rtl/mdct_core.vhd` |
| Top-level ngoại vi | `board/pynq_z2/mdct_axi_lite.vhd` |
| FPGA triển khai mặc định | PYNQ-Z2, `xc7z020clg400-1` |
| Golden baseline | `golden/radix2_q31_v1/` |

Tài liệu mô tả **thiết kế đang có**, không yêu cầu bổ sung DMA, nhiều context
kênh hoặc thay đổi thuật toán. Những hướng nâng cấp được tách riêng tại mục 15.
Các từ **phải**, **không được** và **chỉ khi** biểu thị hợp đồng bắt buộc khi
sử dụng hoặc sửa đổi thiết kế.

Đường dẫn trong tài liệu được tính từ thư mục `window_mdct/`. Khi có khác biệt
giữa tài liệu và mã nguồn, phải xác minh RTL, numerical profile và golden trước
khi sửa tài liệu hoặc thiết kế; không được tự đổi hợp đồng số học.

## 1. Mục tiêu và phạm vi

### 1.1. Mục tiêu chức năng

Khối chuyển một snapshot PCM miền thời gian thành phổ MDCT dùng trong encoder
AAC-LC, với frame length bằng 1024 và số học tương thích đường generic Q15-table
của FDK-AAC.

| ID | Yêu cầu |
|---|---|
| FR-01 | Mỗi frame phải nhận đúng 2048 mẫu PCM signed 16-bit. |
| FR-02 | Mỗi frame phải tạo đúng 1024 mantissa signed 32-bit và một exponent chung. |
| FR-03 | Phải hỗ trợ `LONG`, `START`, `SHORT`, `STOP`. |
| FR-04 | Phải hỗ trợ cửa sổ `SINE` và `KBD`, gồm history shape/slope giữa các transform. |
| FR-05 | Output phải theo thứ tự tự nhiên của FDK; SHORT phải ghép tám miền 128 hệ số theo thứ tự sub-transform tăng dần. |
| FR-06 | Kết quả phải bit-exact với profile đã khóa; sai số chấp nhận đối với golden fixed-point là 0 LSB. |

### 1.2. Thành phần trong phạm vi

- Analysis window kết hợp TDAC fold.
- DCT-IV pre-rotation và packing.
- Forward FFT radix-2 phức 64/512 điểm.
- DCT-IV post-rotation và ordering.
- Bộ nhớ snapshot, work, FFT, cache và spectrum.
- Controller frame/sub-transform và history cửa sổ một kênh.
- AXI4-Lite adapter phục vụ điều khiển, bring-up và regression trên PYNQ-Z2.

### 1.3. Thành phần ngoài phạm vi

BlockSwitch, PCM ring buffer, giao diện ADC/I2S, psychoacoustic, TNS, quantizer,
bitstream formatter, decoder/IMDCT, AAC-ELD và các chức năng HE-AAC như SBR/PS
không thuộc khối này. DMA, AXI-Stream, double-buffer và context nhiều kênh cũng
chưa được triển khai trong giao diện hiện tại.

## 2. Thông số cố định và mã hóa

| Thông số | Giá trị |
|---|---:|
| Frame length AAC | 1024 mẫu |
| Snapshot length | 2048 mẫu |
| Long transform length `L` | 1024 |
| Short transform length `L` | 128 |
| Số short transform/frame | 8 |
| FFT length `M = L/2` | 512 hoặc 64 |
| PCM | signed Q1.15, 16 bit |
| Dữ liệu transform/mantissa | signed Q1.31, 32 bit |
| Hệ số window/rotation/twiddle | signed Q1.15, 16 bit |
| PCM address | unsigned 11 bit |
| Spectrum/work address | unsigned 10 bit |
| FFT address | unsigned 9 bit |
| Output exponent | unsigned 5 bit |
| Clock domain | Một miền clock |
| Frame đồng thời đang xử lý | Tối đa một |
| Context history | Một kênh |

Các độ rộng này là thuộc tính của profile, không phải cấu hình tùy ý. Generic
`DATA_W` của FFT phải bằng 32 trong thiết kế này.

| `block_type[1:0]` | Tên | Chức năng |
|---|---|---|
| `00` | `LONG` | Một biến đổi dài |
| `01` | `START` | Một biến đổi dài với right slope ngắn |
| `10` | `SHORT` | Tám biến đổi ngắn |
| `11` | `STOP` | Một biến đổi dài với right slope dài, left slope lấy từ history |

`right_shape='0'` chọn `SINE`; `right_shape='1'` chọn `KBD`.
`size_mode='0'` chọn FFT-64/DCT-IV-128; `size_mode='1'` chọn FFT-512/DCT-IV-1024.
Mã block phải trùng `WINDOW_SEQUENCE` của FDK-AAC.

## 3. Kiến trúc phần cứng

```text
                         block_type / right_shape / start
                                      |
                                      v
                               mdct_control
                           geometry / start / done
                                      |
PCM loader -> PCM RAM -> Window/Fold -> Work RAM -> DCT-IV pre
                                                       |
                                                       v
                                            FFT radix-2 ping-pong
                                                       |
                                                       v
Spectrum read <- Spectrum RAM <- DCT-IV post <- FFT cache
```

Kiến trúc là iterative multi-engine. Controller chạy tuần tự các pha
`FOLD -> PRE -> FFT -> POST_LOAD -> POST`; SHORT lặp cùng datapath tám lần.
Không có pipeline chồng lấp xử lý hai frame.

| Module | Trách nhiệm |
|---|---|
| `mdct_core` | Kết nối controller, engine, memory và adapter đọc FFT sang post |
| `mdct_control` | Kiểm tra snapshot, chốt metadata, tạo geometry, chạy FSM và giữ history |
| `mdct_window_fold` | Sinh địa chỉ PCM/window, window và TDAC fold |
| `mdct_dct4_pre` | Lưu vector fold, pre-rotation, phát complex stream vào FFT |
| `fft_radix2_core` | Forward FFT radix-2 với scaling cố định |
| `mdct_dct4_post` | Lưu FFT bins, post-rotation và phát scalar output |
| `mdct_axi_lite` | Thanh ghi MMIO, lệnh, cờ sticky và chuyển giao dịch tới core |

## 4. Giao diện `mdct_core`

### 4.1. Clock, reset và generic

| Tín hiệu/generic | Chiều | Đặc tả |
|---|---|---|
| `clk` | in | Clock duy nhất; giao dịch nhận tại cạnh lên |
| `rst_n` | in | Reset bất đồng bộ, active-low |
| `ENABLE_TRACE` | generic | Boolean, mặc định `false`; bật khi kiểm chứng boundary |

**IF-01:** Reset phải được giữ thấp qua ít nhất một cạnh lên clock. Việc nhả
reset ở cấp hệ thống phải bảo đảm recovery/removal; nên dùng reset được nhả
đồng bộ theo clock tương ứng. Flow PYNQ dùng reset của hệ thống AXI.

Trong reset, `pcm_ready`, `busy`, `done`, `spec_rd_valid` phải bằng 0. History
bị vô hiệu và frame đang nạp/xử lý bị hủy. RAM không cần xóa; nội dung RAM sau
reset không được xem là một frame hợp lệ. Nguồn phải giữ `pcm_valid`, `start`
và `spec_rd_en` ở 0 khi reset và chỉ phát giao dịch sau khi nhả reset.

### 4.2. Nạp snapshot PCM

| Port | Chiều | Độ rộng | Ý nghĩa |
|---|---|---:|---|
| `pcm_valid` | in | 1 | Mẫu đang được trình bày |
| `pcm_ready` | out | 1 | Core có thể nhận mẫu và index hiện tại |
| `pcm_index` | in | 11 | Chỉ số tự nhiên 0..2047 |
| `pcm_data` | in | 16 | PCM signed Q1.15 |

**IF-02:** Giao dịch được nhận tại cạnh lên khi
`pcm_valid='1' and pcm_ready='1'`. Nguồn phải giữ valid/index/data ổn định khi
chưa được nhận. Chỉ số phải liên tục từ 0 đến 2047; không được lặp, bỏ hoặc
đổi thứ tự. Core hỗ trợ nạp một mẫu mỗi clock và cho phép có khoảng nghỉ.

`pcm_ready` chỉ lên khi controller ở pha load, chưa đủ snapshot, không reset
và index bằng chỉ số đang chờ. Index unknown hoặc sai thứ tự làm ready xuống.
Sau khi mẫu 2047 được nhận, nguồn phải hạ `pcm_valid`; không được gửi mẫu thừa.
Không được nạp PCM mới trong lúc core xử lý transform.

Core không giữ PCM history theo frame. Scheduler phải tự tạo snapshot gồm
1024 mẫu lịch sử và 1024 mẫu mới, đúng với vị trí frame trong encoder. Với
stream liên tục, snapshot kế tiếp thông thường dịch 1024 mẫu so với snapshot
trước. Zero-padding lúc khởi động/kết thúc stream do hệ thống bên ngoài xử lý.

### 4.3. Lệnh frame và trạng thái

| Port | Chiều | Độ rộng | Ý nghĩa |
|---|---|---:|---|
| `start` | in | 1 | Xung lệnh một clock |
| `block_type` | in | 2 | Loại block của snapshot |
| `right_shape` | in | 1 | Shape cửa sổ bên phải |
| `clear_history` | in | 1 | Vô hiệu history khi ở pha load |
| `busy` | out | 1 | Core đang xử lý frame |
| `done` | out | 1 | Xung một clock khi frame hoàn tất |
| `mdct_exp` | out | 5 | Exponent chung của spectrum |

**IF-03:** `start` chỉ hợp lệ sau khi đã nhận đủ 2048 mẫu, controller đã trở về
pha load và `pcm_valid='0'`. Không được trùng với mẫu PCM cuối hoặc một frame
đang chạy; không được giữ cao nhiều clock.

Core chốt `block_type`, `right_shape` tại cạnh nhận lệnh. Metadata phải là giá
trị nhị phân hợp lệ và ổn định trước cạnh đó; được phép đổi sau khi nhận lệnh.

`busy` lên sau cạnh nhận `start`, giữ 1 qua toàn bộ sub-transform và xuống 0
trong chu kỳ `done`. **`busy=0` không có nghĩa là `start_ready`**: nó cũng bằng
0 trong pha nạp dở snapshot và chu kỳ `S_DONE`. Core không có cổng start-ready
hoặc bộ đếm số mẫu công khai; scheduler phải theo dõi các giao dịch đã nhận.

**IF-04:** `done=1` xác nhận đủ 1024 hệ số đã ghi spectrum. Scheduler phải chốt
`mdct_exp` cùng frame output. `mdct_exp` bằng 12 cho LONG/START/STOP, bằng 9 cho
SHORT; không dùng exponent mặc định sau reset làm kết quả hợp lệ.

Ở giao diện core, `clear_history` có hiệu lực trong pha load và không xóa số
mẫu đã nạp. Nếu cao cùng `start`, frame đó dùng cold-start. Muốn hủy snapshot
nạp dở hoặc transform đang chạy phải reset, không dùng `clear_history`.

### 4.4. Đọc spectrum

| Port | Chiều | Độ rộng | Ý nghĩa |
|---|---|---:|---|
| `spec_rd_en` | in | 1 | Yêu cầu đọc đồng bộ |
| `spec_rd_index` | in | 10 | Chỉ số tự nhiên 0..1023 |
| `spec_rd_valid` | out | 1 | Response của yêu cầu đọc |
| `spec_rd_data` | out | 32 | Mantissa signed Q1.31 |

**IF-05:** Cổng đọc có một tầng đăng ký: yêu cầu được lấy mẫu tại cạnh lên và
data/valid tương ứng xuất hiện sau cạnh đó, tức latency một tầng clock, không
phải đọc tổ hợp. Có thể phát yêu cầu liên tục, một bin mỗi clock. Cổng không
có response-ready; bên nhận phải thu mọi response hợp lệ.

Spectrum chỉ được xem là kết quả frame sau `done`. Scheduler phải thu đủ
output trước `start` frame kế tiếp. Nạp PCM không trực tiếp ghi spectrum, nhưng
post engine của frame kế tiếp sẽ ghi đè spectrum vì chỉ có một bank output.

Giá trị diễn giải theo numerical profile là:

```text
X[k] = signed(spec[k]) * 2^mdct_exp / 2^31
```

Không được bỏ exponent hoặc tự đổi Q-format khi nối với đường quantizer FDK.

### 4.5. Trace kiểm chứng

| Nhóm | Port chính | Giao dịch được quan sát |
|---|---|---|
| Sub-transform | `trace_sub_index` | Chỉ số q=0..7 hiện hành |
| Fold | `trace_fold_valid/index/data` | Scalar fold đã phát |
| Pre | `trace_pre_valid/index/re/im` | Complex sample đã được FFT nhận |
| FFT output | `trace_fft_valid/index/re/im` | Bin FFT được chuyển sang post loader |
| Post | `trace_post_valid/index/data` | Scalar đã được ghi spectrum |
| FFT stage | `trace_fft_stage_valid/last`, `trace_fft_stage`, `trace_fft_addr_a/b`, `trace_fft_a/b_re/im` | Hai output của butterfly sau pipeline |

Trace chỉ hợp lệ khi valid tương ứng bằng 1. `trace_sub_index` xác định
sub-transform của các boundary trong frame SHORT. Khi `ENABLE_TRACE=false`,
mọi output trace phải bằng 0; logic chỉ phục vụ trace được phép loại khi
tổng hợp. Trace không phải giao diện dữ liệu production.

## 5. Geometry và history cửa sổ

### 5.1. Geometry của từng block

| Block | Số transform | L | FFT M | Input base | Output base | Right slope fr | Exponent |
|---|---:|---:|---:|---:|---:|---:|---:|
| LONG | 1 | 1024 | 512 | 0 | 0 | 1024 | 12 |
| START | 1 | 1024 | 512 | 0 | 0 | 128 | 12 |
| SHORT | 8 | 128 | 64 | `448 + 128*q` | `128*q` | 128 | 9 |
| STOP | 1 | 1024 | 512 | 0 | 0 | 1024 | 12 |

**GE-01:** Với SHORT, q chạy từ 0 đến 7. Transform q dùng 256 mẫu cục bộ tại
`snapshot[448+128*q .. 703+128*q]`, tạo 128 hệ số và ghi vào
`spec[128*q .. 128*q+127]`. Các vùng input chồng lấn; vùng output không chồng
lấn. Với block dài, dùng toàn snapshot và ghi `spec[0..1023]`.

### 5.2. History

**GE-02:** Controller lưu `prev_shape`, `prev_slope_len`, `history_valid`:

1. Nếu history hợp lệ, left shape/slope của transform lấy từ right shape/slope
   transform trước.
2. Nếu history chưa hợp lệ hoặc `clear_history=1` tại lệnh, left shape/slope
   bằng right shape/slope của transform hiện tại, đúng cold-start FDK.
3. Sau mỗi sub-transform hoàn tất, right state hiện tại trở thành history.
4. Với SHORT q>0, left state lấy từ short transform ngay trước đó.
5. Reset vô hiệu history; core không có cổng đọc/ghi trực tiếp context này.

Left slope của LONG/START/STOP không được suy ra chỉ từ tên block; nó phụ thuộc
history. Vì vậy cold-start START hoặc STOP không nhất thiết có left slope như
một chuỗi AAC chuyển tiếp thông thường.

Core không kiểm tra đầy đủ chuỗi block hợp lệ của AAC. Scheduler/BlockSwitch
phải cung cấp chuỗi phù hợp, ví dụ:

```text
LONG -> START -> SHORT -> SHORT -> ... -> STOP -> LONG
```

Không được xen kẽ nhiều kênh trên một history mà vẫn giả định bit-exact từng
kênh. `clear_history` mỗi lần đổi kênh không thay thế save/restore context.

## 6. Hợp đồng số học

### 6.1. Quy tắc cơ bản

**NUM-01:** Số học phải giữ đúng statement ordering của profile FDK:

```text
wrap32(v)          = lấy 32 bit thấp, diễn giải signed two's-complement
add32(a,b)         = wrap32(a+b)
sub32(a,b)         = wrap32(a-b)
neg32(a)           = wrap32(-a)
mulDiv2(a,c)       = wrap32(ASR(signed32(a) * signed16(c), 16))
fMult(a,c)         = wrap32(mulDiv2(a,c) << 1)
pcmShift15(x)      = signed32(x) << 15
pcmProduct(x,c)    = signed16(x) * signed16(c), kết quả signed 32 bit
```

`ASR` là dịch phải số học. Q31 x Q15 dùng tích signed 48-bit; từng tích phải
truncate trước phép cộng/trừ bao quanh. `fMult` không được thay bằng dịch phải
15 bit trực tiếp vì có thể khác LSB. Không round-to-nearest, không saturation.

Các phép cộng/trừ dùng độ rộng mở rộng khi RTL yêu cầu; wrap được áp dụng tại
đúng boundary chỉ định. Đặc biệt, stage 1 FFT cộng A+B ở 33 bit trước khi ASR;
không được wrap tổng xuống 32 bit trước phép dịch đó.

### 6.2. Window và TDAC fold

Xét một transform cục bộ có 2L mẫu `x[]`, bắt đầu tại input base. Đặt:

```text
H  = L/2
fl = left_slope_len
fr = right_slope_len
nl = (L-fl)/2
nr = (L-fr)/2
```

**NUM-02:** Vector fold phải tương đương bốn miền của `mdct_block()`:

```text
u[H+i]        = neg32(pcmShift15(x[L-1-i]))                  i=0..nl-1
u[H+nl+i]     = sub32(x[nl+i]*wL.im, x[L-nl-i-1]*wL.re)     i=0..fl/2-1
u[H-1-i]      = neg32(pcmShift15(x[L+i]))                    i=0..nr-1
u[H-nr-i-1]   = neg32(add32(x[L+nr+i]*wR.re,
                            x[2L-nr-i-1]*wR.im))           i=0..fr/2-1
```

Các tích ở đây là PCM Q15 x hệ số Q15, trả thẳng signed 32-bit. `wL[i]` và
`wR[i]` là cặp hệ số FDK của shape/slope tương ứng. Miền có chiều dài 0 được
bỏ qua. Fold phải phát index tự nhiên 0..L-1 và exponent bằng 2.

### 6.3. DCT-IV pre-rotation

**NUM-03:** Với m=0..M-1, M=L/2:

```text
t = 2*m                 nếu m < M/2
t = 2*(M-1-m)+1         nếu m >= M/2
a = u[L-1-t]
b = u[t]
c_re = sub32(mulDiv2(a,cos_t), mulDiv2(b,sin_t))
c_im = add32(mulDiv2(a,sin_t), mulDiv2(b,cos_t))
z[m].re = ASR(c_im,1)
z[m].im = ASR(c_re,1)                nếu m < M/2
z[m].im = neg32(ASR(c_re,1))         nếu m >= M/2
```

Hệ số dùng SineWindow1024 hoặc SineWindow128 đã khóa. Stream vào FFT phải
theo index tự nhiên 0..M-1. Pre đóng góp thêm 2 bit exponent, đưa exponent
tích lũy từ 2 lên 4.

### 6.4. FFT radix-2

**NUM-04:** FFT thuận dùng kernel `exp(-j*2*pi*k*n/M)`, pure radix-2 DIT.
Input/output ở thứ tự tự nhiên; bit-reversal chỉ là chi tiết lưu trữ nội bộ.

| FFT | Số stage | Scale mask theo stage 1..log2(M) | Exponent FFT |
|---|---:|---|---:|
| 512 | 9 | `101111111` | 8 |
| 64 | 6 | `101111` | 5 |

Mỗi stage có M/2 butterfly. Với stage s:

```text
m_stage = 2^s
half    = m_stage/2
addr_a  = group_base + j
addr_b  = addr_a + half
phase   = j * 2^(9-s), trên lưới FFT-512
```

Quy tắc butterfly, áp dụng cho từng thành phần complex:

- Stage 1: `top=wrap32(ASR(A+B,1))`, `bot=sub32(top,B)`.
- Stage 2: không scale; `top=add32(A,B*W)`, `bot=sub32(A,B*W)` với W chính xác
  bằng 1 hoặc -j.
- Stage 3 trở đi: `U=ASR(A,1)`, `T=complexMulDiv2(B,W)`,
  `top=add32(U,T)`, `bot=sub32(U,T)`.

Nhánh W=1 phải bypass phép nhân hệ số 0x7FFF. Nhánh W=-j phải giữ đúng thứ tự
dịch phải rồi đổi dấu khi stage có scale. Với twiddle khác, dấu cos được áp
dụng sau truncate từng tích magnitude, không được tự đổi vị trí phép đổi dấu.

FFT dùng hai bank ping-pong: bank nguồn đọc hai operand, bank đích ghi hai
output. Chỉ đổi bank khi butterfly cuối của stage đã được ghi. Pipeline hiện
tại nhận một butterfly mỗi clock trong pha issue.

### 6.5. DCT-IV post-rotation

**NUM-05:** Post không tăng exponent. Đặt `h=0x5A82`, biểu diễn Q15 của
sqrt(1/2), và M=L/2:

```text
y[0]     = z[0].re
y[L-1]   = neg32(z[0].im)
y[M-1]   = sub32(fMult(z[M/2].re,h), fMult(z[M/2].im,h))
y[M]     = add32(fMult(z[M/2].re,h), fMult(z[M/2].im,h))
```

Với i=1..M/2-1, dùng hệ số w_i từ SineTable1024:

```text
high = complexFMult(z[M-i], w_i)
low  = complexFMult(z[i].im + j*z[i].re, w_i)
y[2*i-1]   = high.re
y[2*i]     = low.im
y[L-1-2*i] = neg32(low.re)
y[L-2*i]   = high.im
```

`complexFMult` phải truncate từng tích theo `fMult` trước khi add/sub.
Stride trên bảng FDK là 2 cho L=1024, 16 cho L=128. ROM compact lưu mỗi entry
thứ hai, nên stride địa chỉ nội bộ tương ứng là 1 và 8. Output post phải phát
theo index tự nhiên 0..L-1.

### 6.6. Exponent và ROM

| Boundary | LONG/START/STOP | SHORT |
|---|---:|---:|
| Fold | 2 | 2 |
| Sau pre | 4 | 4 |
| Sau FFT | 12 | 9 |
| Post/spectrum | 12 | 9 |

**NUM-06:** ROM phải giữ literal FDK đã khóa, không tái lượng tử hóa bằng sin/cos
float trong quá trình tổng hợp. Golden contract lưu tại
`golden/radix2_q31_v1/contract.meta` và `checksums.sha256`, với FDK snapshot:

```text
35f9c13cb6df0c5d4e7ba958ef2d251c48b8d1d9
```

Mọi thay đổi có chủ ý về width, coefficient, rounding, saturation, scaling,
direction hoặc ordering phải tạo numerical profile/golden version mới.

## 7. FSM và giao tiếp nội bộ

### 7.1. FSM frame

| Trạng thái | Hoạt động | Điều kiện chuyển |
|---|---|---|
| `S_LOAD` | Nhận snapshot, xử lý clear-history | Start hợp lệ |
| `S_FOLD_START` | Phát fold-start một clock | Sang fold-wait |
| `S_FOLD_WAIT` | Đợi fold | `fold_done=1` |
| `S_PRE_START` | Phát pre-start một clock | Sang pre-wait |
| `S_PRE_WAIT` | Đợi pre/FFT loader nhận đủ input | `pre_done=1` |
| `S_FFT_START` | Phát FFT-start một clock | Sang FFT-wait |
| `S_FFT_WAIT` | Đợi FFT | `fft_done=1` |
| `S_POST_LOAD` | Đọc FFT, nạp cache post | Đủ M response được nhận |
| `S_POST_START` | Phát post-start một clock | Sang post-wait |
| `S_POST_WAIT` | Đợi post, cập nhật history | Transform kế tiếp hoặc frame-done |
| `S_DONE` | Phát done một clock | Xóa load-count, trở về load |

### 7.2. Hợp đồng engine

**INT-01:** Fold là stream không có backpressure. Pre loader phải ready suốt
pha fold. `mdct_core` có assertion khi fold-valid gặp pre-not-ready.

Pre phát ready/valid đến FFT. Khi FFT-ready thấp, pre phải giữ valid, index,
real và imag ổn định. Pre-done chỉ lên khi complex sample cuối được nhận.

Adapter FFT-to-post phát tối đa một yêu cầu đọc mỗi clock, gắn tag index theo
latency RAM. Post loader phải duy trì ready trong pha nạp; response đồng bộ
đang pending không được mất. Post-load-done chỉ lên sau đủ M bin đã nhận.

Post có ready/valid output; done chỉ lên khi scalar cuối được nhận. Trong
`mdct_core`, post-ready được nối cố định bằng 1 và mỗi sample được ghi spectrum.
Pre/post hiện dùng chuỗi fetch -> calculate -> hold-output: khi không stall,
mỗi engine phát một output tương ứng mỗi ba clock.

Start một engine khi bận, đổi mode khi đang load/compute hoặc completion lệch
trạng thái là vi phạm hợp đồng nội bộ.

## 8. Tổ chức bộ nhớ

| Bộ nhớ | Kích thước logic | Cổng/pha sử dụng |
|---|---:|---|
| PCM RAM | 2048 x 16 bit | Port A load hoặc read-A; port B read-B cho fold |
| Work RAM | 1024 x 32 bit | Port A fold-write hoặc pre-read-A; port B pre-read-B |
| FFT bank 0/1 | 2 x 512 x 64 bit | Hai cổng/bank; source đọc, destination ghi |
| FFT cache | 512 x 64 bit | Ghi complex bin, đọc complex operand cho post |
| Spectrum RAM | 1024 x 32 bit | Ghi scalar post, đọc đồng bộ bên ngoài |

Một complex word 64-bit đóng gói real ở [63:32], imag ở [31:0]. Tổng dung lượng
RAM dữ liệu logic là 196.608 bit, tương đương 24 KiB, chưa gồm ROM và thanh ghi.
SHORT chỉ dùng một phần RAM work/FFT/cache nhưng không đổi kích thước vật lý.

**MEM-01:** RAM đọc đồng bộ; valid phải cùng latency với dữ liệu và tag.
Không được reset toàn mảng RAM trong datapath. Load/compute phải tuân theo các
pha không chồng lấn và hai bank FFT phải khác nhau khi đồng thời đọc/ghi stage.

Số RAMB36/RAMB18, DSP, LUT, FF thực tế phải lấy từ báo cáo tổng hợp/route của
đúng phiên bản RTL và FPGA; dung lượng logic hoặc `ram_style="block"` không
phải bằng chứng tự thân rằng inference đã đạt.

## 9. Giao diện AXI4-Lite trên PYNQ-Z2

### 9.1. Cấu hình bus

| Thuộc tính | Giá trị |
|---|---|
| Bus | AXI4-Lite slave, không burst |
| Data width | 32 bit bắt buộc |
| Address width | Mặc định 6, tối thiểu 6 bit |
| Clock | `s_axi_aclk`, cũng cấp trực tiếp cho core |
| Reset adapter | `s_axi_aresetn`, active-low, lấy mẫu đồng bộ tại cạnh lên |
| Reset core bên trong | Cùng tín hiệu, tác động bất đồng bộ theo RTL core |
| Clock overlay mặc định | 50 MHz |
| Base address mặc định | `0x43C00000` |
| Segment block design | 64 KiB |

**AXI-01:** AW và W phải được đệm độc lập; commit chỉ khi đã nhận đủ cả hai.
BVALID và RVALID/data phải được giữ ổn định khi master backpressure. Adapter
giữ tối đa một B response và một R response pending; không coi đây là giao
diện bulk streaming.

BRESP/RRESP luôn là OKAY (`00`), kể cả lỗi trình tự phần mềm. Lỗi trình tự được
báo qua `STATUS.ERROR`, không qua SLVERR. Địa chỉ thanh ghi được giải mã bằng
bits [5:2]; không được dựa vào các địa chỉ cao hoặc không word-aligned để truy
cập tài nguyên khác. Segment 64 KiB không có nghĩa là có RAM MMIO 64 KiB.

### 9.2. Register map

| Offset | Register | Truy cập | Ý nghĩa |
|---|---|---|---|
| `0x00` | CONTROL | R/W | Metadata và command |
| `0x04` | STATUS | R | Trạng thái và cờ sticky |
| `0x08` | PCM_INDEX | R | Index PCM kế tiếp, tự tăng |
| `0x0C` | PCM_DATA | R/W | Ghi một mẫu; đọc mẫu issue gần nhất |
| `0x10` | SPEC_INDEX | R/W | Index spectrum cho request tiếp theo |
| `0x14` | SPEC_DATA | R | Response spectrum gần nhất |
| `0x18` | MDCT_EXP | R | Exponent trong [4:0] |
| `0x1C` | ID | R | `0x4D444354`, ASCII MDCT |
| `0x20` | PCM_COUNT | R | Số mẫu core đã nhận trong [11:0], 0..2048 |

Các bit không định nghĩa đọc 0. Trong các word offset chưa định nghĩa của vùng
64-byte, ghi không có tác dụng, đọc trả 0. Ghi PCM_INDEX có strobe khác 0 là
lỗi; register này không phải cổng đặt lại bộ đếm loader.

### 9.3. CONTROL

| Bit | Tên | Hành vi |
|---|---|---|
| 0 | START | Write-one pulse, phát lệnh frame nếu đủ điều kiện |
| 1 | CLEAR_HISTORY | Qualifier của START hợp lệ, không phải command độc lập |
| 2 | SPEC_READ | Write-one pulse, yêu cầu một hệ số |
| 3 | CLEAR_FLAGS | Write-one pulse, xóa DONE/SPEC_VALID/ERROR |
| 9:8 | BLOCK_TYPE | Metadata R/W |
| 10 | RIGHT_SHAPE | Metadata R/W |

Command bit không được lưu; đọc CONTROL chỉ trả metadata. Phần mềm nên phát
command tách biệt để tránh phụ thuộc thứ tự cập nhật các cờ trong cùng clock.

**AXI-02:** START chỉ được chấp nhận khi frame không active, không PCM pending,
không spectrum pending và PCM_COUNT=2048. START cùng SPEC_READ bị từ chối và
đặt ERROR. Khi nhận START, adapter đặt frame-active, xóa DONE/SPEC_VALID và
đưa PCM_COUNT về 0; điều này không cho phép nạp frame mới khi còn active.

**AXI-03:** SPEC_READ chỉ được chấp nhận khi không active, không spectrum
pending và DONE=1. Adapter chốt index request, tự tăng SPEC_INDEX modulo 1024,
đặt pending và xóa SPEC_VALID. Khi response về, adapter chốt SPEC_DATA, xóa
pending và đặt SPEC_VALID. Đọc SPEC_DATA không tự xóa valid.

CLEAR_HISTORY chỉ được đưa xuống core nếu đi cùng START được chấp nhận.
CLEAR_FLAGS không xóa PCM_COUNT, không hủy frame và không xóa history. Sau
CLEAR_FLAGS làm DONE xuống 0, SPEC_READ bị chặn cho tới khi một frame mới done.

### 9.4. STATUS và LED

| STATUS bit | Tên | Điều kiện/hành vi |
|---|---|---|
| 0 | PCM_READY | Không active, không PCM pending, PCM_COUNT<2048 |
| 1 | ACTIVE | Adapter frame-active hoặc core-busy |
| 2 | DONE | Sticky khi core hoàn tất frame |
| 3 | SPEC_VALID | SPEC_DATA chứa response request gần nhất |
| 4 | ERROR | Sticky lỗi trình tự/giao thức |
| 5 | PCM_PENDING | Mẫu PCM đang chờ core nhận |
| 6 | SPEC_PENDING | Spectrum request đang chờ response |

LED [0..3] lần lượt hiển thị PCM_READY, ACTIVE, DONE, ERROR. Reset xóa các cờ
sticky, bộ đếm, request pending và history core.

### 9.5. Byte strobe và lỗi

**AXI-04:** `WSTRB=0000` phải được acknowledge mà không có tác dụng phụ.
PCM_DATA là mẫu nguyên tử: cần `WSTRB[1:0]=11`. Ghi thiếu một trong hai byte
thấp phải đặt ERROR và không enqueue mẫu. Register metadata/index hỗ trợ merge
theo từng byte được enable.

ERROR được đặt khi start sai thời điểm, start cùng spec-read, spec-read chưa
done/đang active/đang pending, ghi PCM_INDEX, ghi PCM lúc không sẵn sàng/thừa
mẫu/thiếu byte, hoặc đổi SPEC_INDEX khi spectrum request pending.

Phần mềm phải kiểm tra ERROR; OKAY trên AXI không xác nhận command đã được
chấp nhận. Một snapshot dở dang không có lệnh abort mềm; phục hồi cần reset.

## 10. Trình tự vận hành hệ thống

### 10.1. Giao diện core

1. Reset hợp lệ; chuẩn bị snapshot và metadata đúng frame/kênh.
2. Nạp 2048 giao dịch PCM, tăng index chỉ sau mỗi lần valid/ready được nhận.
3. Hạ PCM-valid; phát start một clock với metadata ổn định.
4. Chờ done; chốt exponent của frame.
5. Đọc đủ 1024 spectrum response, giữ nguyên thứ tự hoặc lưu theo index.
6. Chỉ phát start frame kế tiếp sau khi đã thu xong output frame trước.

### 10.2. Giao diện MMIO

1. Kiểm tra ID và trạng thái sau reset.
2. Ghi CONTROL metadata; xóa cờ cũ khi bắt đầu quy trình frame mới.
3. Với từng mẫu: chờ PCM_READY, kiểm tra ERROR, ghi PCM_DATA.
4. Xác nhận PCM_COUNT=2048, không PCM_PENDING.
5. Ghi START cùng metadata; thêm CLEAR_HISTORY chỉ khi cần cold-start.
6. Chờ DONE, kiểm tra ERROR; không giả định busy=0 là đã có output hợp lệ.
7. Đặt SPEC_INDEX=0. Với mỗi bin: ghi SPEC_READ, chờ SPEC_VALID, đọc SPEC_DATA.
8. Đọc/chốt MDCT_EXP trước start frame mới; chuyển spectrum và exponent sang
   phần xử lý AAC bên ngoài.

Core không kiểm tra snapshot có chồng lấn đúng hoặc metadata có thuộc đúng
PCM frame. Đây là trách nhiệm của scheduler/ring buffer/BlockSwitch.

## 11. Latency, clock và timing

### 11.1. Latency thuật toán của RTL hiện tại

**PERF-01:** Khi không reset và không có stall nội bộ, latency tính theo clock
của kiến trúc hiện tại là:

```text
M    = L/2
Cfft = log2(M) * (M/2 + 5)
Csub = 6*L + Cfft + 11
```

Đối với frame, đo từ cạnh nhận start đến cạnh làm done lên 1:

| Frame | Latency | Tại 50 MHz | Tại 100 MHz, chỉ quy đổi lý thuyết |
|---|---:|---:|---:|
| LONG/START/STOP | 8504 clock | 170,08 us | 85,04 us |
| SHORT, đủ tám transform | 8008 clock | 160,16 us | 80,08 us |

Nạp liên tục cần thêm 2048 clock; đọc spectrum cần 1024 yêu cầu. Các số trên
không gồm giao dịch AXI, MMIO, polling, scheduling hoặc trao đổi DDR/CPU. Không
được dùng latency transform để đại diện cho latency end-to-end.

### 11.2. Constraint và trạng thái triển khai

| Flow | Mục đích | Clock |
|---|---|---|
| `synth/vivado_mdct_runtime.tcl` | Characterization core, out-of-context | Target 100 MHz, XDC 10 ns |
| `synth/vivado_pynq_z2_bitstream.tcl` | Overlay PS/AXI/core trên PYNQ-Z2 | Mặc định 50 MHz; có override MDCT_FCLK_MHZ |

`synth/mdct_core.xdc` đặt uncertainty 0,2 ns và I/O budget 2 ns cho
characterization standalone; không được đọc bởi flow overlay.

**PERF-02:** Chỉ công bố đạt tần số khi post-route setup/hold slack không âm,
không có internal path quan trọng unconstrained và DRC được kiểm tra. Flow
overlay phải chặn export khi kiểm tra setup/hold hoặc internal timing coverage
không đạt; không được dùng bitstream vi phạm timing để nghiệm thu chức năng.

Tài liệu triển khai đã lưu kết quả target 100 MHz WNS=-5,139 ns, tương ứng
Fmax ước lượng khoảng 66,05 MHz. Đây là số liệu lịch sử trong
`docs/huong_dan_trien_khai_mdct_pynq_z2.md`, không phải timing được đo lại khi
lập spec. **100 MHz là target characterization, chưa phải khả năng đã đạt.**
50 MHz là lựa chọn mặc định, không tự thân chứng minh mọi bản build đều đạt.

### 11.3. Real-time cấp hệ thống

Với 48 kHz, chu kỳ một frame 1024 mẫu là khoảng 21,33 ms. Latency compute tại
50 MHz nhỏ hơn thời hạn này, nhưng hệ thống dùng Python/MMIO hiện tại không
được mặc định coi là encoder real-time.

Log lưu trong `build/results/20260916T043158_506237Z/frames.csv` có 54 frame,
total wall-time trung vị khoảng 181,969 ms/frame, gồm MMIO/polling. Đây là kết
quả của cấu hình phần mềm/overlay đã thử, không phải giới hạn cứng của AXI4-Lite
hay phép đo mới. Real-time end-to-end phải được nghiệm thu riêng với đường
truyền dữ liệu và workload encoder thực tế.

## 12. Kiểm chứng và tiêu chí nghiệm thu

### 12.1. Regression hiện có

Baseline gồm ba case, mỗi case sáu frame:

```text
LONG -> LONG -> START -> SHORT -> STOP -> LONG
shape: SINE, KBD, SINE, KBD, SINE, KBD
```

Case gồm zero-transition, impulse-boundaries và extrema/PRNG. Tổng cộng 18
frame, 39 sub-transform và 18.432 hệ số cuối. Corpus có manifest và checksum;
testbench baseline hiện vẫn cố định số case/frame và chuỗi metadata.

| ID | Tiêu chí nghiệm thu | Bằng chứng/công cụ |
|---|---|---|
| VER-01 | Analyze/elaborate toàn bộ core và wrapper thành công | GHDL, `tools/run_bringup_sim.py` |
| VER-02 | Fold, pre, mọi stage FFT, FFT output, post và final khớp 0 LSB | `tb/tb_mdct_core.vhd` |
| VER-03 | Output count/order và exponent đúng mọi mode baseline | Core/AXI testbench và golden |
| VER-04 | Qua AXI khớp 18 frame; AW/W độc lập, B/R backpressure, lỗi đã kiểm thử đúng | `tb/tb_mdct_axi_lite.vhd` |
| VER-05 | C++ fixed model, Python integer model và FDK gốc tương đương profile | Reference/equivalence flow trong tài liệu kiểm chứng |
| VER-06 | Timing, inference RAM/DSP và resource phù hợp FPGA đích | Báo cáo synthesis/post-route của đúng build |

Lệnh regression hiện có, chạy từ `window_mdct/`:

```sh
python tools/run_bringup_sim.py --build-dir build/spec_validation
```

GHDL dùng `--std=08 -frelaxed-rules` vì template true-dual-port RAM dùng shared
variable không protected. Warning liên quan template/attribute phải được phân
biệt với lỗi số học hoặc giao thức; không tự thay template mà bỏ kiểm tra BRAM
inference trong Vivado.

### 12.2. Trạng thái bằng chứng khi lập spec

- Regression GHDL đã chạy lại ngày 2026-10-14: native core PASS tại mọi boundary
  0 LSB; AXI wrapper PASS 18 frame/18.432 bins 0 LSB.
- Có log thử phần cứng ngày 2026-09-16 trong `build/results/`, gồm lần 54 frame
  không mismatch. Log lưu hash overlay/golden, nhưng không thay thế việc xác
  nhận RTL hiện tại tương ứng đúng overlay đó.
- Không chạy lại Vivado hoặc board trong lần lập spec này. Không công bố số
  resource/timing mới.

So sánh NumPy phục vụ kiểm tra toán học, không thay thế bit-exact golden.
`tools/compare_rtl_numpy.py` tạo DCT-IV float từ fold integer và hiện không có
ngưỡng sai số quyết định exit code. Vì vậy chữ PASS của script này chỉ xác nhận
đã hoàn tất so sánh, không tự chứng minh toàn bộ window/MDCT float oracle độc
lập hoặc một ngưỡng chất lượng đã đạt.

### 12.3. Độ phủ cần bổ sung trước nghiệm thu mở rộng

Các trường hợp sau chưa được chứng minh đầy đủ bởi baseline và phải được kiểm
tra nếu nghiệm thu reset-recovery, tích hợp streaming hoặc nâng cấp datapath:

- Reset giữa fold/pre/FFT/post và khi RAM/AXI response pending.
- SHORT liên tiếp, cold-start ở các mode và nhiều tổ hợp history/shape hợp lệ.
- PCM-valid có khoảng nghỉ; kiểm riêng pre/post với ready stall ngẫu nhiên.
- Độ rộng xung done/busy và latency MDCT chính xác theo từng mode.
- Corpus mở rộng qua RTL, không chỉ qua reference hoặc board runner.
- Chuỗi frame dài ở cấp encoder, gồm khởi động, flush và metadata/snapshot.

Các mục này là công việc kiểm chứng còn cần làm, không phải tuyên bố RTL đã có
lỗi hoặc đã pass các tình huống đó.

## 13. Ma trận truy vết yêu cầu

| Nhóm yêu cầu | Source thực hiện | Kiểm tra chính |
|---|---|---|
| FR-01, IF-02 | `rtl/mdct_control.vhd`, `rtl/mdct_pcm_memory.vhd` | Nạp/count/index PCM |
| FR-02, FR-05, IF-04/05 | `rtl/mdct_core.vhd`, `rtl/mdct_spectrum_memory.vhd` | Count/order/final spectrum/exponent |
| FR-03/04, GE-01/02 | `rtl/mdct_control.vhd`, `rtl/mdct_pkg.vhd` | Chuỗi mode/shape và sub-transform |
| NUM-01 | `rtl/mdct_pkg.vhd`, `fft_radix2_core/rtl/fft_radix2_pkg.vhd` | Integer boundary golden |
| NUM-02 | `rtl/mdct_window_fold.vhd`, `rtl/mdct_window_rom.vhd` | Fold golden |
| NUM-03 | `rtl/mdct_dct4_pre.vhd`, `rtl/mdct_rotation_rom.vhd` | Pre golden |
| NUM-04 | `fft_radix2_core/rtl/` | Mọi FFT stage/final golden |
| NUM-05 | `rtl/mdct_dct4_post.vhd`, `rtl/mdct_rotation_rom.vhd` | Post/final golden |
| NUM-06, FR-06 | `golden/radix2_q31_v1/`, `ref/` | Profile/checksum/FDK equivalence |
| IF-01, INT-01 | Core/controller/engine và wrapper | Reset/handshake assertions, test bổ sung |
| MEM-01 | `rtl/mdct_*_memory.vhd`, FFT memory | Response/tag và RAM inference |
| AXI-01..04 | `board/pynq_z2/mdct_axi_lite.vhd` | AXI testbench |
| PERF-01/02 | RTL và `synth/` | Cycle count, timing/resource reports |

## 14. Giới hạn vận hành bắt buộc phải công bố

1. Chỉ AAC-LC frame length 1024; không phải MDCT configurable mọi chiều dài.
2. Một frame đang compute và một history context; chưa time-multiplex nhiều
   kênh một cách trong suốt.
3. Không có double-buffer PCM/spectrum hoặc overlap compute hai frame.
4. Không có DMA, AXI-Stream, FIFO bulk hay interrupt trong wrapper hiện tại.
5. Core dựa trên hợp đồng scheduler; assertion mô phỏng không phải phần cứng
   báo lỗi production. Với vi phạm giao thức core, kết quả/phục hồi không được
   bảo đảm. Adapter chỉ chặn/báo các lỗi nó có kiểm tra.
6. Clear-flags/history không phải abort; recovery snapshot/transform dở cần
   reset và nạp lại.
7. Không công bố 100 MHz đạt timing hoặc encoder real-time từ kết quả simulation
   và latency compute đơn thuần.

## 15. Hướng nâng cấp ngoài baseline

Các hướng sau cần spec thay đổi riêng và không phải tính năng của bản hiện tại:

- AXI-Stream/DMA hoặc shared memory để giảm overhead truyền PCM/spectrum.
- Context history theo channel hoặc nhân bản core cho stereo.
- Pipeline theo critical path để đạt target clock cao hơn, giữ nguyên truncate.
- Double-buffer khi hệ thống thực sự cần overlap và đã định nghĩa ownership.
- Regression manifest-driven, reset/stall randomized và float acceptance gate.

Không cần đổi radix hoặc viết lại MDCT chỉ để xử lý overhead Python/MMIO.
Mọi tối ưu phải giữ numerical contract, hoặc công bố profile mới nếu chủ ý
thay đổi kết quả.

## 16. Tài liệu tham chiếu

- [Đặc tả chi tiết core](mdct_core.md).
- [Đặc tả AXI4-Lite](dac_ta_mdct_axi_lite.md).
- [Luồng thuật toán](mdct_workflow.md).
- [Quyết định numerical profile và kiến trúc](phattrien.md).
- [Reference model và golden](window_mdct_reference_model.md).
- [Đặc tả FFT dùng chung](../fft_radix2_core/docs/dactafftcor.md).
- [Bring-up và regression PYNQ-Z2](pynq_z2_bringup.md).
- [Hướng dẫn triển khai và số liệu timing đã lưu](huong_dan_trien_khai_mdct_pynq_z2.md).
- [Tích hợp vào encoder AAC-LC](tich_hop_aac_lc_encoder.md).
