/* -----------------------------------------------------------------------------
Third-Party Modified Version of the Fraunhofer FDK AAC Codec Library.
Encoder profiling instrumentation added in 2026.
----------------------------------------------------------------------------- */

#ifndef AACENC_PROFILE_H
#define AACENC_PROFILE_H

#include <stdint.h>

typedef enum {
  FDK_ENC_PROFILE_FRAME_TOTAL = 0,
  FDK_ENC_PROFILE_PSY_TOTAL,
  FDK_ENC_PROFILE_BLOCK_SWITCHING,
  FDK_ENC_PROFILE_WINDOW_MDCT,
  FDK_ENC_PROFILE_BAND_ENERGY_SCALING,
  FDK_ENC_PROFILE_TONALITY,
  FDK_ENC_PROFILE_TNS,
  FDK_ENC_PROFILE_THRESHOLD_SPREADING,
  FDK_ENC_PROFILE_PSY_TOOLS,
  FDK_ENC_PROFILE_QC_PREPARE,
  FDK_ENC_PROFILE_QC_TOTAL,
  FDK_ENC_PROFILE_ADJUST_THRESHOLDS,
  FDK_ENC_PROFILE_SCALE_FACTOR_ESTIMATION,
  FDK_ENC_PROFILE_IMPROVE_SCF,
  FDK_ENC_PROFILE_ASSIMILATE_SINGLE_SCF,
  FDK_ENC_PROFILE_ASSIMILATE_MULTIPLE_SCF,
  FDK_ENC_PROFILE_ASSIMILATE_MULTIPLE_SCF2,
  FDK_ENC_PROFILE_CALC_SFB_DIST,
  FDK_ENC_PROFILE_CALC_SFB_QUANT_ENERGY_DIST,
  FDK_ENC_PROFILE_RATE_CONTROL,
  FDK_ENC_PROFILE_QUANTIZE_AND_MAX_SFB,
  FDK_ENC_PROFILE_HUFFMAN_BIT_COUNT,
  FDK_ENC_PROFILE_SECTION_MERGE,
  FDK_ENC_PROFILE_CRASH_RECOVERY,
  FDK_ENC_PROFILE_QC_FINALIZE,
  FDK_ENC_PROFILE_BITSTREAM_WRITE,
  FDK_ENC_PROFILE_BLOCK_COUNT
} FDK_ENCODER_PROFILE_BLOCK;

typedef enum {
  FDK_ENC_PROFILE_COUNTER_QMAX_SCANS = 0,
  FDK_ENC_PROFILE_COUNTER_QMAX_LINES,
  FDK_ENC_PROFILE_COUNTER_DISTORTION_TRIALS,
  FDK_ENC_PROFILE_COUNTER_DISTORTION_TRIAL_LINES,
  FDK_ENC_PROFILE_COUNTER_QUANT_ENERGY_CALLS,
  FDK_ENC_PROFILE_COUNTER_QUANT_ENERGY_LINES,
  FDK_ENC_PROFILE_COUNTER_GAIN_RETRIES,
  FDK_ENC_PROFILE_COUNTER_SECTION_MERGE_SEARCHES,
  FDK_ENC_PROFILE_COUNTER_SECTION_MERGE_OPERATIONS,
  FDK_ENC_PROFILE_COUNTER_RECOVERY_CALLS,
  FDK_ENC_PROFILE_COUNTER_OUTPUT_BYTES,
  FDK_ENC_PROFILE_COUNTER_WINDOW_LONG,
  FDK_ENC_PROFILE_COUNTER_WINDOW_START,
  FDK_ENC_PROFILE_COUNTER_WINDOW_SHORT,
  FDK_ENC_PROFILE_COUNTER_WINDOW_STOP,
  FDK_ENC_PROFILE_COUNTER_COUNT
} FDK_ENCODER_PROFILE_COUNTER;

#if defined(FDK_ENABLE_ENCODER_PROFILING)

typedef struct {
  uint64_t wallNanoseconds;
  uint64_t cpuNanoseconds;
} FDK_ENCODER_PROFILE_STAMP;

FDK_ENCODER_PROFILE_STAMP FDKaacEnc_ProfileNow(void);
void FDKaacEnc_ProfileAdd(FDK_ENCODER_PROFILE_BLOCK block,
                          FDK_ENCODER_PROFILE_STAMP start);
void FDKaacEnc_ProfileCounterAdd(FDK_ENCODER_PROFILE_COUNTER counter,
                                 uint64_t value);
void FDKaacEnc_ProfileDistortionTrial(int sfb, int lineCount);
void FDKaacEnc_ProfileNextChannel(int sfbCnt, int maxSfbPerGroup,
                                  int sfbPerGroup);
void FDKaacEnc_ProfileFrameBegin(void);
void FDKaacEnc_ProfileFrameEnd(void);
void FDKaacEnc_ProfileDump(void);

class FDKaacEnc_ProfileScope {
 public:
  explicit FDKaacEnc_ProfileScope(FDK_ENCODER_PROFILE_BLOCK block)
      : block_(block), start_(FDKaacEnc_ProfileNow()) {}

  ~FDKaacEnc_ProfileScope() { FDKaacEnc_ProfileAdd(block_, start_); }

 private:
  FDK_ENCODER_PROFILE_BLOCK block_;
  FDK_ENCODER_PROFILE_STAMP start_;
};

class FDKaacEnc_ProfileFrameScope {
 public:
  FDKaacEnc_ProfileFrameScope() {
    FDKaacEnc_ProfileFrameBegin();
    start_ = FDKaacEnc_ProfileNow();
  }

  ~FDKaacEnc_ProfileFrameScope() {
    FDKaacEnc_ProfileAdd(FDK_ENC_PROFILE_FRAME_TOTAL, start_);
    FDKaacEnc_ProfileFrameEnd();
  }

 private:
  FDK_ENCODER_PROFILE_STAMP start_;
};

#define FDK_ENC_PROFILE_SCOPE(name, block) \
  FDKaacEnc_ProfileScope name(block)
#define FDK_ENC_PROFILE_FRAME_SCOPE(name) FDKaacEnc_ProfileFrameScope name
#define FDK_ENC_PROFILE_START(name) \
  const FDK_ENCODER_PROFILE_STAMP name = FDKaacEnc_ProfileNow()
#define FDK_ENC_PROFILE_STOP(block, name) FDKaacEnc_ProfileAdd(block, name)
#define FDK_ENC_PROFILE_COUNTER_ADD(counter, value) \
  FDKaacEnc_ProfileCounterAdd(counter, (uint64_t)(value))
#define FDK_ENC_PROFILE_DISTORTION_TRIAL(sfb, lineCount) \
  FDKaacEnc_ProfileDistortionTrial((sfb), (lineCount))
#define FDK_ENC_PROFILE_NEXT_CHANNEL(sfbCnt, maxSfbPerGroup, sfbPerGroup) \
  FDKaacEnc_ProfileNextChannel((sfbCnt), (maxSfbPerGroup), (sfbPerGroup))
#define FDK_ENC_PROFILE_DUMP() FDKaacEnc_ProfileDump()

#else

#define FDK_ENC_PROFILE_SCOPE(name, block)
#define FDK_ENC_PROFILE_FRAME_SCOPE(name)
#define FDK_ENC_PROFILE_START(name)
#define FDK_ENC_PROFILE_STOP(block, name)
#define FDK_ENC_PROFILE_COUNTER_ADD(counter, value)
#define FDK_ENC_PROFILE_DISTORTION_TRIAL(sfb, lineCount)
#define FDK_ENC_PROFILE_NEXT_CHANNEL(sfbCnt, maxSfbPerGroup, sfbPerGroup)
#define FDK_ENC_PROFILE_DUMP()

#endif

#endif /* AACENC_PROFILE_H */
