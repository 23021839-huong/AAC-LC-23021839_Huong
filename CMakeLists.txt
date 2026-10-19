# # CMake project for fdk-aac
#
# ## Basic usage
#
# 1. Download and install CMake >= 3.10 (CMake >= 3.15 is recommended)
# 2. Clone fdk-aac repository
# 3. In fdk-aac directory create and go to `build` subdirectory:
#
#    mkdir build
#    cd build
#
# 4. Run cmake to configure project with desired build type (Release|Debug):
#
#    cmake .. -DCMAKE_BUILD_TYPE=Release
#
#    Note CMake configuration without CMAKE_BUILD_TYPE option will not set build
#    type to some default and it is most likely is not what you want.
#
#    If you want to build static (default is shared library), add BUILD_SHARED_LIBS=OFF option:
#
#    #    cmake .. -DBUILD_SHARED_LIBS=OFF
#
#    You can combine options as well:
#
#    cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF
#
# 5. Run cmake to build project:
#
#    cmake --build . -c Release

cmake_minimum_required(VERSION 3.10)

# Policies

## Enables CMAKE_MSVC_RUNTIME_LIBRARY option support for CMake >= 3.15
## if you want to use a MSVC multi-threaded statically-linked runtime library
## If you enable it, CMake will build fdk-acc.dll without external dependencies.
##
## Example usage:
##
## cmake .. -DCMAKE_MSVC_RUNTIME_LIBRARY="MultiThreaded$<$<CONFIG:Debug>:Debug>
if(POLICY CMP0091)
  cmake_policy(SET CMP0091 NEW)
endif()

project(fdk-aac VERSION 2.0.3)

# Includes

include(CheckFunctionExists)
include(CheckLibraryExists)
include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

if(CMAKE_VERSION VERSION_LESS 3.11)
  set(CPACK_PACKAGE_VERSION_MAJOR ${PROJECT_VERSION_MAJOR})
  set(CPACK_PACKAGE_VERSION_MINOR ${PROJECT_VERSION_MINOR})
  set(CPACK_PACKAGE_VERSION_PATCH ${PROJECT_VERSION_PATCH})
endif()
include(CPack)

# Options

option(BUILD_SHARED_LIBS "Build shared library" ON)
option(BUILD_PROGRAMS "Build extra utilities" OFF)
option(FDK_AAC_INSTALL_CMAKE_CONFIG_MODULE "Install CMake package configuration file" ON)
option(FDK_AAC_INSTALL_PKGCONFIG_MODULE "Install pkg-config .pc file" ON)
option(FDK_ENABLE_ENCODER_PROFILING "Profile AAC encoder blocks and write CSV" OFF)
option(MDCT_DEBUG "Observe the native AAC-LC Window/MDCT pipeline" OFF)
option(BUILD_MDCT_TRACE "Build the WAV encoder/MDCT trace utility" OFF)
option(PSY_DEBUG "Observe native AAC-LC psychoacoustic stages" OFF)
option(BUILD_PSY_TRACE "Build the native WAV/Psy survey runner" OFF)
option(QUANT_DEBUG "Observe native AAC-LC quantization and control" OFF)
option(BUILD_QUANT_TRACE "Build the native WAV/Quantization survey runner" OFF)
option(WINDOW_EXPERIMENT "Enable research-only AAC-LC window shape policies" OFF)
option(FFT_EXPERIMENT "Enable encoder-MDCT original/pure radix-2 research FFT" OFF)
option(PSY_EXPERIMENT "Enable research-only native Tonality/TNS controls" OFF)
option(BUILD_PSY_EXPERIMENT "Build the native Psy experiment runner" OFF)

# Checks

## Check if math functions are in separate library (Most of Linux distros, maybe some other OSes)
check_function_exists(sin HAVE_DEFAULT_MATH)
if(NOT HAVE_DEFAULT_MATH)
  check_library_exists(m sin "" HAVE_LIBM)
endif()

# Library

## Sources

set(AACDEC_SRC
  libAACdec/src/FDK_delay.cpp
  libAACdec/src/aac_ram.cpp
  libAACdec/src/aac_rom.cpp
  libAACdec/src/aacdec_drc.cpp
  libAACdec/src/aacdec_hcr.cpp
  libAACdec/src/aacdec_hcr_bit.cpp
  libAACdec/src/aacdec_hcrs.cpp
  libAACdec/src/aacdec_pns.cpp
  libAACdec/src/aacdec_tns.cpp
  libAACdec/src/aacdecoder.cpp
  libAACdec/src/aacdecoder_lib.cpp
  libAACdec/src/block.cpp
  libAACdec/src/channel.cpp
  libAACdec/src/channelinfo.cpp
  libAACdec/src/conceal.cpp
  libAACdec/src/ldfiltbank.cpp
  libAACdec/src/pulsedata.cpp
  libAACdec/src/rvlc.cpp
  libAACdec/src/rvlcbit.cpp
  libAACdec/src/rvlcconceal.cpp
  libAACdec/src/stereo.cpp
  libAACdec/src/usacdec_ace_d4t64.cpp
  libAACdec/src/usacdec_ace_ltp.cpp
  libAACdec/src/usacdec_acelp.cpp
  libAACdec/src/usacdec_fac.cpp
  libAACdec/src/usacdec_lpc.cpp
  libAACdec/src/usacdec_lpd.cpp
  libAACdec/src/usacdec_rom.cpp
  libAACdec/src/aac_ram.h
  libAACdec/src/aac_rom.h
  libAACdec/src/aacdec_drc.h
  libAACdec/src/aacdec_drc_types.h
  libAACdec/src/aacdec_hcr.h
  libAACdec/src/aacdec_hcr_bit.h
  libAACdec/src/aacdec_hcr_types.h
  libAACdec/src/aacdec_hcrs.h
  libAACdec/src/aacdec_pns.h
  libAACdec/src/aacdec_tns.h
  libAACdec/src/aacdecoder.h
  libAACdec/src/block.h
  libAACdec/src/channel.h
  libAACdec/src/channelinfo.h
  libAACdec/src/conceal.h
  libAACdec/src/conceal_types.h
  libAACdec/src/FDK_delay.h
  libAACdec/src/ldfiltbank.h
  libAACdec/src/overlapadd.h
  libAACdec/src/pulsedata.h
  libAACdec/src/rvlc.h
  libAACdec/src/rvlc_info.h
  libAACdec/src/rvlcbit.h
  libAACdec/src/rvlcconceal.h
  libAACdec/src/stereo.h
  libAACdec/src/usacdec_ace_d4t64.h
  libAACdec/src/usacdec_ace_ltp.h
  libAACdec/src/usacdec_acelp.h
  libAACdec/src/usacdec_const.h
  libAACdec/src/usacdec_fac.h
  libAACdec/src/usacdec_lpc.h
  libAACdec/src/usacdec_lpd.h
  libAACdec/src/usacdec_rom.h)

set(AACENC_SRC
  libAACenc/src/common/aacEnc_ram.cpp
  libAACenc/src/common/aacEnc_rom.cpp
  libAACenc/src/encoder/aacenc.cpp
  libAACenc/src/encoder/aacenc_lib.cpp
  libAACenc/src/profiling/aacenc_profile.cpp
  libAACenc/src/psy_model/aacenc_pns.cpp
  libAACenc/src/psy_model/aacenc_tns.cpp
  libAACenc/src/quantization/adj_thr.cpp
  libAACenc/src/psy_model/band_nrg.cpp
  libAACenc/src/encoder/bandwidth.cpp
  libAACenc/src/coding/bit_cnt.cpp
  libAACenc/src/coding/bitenc.cpp
  libAACenc/src/block_switch/block_switch.cpp
  libAACenc/src/encoder/channel_map.cpp
  libAACenc/src/psy_model/chaosmeasure.cpp
  libAACenc/src/coding/dyn_bits.cpp
  libAACenc/src/psy_model/grp_data.cpp
  libAACenc/src/psy_model/intensity.cpp
  libAACenc/src/quantization/line_pe.cpp
  libAACenc/src/extensions/metadata_compressor.cpp
  libAACenc/src/extensions/metadata_main.cpp
  libAACenc/src/extensions/mps_main.cpp
  libAACenc/src/psy_model/ms_stereo.cpp
  libAACenc/src/psy_model/noisedet.cpp
  libAACenc/src/psy_model/pnsparam.cpp
  libAACenc/src/psy_model/pre_echo_control.cpp
  libAACenc/src/psy_model/psy_configuration.cpp
  libAACenc/src/psy_model/psy_main.cpp
  libAACenc/src/quantization/qc_main.cpp
  libAACenc/src/quantization/quantize.cpp
  libAACenc/src/quantization/sf_estim.cpp
  libAACenc/src/psy_model/spreading.cpp
  libAACenc/src/psy_model/tonality.cpp
  libAACenc/src/filterbank/transform.cpp
  libAACenc/src/aacenc.h
  libAACenc/src/aacenc_profile.h
  libAACenc/src/aacenc_pns.h
  libAACenc/src/aacEnc_ram.h
  libAACenc/src/aacEnc_rom.h
  libAACenc/src/aacenc_tns.h
  libAACenc/src/adj_thr.h
  libAACenc/src/adj_thr_data.h
  libAACenc/src/band_nrg.h
  libAACenc/src/bandwidth.h
  libAACenc/src/bit_cnt.h
  libAACenc/src/bitenc.h
  libAACenc/src/block_switch.h
  libAACenc/src/channel_map.h
  libAACenc/src/chaosmeasure.h
  libAACenc/src/dyn_bits.h
  libAACenc/src/grp_data.h
  libAACenc/src/intensity.h
  libAACenc/src/interface.h
  libAACenc/src/line_pe.h
  libAACenc/src/metadata_compressor.h
  libAACenc/src/metadata_main.h
  libAACenc/src/mps_main.h
  libAACenc/src/ms_stereo.h
  libAACenc/src/noisedet.h
  libAACenc/src/pns_func.h
  libAACenc/src/pnsparam.h
  libAACenc/src/pre_echo_control.h
  libAACenc/src/psy_configuration.h
  libAACenc/src/psy_const.h
  libAACenc/src/psy_data.h
  libAACenc/src/psy_main.h
  libAACenc/src/qc_data.h
  libAACenc/src/qc_main.h
  libAACenc/src/quantize.h
  libAACenc/src/sf_estim.h
  libAACenc/src/spreading.h
  libAACenc/src/tns_func.h
  libAACenc/src/tonality.h
  libAACenc/src/transform.h)

set(ARITHCODING_SRC
  libArithCoding/src/ac_arith_coder.cpp)

set(DRCDEC_SRC
  libDRCdec/src/FDK_drcDecLib.cpp
  libDRCdec/src/drcDec_gainDecoder.cpp
  libDRCdec/src/drcDec_reader.cpp
  libDRCdec/src/drcDec_rom.cpp
  libDRCdec/src/drcDec_selectionProcess.cpp
  libDRCdec/src/drcDec_tools.cpp
  libDRCdec/src/drcGainDec_init.cpp
  libDRCdec/src/drcGainDec_preprocess.cpp
  libDRCdec/src/drcGainDec_process.cpp
  libDRCdec/src/drcDec_gainDecoder.h
  libDRCdec/src/drcDec_reader.h
  libDRCdec/src/drcDec_rom.h
  libDRCdec/src/drcDec_selectionProcess.h
  libDRCdec/src/drcDec_tools.h
  libDRCdec/src/drcDec_types.h
  libDRCdec/src/drcDecoder.h
  libDRCdec/src/drcGainDec_init.h
  libDRCdec/src/drcGainDec_preprocess.h
  libDRCdec/src/drcGainDec_process.h)

set(FDK_SRC
  libFDK/src/FDK_bitbuffer.cpp
  libFDK/src/FDK_core.cpp
  libFDK/src/FDK_crc.cpp
  libFDK/src/FDK_decorrelate.cpp
  libFDK/src/FDK_hybrid.cpp
  libFDK/src/FDK_lpc.cpp
  libFDK/src/FDK_matrixCalloc.cpp
  libFDK/src/FDK_qmf_domain.cpp
  libFDK/src/FDK_tools_rom.cpp
  libFDK/src/FDK_trigFcts.cpp
  libFDK/src/autocorr2nd.cpp
  libFDK/src/dct.cpp
  libFDK/src/fft.cpp
  libFDK/src/fft_rad2.cpp
  libFDK/src/fixpoint_math.cpp
  libFDK/src/huff_nodes.cpp
  libFDK/src/mdct.cpp
  libFDK/src/nlc_dec.cpp
  libFDK/src/qmf.cpp
  libFDK/src/scale.cpp)

set(MPEGTPDEC_SRC
  libMpegTPDec/src/tpdec_adif.cpp
  libMpegTPDec/src/tpdec_adts.cpp
  libMpegTPDec/src/tpdec_asc.cpp
  libMpegTPDec/src/tpdec_drm.cpp
  libMpegTPDec/src/tpdec_latm.cpp
  libMpegTPDec/src/tpdec_lib.cpp
  libMpegTPDec/src/tp_version.h
  libMpegTPDec/src/tpdec_adif.h
  libMpegTPDec/src/tpdec_adts.h
  libMpegTPDec/src/tpdec_drm.h
  libMpegTPDec/src/tpdec_latm.h)

set(MPEGTPENC_SRC
  libMpegTPEnc/src/tpenc_adif.cpp
  libMpegTPEnc/src/tpenc_adts.cpp
  libMpegTPEnc/src/tpenc_asc.cpp
  libMpegTPEnc/src/tpenc_latm.cpp
  libMpegTPEnc/src/tpenc_lib.cpp
  libMpegTPEnc/src/tp_version.h
  libMpegTPEnc/src/tpenc_adif.h
  libMpegTPEnc/src/tpenc_adts.h
  libMpegTPEnc/src/tpenc_asc.h
  libMpegTPEnc/src/tpenc_latm.h)

set(PCMUTILS_SRC
  libPCMutils/src/limiter.cpp
  libPCMutils/src/pcm_utils.cpp
  libPCMutils/src/pcmdmx_lib.cpp
  libPCMutils/src/version.h)

set(SACDEC_SRC
  libSACdec/src/sac_bitdec.cpp
  libSACdec/src/sac_calcM1andM2.cpp
  libSACdec/src/sac_dec.cpp
  libSACdec/src/sac_dec_conceal.cpp
  libSACdec/src/sac_dec_lib.cpp
  libSACdec/src/sac_process.cpp
  libSACdec/src/sac_qmf.cpp
  libSACdec/src/sac_reshapeBBEnv.cpp
  libSACdec/src/sac_rom.cpp
  libSACdec/src/sac_smoothing.cpp
  libSACdec/src/sac_stp.cpp
  libSACdec/src/sac_tsd.cpp
  libSACdec/src/sac_bitdec.h
  libSACdec/src/sac_calcM1andM2.h
  libSACdec/src/sac_dec.h
  libSACdec/src/sac_dec_conceal.h
  libSACdec/src/sac_dec_interface.h
  libSACdec/src/sac_dec_ssc_struct.h
  libSACdec/src/sac_process.h
  libSACdec/src/sac_qmf.h
  libSACdec/src/sac_reshapeBBEnv.h
  libSACdec/src/sac_rom.h
  libSACdec/src/sac_smoothing.h
  libSACdec/src/sac_stp.h
  libSACdec/src/sac_tsd.h)

set(SACENC_SRC
  libSACenc/src/sacenc_bitstream.cpp
  libSACenc/src/sacenc_delay.cpp
  libSACenc/src/sacenc_dmx_tdom_enh.cpp
  libSACenc/src/sacenc_filter.cpp
  libSACenc/src/sacenc_framewindowing.cpp
  libSACenc/src/sacenc_huff_tab.cpp
  libSACenc/src/sacenc_lib.cpp
  libSACenc/src/sacenc_nlc_enc.cpp
  libSACenc/src/sacenc_onsetdetect.cpp
  libSACenc/src/sacenc_paramextract.cpp
  libSACenc/src/sacenc_staticgain.cpp
  libSACenc/src/sacenc_tree.cpp
  libSACenc/src/sacenc_vectorfunctions.cpp
  libSACenc/src/sacenc_bitstream.h
  libSACenc/src/sacenc_const.h
  libSACenc/src/sacenc_delay.h
  libSACenc/src/sacenc_dmx_tdom_enh.h
  libSACenc/src/sacenc_filter.h
  libSACenc/src/sacenc_framewindowing.h
  libSACenc/src/sacenc_huff_tab.h
  libSACenc/src/sacenc_nlc_enc.h
  libSACenc/src/sacenc_onsetdetect.h
  libSACenc/src/sacenc_paramextract.h
  libSACenc/src/sacenc_staticgain.h
  libSACenc/src/sacenc_tree.h
  libSACenc/src/sacenc_vectorfunctions.h)

set(SBRDEC_SRC
  libSBRdec/src/HFgen_preFlat.cpp
  libSBRdec/src/env_calc.cpp
  libSBRdec/src/env_dec.cpp
  libSBRdec/src/env_extr.cpp
  libSBRdec/src/hbe.cpp
  libSBRdec/src/huff_dec.cpp
  libSBRdec/src/lpp_tran.cpp
  libSBRdec/src/psbitdec.cpp
  libSBRdec/src/psdec.cpp
  libSBRdec/src/psdec_drm.cpp
  libSBRdec/src/psdecrom_drm.cpp
  libSBRdec/src/pvc_dec.cpp
  libSBRdec/src/sbr_deb.cpp
  libSBRdec/src/sbr_dec.cpp
  libSBRdec/src/sbr_ram.cpp
  libSBRdec/src/sbr_rom.cpp
  libSBRdec/src/sbrdec_drc.cpp
  libSBRdec/src/sbrdec_freq_sca.cpp
  libSBRdec/src/sbrdecoder.cpp
  libSBRdec/src/env_calc.h
  libSBRdec/src/env_dec.h
  libSBRdec/src/env_extr.h
  libSBRdec/src/hbe.h
  libSBRdec/src/HFgen_preFlat.h
  libSBRdec/src/huff_dec.h
  libSBRdec/src/lpp_tran.h
  libSBRdec/src/psbitdec.h
  libSBRdec/src/psdec.h
  libSBRdec/src/psdec_drm.h
  libSBRdec/src/pvc_dec.h
  libSBRdec/src/sbr_deb.h
  libSBRdec/src/sbr_dec.h
  libSBRdec/src/sbr_ram.h
  libSBRdec/src/sbr_rom.h
  libSBRdec/src/sbrdec_drc.h
  libSBRdec/src/sbrdec_freq_sca.h
  libSBRdec/src/transcendent.h)

set(SBRENC_SRC
  libSBRenc/src/bit_sbr.cpp
  libSBRenc/src/code_env.cpp
  libSBRenc/src/env_bit.cpp
  libSBRenc/src/env_est.cpp
  libSBRenc/src/fram_gen.cpp
  libSBRenc/src/invf_est.cpp
  libSBRenc/src/mh_det.cpp
  libSBRenc/src/nf_est.cpp
  libSBRenc/src/ps_bitenc.cpp
  libSBRenc/src/ps_encode.cpp
  libSBRenc/src/ps_main.cpp
  libSBRenc/src/resampler.cpp
  libSBRenc/src/sbr_encoder.cpp
  libSBRenc/src/sbr_misc.cpp
  libSBRenc/src/sbrenc_freq_sca.cpp
  libSBRenc/src/sbrenc_ram.cpp
  libSBRenc/src/sbrenc_rom.cpp
  libSBRenc/src/ton_corr.cpp
  libSBRenc/src/tran_det.cpp
  libSBRenc/src/bit_sbr.h
  libSBRenc/src/cmondata.h
  libSBRenc/src/code_env.h
  libSBRenc/src/env_bit.h
  libSBRenc/src/env_est.h
  libSBRenc/src/fram_gen.h
  libSBRenc/src/invf_est.h
  libSBRenc/src/mh_det.h
  libSBRenc/src/nf_est.h
  libSBRenc/src/ps_bitenc.h
  libSBRenc/src/ps_const.h
  libSBRenc/src/ps_encode.h
  libSBRenc/src/ps_main.h
  libSBRenc/src/resampler.h
  libSBRenc/src/sbr.h
  libSBRenc/src/sbr_def.h
  libSBRenc/src/sbr_misc.h
  libSBRenc/src/sbrenc_freq_sca.h
  libSBRenc/src/sbrenc_ram.h
  libSBRenc/src/sbrenc_rom.h
  libSBRenc/src/ton_corr.h
  libSBRenc/src/tran_det.h)

set(SYS_SRC
  libSYS/src/genericStds.cpp
  libSYS/src/syslib_channelMapDescr.cpp)

set(fdk_aacinclude_HEADERS
  libSYS/include/machine_type.h
  libSYS/include/genericStds.h
  libSYS/include/FDK_audio.h
  libSYS/include/syslib_channelMapDescr.h
  libAACenc/include/aacenc_lib.h
  libAACdec/include/aacdecoder_lib.h)

set(libfdk_aac_SOURCES
    ${AACDEC_SRC} ${AACENC_SRC}
    ${ARITHCODING_SRC}
    ${DRCDEC_SRC}
    ${MPEGTPDEC_SRC} ${MPEGTPENC_SRC}
    ${SACDEC_SRC} ${SACENC_SRC}
    ${SBRDEC_SRC} ${SBRENC_SRC}
    ${PCMUTILS_SRC} ${FDK_SRC} ${SYS_SRC})

if(WIN32 AND BUILD_SHARED_LIBS)
  set(libfdk_aac_SOURCES ${libfdk_aac_SOURCES} fdk-aac.def)
endif()

## Create Library target. Actually fdk-aac is enough, but we also create
## FDK-AAC::fdk-aac for consistence with config-file package.

add_library(fdk-aac ${libfdk_aac_SOURCES})
add_library(FDK-AAC::fdk-aac ALIAS fdk-aac)
if(PSY_EXPERIMENT)
  target_sources(fdk-aac PRIVATE libAACenc/src/psy_model/psy_experiment.cpp)
  target_compile_definitions(fdk-aac PRIVATE PSY_EXPERIMENT=1)
  target_compile_features(fdk-aac PRIVATE cxx_std_17)
endif()
if(FFT_EXPERIMENT)
  target_sources(fdk-aac PRIVATE libFDK/src/fft_experiment.cpp)
  target_compile_definitions(fdk-aac PRIVATE FFT_EXPERIMENT=1 FDK_FFT_EXPERIMENT_BUILD=1)
  if(WIN32 AND BUILD_SHARED_LIBS)
    target_compile_definitions(fdk-aac PUBLIC FDK_FFT_EXPERIMENT_SHARED=1)
  endif()
endif()
if(WINDOW_EXPERIMENT)
  target_sources(fdk-aac PRIVATE libAACenc/src/block_switch/window_experiment.cpp)
  target_compile_definitions(fdk-aac PRIVATE WINDOW_EXPERIMENT=1 FDK_WINDOW_EXPERIMENT_BUILD=1)
  if(WIN32 AND BUILD_SHARED_LIBS)
    target_compile_definitions(fdk-aac PUBLIC FDK_WINDOW_EXPERIMENT_SHARED=1)
  endif()
endif()
if(QUANT_DEBUG)
  target_sources(fdk-aac PRIVATE libAACenc/src/quantization/quant_debug.cpp)
  target_compile_definitions(fdk-aac PRIVATE QUANT_DEBUG=1 FDK_QUANT_DEBUG_BUILD=1)
  if(WIN32 AND BUILD_SHARED_LIBS)
    target_compile_definitions(fdk-aac PUBLIC FDK_QUANT_DEBUG_SHARED=1)
  endif()
endif()
if(PSY_DEBUG)
  target_sources(fdk-aac PRIVATE libAACenc/src/psy_model/psy_debug.cpp)
  target_compile_definitions(fdk-aac PRIVATE PSY_DEBUG=1 FDK_PSY_DEBUG_BUILD=1)
  if(WIN32 AND BUILD_SHARED_LIBS)
    target_compile_definitions(fdk-aac PUBLIC FDK_PSY_DEBUG_SHARED=1)
  endif()
endif()

if(MDCT_DEBUG)
  target_sources(fdk-aac PRIVATE libFDK/src/mdct_debug.cpp)
  target_compile_definitions(fdk-aac PRIVATE MDCT_DEBUG=1 FDK_MDCT_DEBUG_BUILD=1)
  if(WIN32 AND BUILD_SHARED_LIBS)
    target_compile_definitions(fdk-aac PUBLIC FDK_MDCT_DEBUG_SHARED=1)
  endif()
endif()

if(FDK_ENABLE_ENCODER_PROFILING)
  target_compile_definitions(fdk-aac PRIVATE FDK_ENABLE_ENCODER_PROFILING=1)
endif()

## Library target configuration

### Library target includes
target_include_directories(fdk-aac
  PUBLIC
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/libAACdec/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/libAACenc/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/libSYS/include>
  PRIVATE
    libAACenc/src
    libArithCoding/include
    libDRCdec/include
    libSACdec/include
    libSACenc/include
    libSBRdec/include
    libSBRenc/include
    libMpegTPDec/include
    libMpegTPEnc/include
    libFDK/include
    libPCMutils/include)

### Link math library if required
target_link_libraries(fdk-aac PRIVATE $<$<BOOL:${HAVE_LIBM}>:m>)

### Set public headers and shared library version. Version info is critical for Unix-like OSes.
set_target_properties(fdk-aac PROPERTIES
  PUBLIC_HEADER "${fdk_aacinclude_HEADERS}"
  VERSION 2.0.3
  SOVERSION 2
  MACHO_COMPATIBILITY_VERSION 3.0.0
  MACHO_CURRENT_VERSION 3.3.0
  LINKER_LANGUAGE C)

### Some compiler options from Makefile.am
if(MSVC)
  target_compile_options(fdk-aac PRIVATE /EHsc)
else()
  target_compile_options(fdk-aac PRIVATE -fno-exceptions -fno-rtti)
endif()

if(FFT_EXPERIMENT)
  if(NOT WINDOW_EXPERIMENT)
    message(FATAL_ERROR "FFT_EXPERIMENT runner requires WINDOW_EXPERIMENT=ON to freeze window policy")
  endif()
  add_executable(fdk_fft_validate my_workspace/window_mdct/experiments/fft/tools/validate_fft.cpp)
  target_compile_features(fdk_fft_validate PRIVATE cxx_std_17)
  target_include_directories(fdk_fft_validate PRIVATE libFDK/include)
  target_link_libraries(fdk_fft_validate PRIVATE fdk-aac)
  add_executable(fdk_fft_experiment my_workspace/window_mdct/experiments/fft/tools/fdk_fft_experiment.cpp my_workspace/fdk_model_testing/tools/wav_pcm.cpp)
  target_compile_features(fdk_fft_experiment PRIVATE cxx_std_17)
  target_include_directories(fdk_fft_experiment PRIVATE libFDK/include libAACenc/src/block_switch my_workspace/fdk_model_testing/tools)
  target_link_libraries(fdk_fft_experiment PRIVATE fdk-aac)
  include(CTest)
  if(BUILD_TESTING)
    find_program(FFT_EXPERIMENT_PYTHON NAMES python3 python)
    if(FFT_EXPERIMENT_PYTHON)
      add_test(NAME fft_native_numerical_and_codec COMMAND "${FFT_EXPERIMENT_PYTHON}"
        "${CMAKE_CURRENT_SOURCE_DIR}/my_workspace/window_mdct/tests/fft_experiments/test_native_fft.py"
        --validator $<TARGET_FILE:fdk_fft_validate> --runner $<TARGET_FILE:fdk_fft_experiment>)
      add_test(NAME fft_pipeline_integration COMMAND "${FFT_EXPERIMENT_PYTHON}"
        "${CMAKE_CURRENT_SOURCE_DIR}/my_workspace/window_mdct/tests/fft_experiments/test_fft_pipeline.py"
        --validator $<TARGET_FILE:fdk_fft_validate> --runner $<TARGET_FILE:fdk_fft_experiment>)
    endif()
  endif()
  if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 9)
    target_link_libraries(fdk_fft_validate PRIVATE stdc++fs)
    target_link_libraries(fdk_fft_experiment PRIVATE stdc++fs)
  endif()
endif()

if(WINDOW_EXPERIMENT)
  add_executable(fdk_window_experiment my_workspace/window_mdct/experiments/tools/fdk_window_experiment.cpp my_workspace/fdk_model_testing/tools/wav_pcm.cpp)
  target_compile_features(fdk_window_experiment PRIVATE cxx_std_17)
  target_include_directories(fdk_window_experiment PRIVATE libAACenc/src/block_switch libFDK/include my_workspace/fdk_model_testing/tools)
  target_link_libraries(fdk_window_experiment PRIVATE fdk-aac)
  if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 9)
    target_link_libraries(fdk_window_experiment PRIVATE stdc++fs)
  endif()
  include(CTest)
  if(BUILD_TESTING)
    find_program(WINDOW_EXPERIMENT_PYTHON NAMES python3 python)
    if(WINDOW_EXPERIMENT_PYTHON)
      add_test(NAME window_native_integration COMMAND "${WINDOW_EXPERIMENT_PYTHON}"
        "${CMAKE_CURRENT_SOURCE_DIR}/my_workspace/window_mdct/tests/window_experiments/test_native_window.py"
        --binary $<TARGET_FILE:fdk_window_experiment>)
      add_test(NAME window_measurement_units COMMAND "${WINDOW_EXPERIMENT_PYTHON}"
        "${CMAKE_CURRENT_SOURCE_DIR}/my_workspace/window_mdct/tests/window_experiments/test_measurements.py")
      add_test(NAME window_pipeline_integration COMMAND "${WINDOW_EXPERIMENT_PYTHON}"
        "${CMAKE_CURRENT_SOURCE_DIR}/my_workspace/window_mdct/tests/window_experiments/test_pipeline.py"
        --binary $<TARGET_FILE:fdk_window_experiment>)
    endif()
  endif()
endif()

if(PSY_EXPERIMENT OR BUILD_PSY_EXPERIMENT)
  if(BUILD_SHARED_LIBS)
    message(FATAL_ERROR "Psy research runner requires BUILD_SHARED_LIBS=OFF")
  endif()
  if(PSY_DEBUG OR QUANT_DEBUG OR MDCT_DEBUG OR WINDOW_EXPERIMENT OR FFT_EXPERIMENT OR FDK_ENABLE_ENCODER_PROFILING)
    message(FATAL_ERROR "Psy experiment requires all other research/debug/profiling flags OFF")
  endif()
  add_executable(fdk_psy_experiment my_workspace/psychoacoustic_model/experiments/psy/tools/fdk_psy_experiment.cpp my_workspace/fdk_model_testing/tools/wav_pcm.cpp)
  target_compile_features(fdk_psy_experiment PRIVATE cxx_std_17)
  target_include_directories(fdk_psy_experiment PRIVATE libAACenc/src libFDK/include my_workspace/fdk_model_testing/tools)
  target_link_libraries(fdk_psy_experiment PRIVATE fdk-aac)
  if(PSY_EXPERIMENT)
    target_compile_definitions(fdk_psy_experiment PRIVATE PSY_EXPERIMENT=1)
  endif()
endif()

if(PSY_DEBUG OR BUILD_PSY_TRACE)
  add_executable(fdk_psy_trace my_workspace/psychoacoustic_model/tools/fdk_psy_trace.cpp my_workspace/fdk_model_testing/tools/wav_pcm.cpp)
  target_compile_features(fdk_psy_trace PRIVATE cxx_std_17)
  target_include_directories(fdk_psy_trace PRIVATE libAACenc/src libFDK/include my_workspace/fdk_model_testing/tools)
  target_link_libraries(fdk_psy_trace PRIVATE fdk-aac)
  if(PSY_DEBUG)
    target_compile_definitions(fdk_psy_trace PRIVATE PSY_DEBUG=1)
  endif()
  if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 9)
    target_link_libraries(fdk_psy_trace PRIVATE stdc++fs)
  endif()
endif()

if(QUANT_DEBUG OR BUILD_QUANT_TRACE)
  add_executable(fdk_quant_trace my_workspace/quantization_coding/tools/fdk_quant_trace.cpp my_workspace/fdk_model_testing/tools/wav_pcm.cpp)
  target_compile_features(fdk_quant_trace PRIVATE cxx_std_17)
  target_include_directories(fdk_quant_trace PRIVATE libAACenc/src libFDK/include my_workspace/fdk_model_testing/tools)
  target_link_libraries(fdk_quant_trace PRIVATE fdk-aac)
  if(QUANT_DEBUG)
    target_compile_definitions(fdk_quant_trace PRIVATE QUANT_DEBUG=1)
  endif()
  if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 9)
    target_link_libraries(fdk_quant_trace PRIVATE stdc++fs)
  endif()
endif()

# This runner always uses aacEncEncode(). Debug OFF also permits an independent
# build of the same runner for byte-for-byte bitstream comparison.
if(MDCT_DEBUG OR BUILD_MDCT_TRACE)
  add_executable(fdk_mdct_trace my_workspace/window_mdct/tools/fdk_mdct_trace.cpp my_workspace/fdk_model_testing/tools/wav_pcm.cpp)
  target_compile_features(fdk_mdct_trace PRIVATE cxx_std_17)
  target_include_directories(fdk_mdct_trace PRIVATE libFDK/include my_workspace/fdk_model_testing/tools)
  target_link_libraries(fdk_mdct_trace PRIVATE fdk-aac)
  if(MDCT_DEBUG)
    target_compile_definitions(fdk_mdct_trace PRIVATE MDCT_DEBUG=1)
  endif()
  if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 9)
    target_link_libraries(fdk_mdct_trace PRIVATE stdc++fs)
  endif()
  include(CTest)
  if(MDCT_DEBUG AND BUILD_TESTING)
    find_program(MDCT_TRACE_PYTHON NAMES python3 python)
    if(MDCT_TRACE_PYTHON)
      add_test(NAME mdct_trace_integration
        COMMAND "${MDCT_TRACE_PYTHON}" "${CMAKE_CURRENT_SOURCE_DIR}/my_workspace/window_mdct/tests/mdct_trace/test_mdct_trace.py"
          --binary $<TARGET_FILE:fdk_mdct_trace>)
      add_test(NAME mdct_plot_units
        COMMAND "${MDCT_TRACE_PYTHON}" "${CMAKE_CURRENT_SOURCE_DIR}/my_workspace/window_mdct/tests/mdct_trace/test_plot_mdct_stages.py")
    endif()
  endif()
endif()

### Set proper name for MinGW or Cygwin DLL

if((MINGW OR CYGWIN) AND BUILD_SHARED_LIBS)
  set_property(TARGET fdk-aac PROPERTY RUNTIME_OUTPUT_NAME fdk-aac-2)
endif()

## Library installation

### Note we export `fdk-aac-targets` to use with config-file package.
install(TARGETS fdk-aac EXPORT fdk-aac-targets
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR} COMPONENT BIN
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR} COMPONENT DEV
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR} COMPONENT DEV
  PUBLIC_HEADER DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/fdk-aac COMPONENT DEV)

### Configure and install pkg-config module.
if(FDK_AAC_INSTALL_PKGCONFIG_MODULE)
  set(prefix ${CMAKE_INSTALL_PREFIX})
  set(exec_prefix "\$\{prefix\}")
  set(libdir "\$\{exec_prefix\}/${CMAKE_INSTALL_LIBDIR}")
  set(includedir "\$\{prefix\}/${CMAKE_INSTALL_INCLUDEDIR}")
  set(PACKAGE_VERSION ${PROJECT_VERSION})
  if(HAVE_LIBM)
    if(BUILD_SHARED_LIBS)
      set(LIBS_PRIVATE "-lm")
    else()
      set(LIBS_PUBLIC "-lm")
    endif()
  endif()
  configure_file(fdk-aac.pc.in fdk-aac.pc @ONLY)
  install(
    FILES
      ${CMAKE_CURRENT_BINARY_DIR}/fdk-aac.pc
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)
endif()

### Configure and install config-file package. Something like pkg-config module, but for Windows.
if(FDK_AAC_INSTALL_CMAKE_CONFIG_MODULE)

  set(CMAKE_INSTALL_PACKAGEDIR ${CMAKE_INSTALL_LIBDIR}/cmake/fdk-aac)

  configure_package_config_file(fdk-aac-config.cmake.in ${CMAKE_CURRENT_BINARY_DIR}/fdk-aac-config.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_PACKAGEDIR})

  if(CMAKE_VERSION VERSION_LESS 3.11)
    write_basic_package_version_file(fdk-aac-config-version.cmake COMPATIBILITY SameMajorVersion)
  else()
    write_basic_package_version_file(fdk-aac-config-version.cmake COMPATIBILITY SameMinorVersion)
  endif()

  install(EXPORT fdk-aac-targets
    NAMESPACE FDK-AAC::
    DESTINATION ${CMAKE_INSTALL_PACKAGEDIR})
  install(
    FILES
      ${CMAKE_CURRENT_BINARY_DIR}/fdk-aac-config.cmake
      ${CMAKE_CURRENT_BINARY_DIR}/fdk-aac-config-version.cmake
    DESTINATION ${CMAKE_INSTALL_PACKAGEDIR})

endif()

# Programs

if(BUILD_PROGRAMS)

  ## Program sources

  set(aac_enc_SOURCES
    aac-enc.c
    wavreader.c
    wavreader.h)

  ## Program target
  add_executable(aac-enc ${aac_enc_SOURCES})

  ## Program target configuration
  target_link_libraries(aac-enc PRIVATE fdk-aac)
  target_compile_definitions(aac-enc PRIVATE $<$<BOOL:${MSVC}>:_CRT_SECURE_NO_WARNINGS>)
  if(WIN32)
    target_sources(aac-enc PRIVATE win32/getopt.h)
    target_include_directories(aac-enc PRIVATE win32)
  endif()

  ## Program target installation
  install(TARGETS aac-enc RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})


  ## Tool for testing the library
  set(test_encode_decode_SOURCES
    test-encode-decode.c
    wavreader.c
    wavreader.h
    sha1.c
    sha1.h)

  add_executable(test-encode-decode ${test_encode_decode_SOURCES})
  target_link_libraries(test-encode-decode PRIVATE fdk-aac)
endif()
