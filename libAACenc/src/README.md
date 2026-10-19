# Phân nhóm source AAC encoder

Các file CPP được tổ chức theo chức năng để đọc và tham chiếu mã nguồn.

| Nhóm | Số CPP | File |
|---|---:|---|
| encoder/ | 4 | [aacenc_lib.cpp](encoder/aacenc_lib.cpp), [aacenc.cpp](encoder/aacenc.cpp), [channel_map.cpp](encoder/channel_map.cpp), [bandwidth.cpp](encoder/bandwidth.cpp) |
| block_switch/ | 1 | [block_switch.cpp](block_switch/block_switch.cpp) |
| filterbank/ | 1 | [transform.cpp](filterbank/transform.cpp) |
| psy_model/ | 15 | [psy_main.cpp](psy_model/psy_main.cpp), [psy_configuration.cpp](psy_model/psy_configuration.cpp), [band_nrg.cpp](psy_model/band_nrg.cpp), [spreading.cpp](psy_model/spreading.cpp), [pre_echo_control.cpp](psy_model/pre_echo_control.cpp), [tonality.cpp](psy_model/tonality.cpp), [chaosmeasure.cpp](psy_model/chaosmeasure.cpp), [aacenc_tns.cpp](psy_model/aacenc_tns.cpp), [aacenc_pns.cpp](psy_model/aacenc_pns.cpp), [pnsparam.cpp](psy_model/pnsparam.cpp), [noisedet.cpp](psy_model/noisedet.cpp), [grp_data.cpp](psy_model/grp_data.cpp), [ms_stereo.cpp](psy_model/ms_stereo.cpp), [intensity.cpp](psy_model/intensity.cpp), [psy_debug.cpp](psy_model/psy_debug.cpp) |
| quantization/ | 5 | [qc_main.cpp](quantization/qc_main.cpp), [adj_thr.cpp](quantization/adj_thr.cpp), [line_pe.cpp](quantization/line_pe.cpp), [sf_estim.cpp](quantization/sf_estim.cpp), [quantize.cpp](quantization/quantize.cpp) |
| coding/ | 3 | [dyn_bits.cpp](coding/dyn_bits.cpp), [bit_cnt.cpp](coding/bit_cnt.cpp), [bitenc.cpp](coding/bitenc.cpp) |
| extensions/ | 3 | [metadata_main.cpp](extensions/metadata_main.cpp), [metadata_compressor.cpp](extensions/metadata_compressor.cpp), [mps_main.cpp](extensions/mps_main.cpp) |
| common/ | 2 | [aacEnc_rom.cpp](common/aacEnc_rom.cpp), [aacEnc_ram.cpp](common/aacEnc_ram.cpp) |
| profiling/ | 1 | [aacenc_profile.cpp](profiling/aacenc_profile.cpp) |
| **Tổng** | **35** | |

Header nội bộ vẫn nằm trực tiếp tại libAACenc/src. Mỗi CPP giữ nguyên nội dung khi chuyển thư mục.

- encoder: API, cấu hình và điều phối encoder.
- block_switch: transient, window sequence và đồng bộ cửa sổ.
- filterbank: Window/MDCT transform.
- psy_model: energy, masking, tonality, TNS/PNS, grouping và stereo.
- quantization: PE, bit allocation/rate control, scalefactor và lượng tử hóa.
- coding: sectioning, Huffman và ghi bitstream.
- extensions: metadata/DRC và MPEG Surround.
- common: bảng ROM và layout/cấp phát RAM dùng chung.
- profiling: timer, counter và xuất thống kê.

Phân nhóm file phản ánh chức năng chính; psy_main.cpp vẫn chứa lời gọi Block Switching/transform, còn qc_main.cpp vẫn gọi các helper coding để đếm bit.


`psy_debug.cpp` là sink quan sát mới, chỉ build khi `PSY_DEBUG=ON`; hướng dẫn tại [docs/psy_analysis.md](../../docs/psy_analysis.md). Các thuật toán native được giữ nguyên ngoài hook quan sát.
