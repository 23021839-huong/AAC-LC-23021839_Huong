/* Research-only controls, one sequential AAC-LC encoder per process/thread.
 * Original estimator/filter arithmetic is not implemented in this interface. */
#ifndef FDK_PSY_EXPERIMENT_H
#define FDK_PSY_EXPERIMENT_H
#include "common_fix.h"
#include <cstdint>
enum PSY_TEST_MODE {
  PSY_NATIVE_DEFAULT=-1,
  PSY_TONALITY_ON_TNS_ON=0,
  PSY_TONALITY_ON_TNS_OFF=1,
  PSY_TONALITY_OFF_TNS_ON=2,
  PSY_TONALITY_OFF_TNS_OFF=3
};
enum PSY_PROFILE_STAGE { PSY_MAIN=0, PSY_TONALITY=1, PSY_TNS_ANALYSIS=2, PSY_TNS_FILTERING=3 };
struct FDK_PSY_EVENT {
  int frame_index,channel,sequence,shape,tonality_enabled,tonality_applied;
  int tns_enabled,tns_applied,pns_enabled,pns_used,tonality_count,filter_count;
  int tonality_q15[51],orders[16],start_bands[16],stop_bands[16],syntax_start_bands[16],syntax_stop_bands[16];
  std::uint64_t mdct_hash;
};
struct FDK_PSY_PROFILE { std::uint64_t nanoseconds[4],calls[4]; };
struct FDK_PSY_DECODER_CHECK { int present_flags,signaled_filters,nonzero_orders; };
typedef void (*FDK_PSY_OBSERVER)(const FDK_PSY_EVENT *,void *);
extern "C" {
int FDKpsyExperimentConfigure(int mode,int expected_pns,int profile,FDK_PSY_OBSERVER observer,void *context);
const char *FDKpsyExperimentError(void);
int FDKpsyExperimentTnsMask(int nativeMask);
int FDKpsyExperimentTonality(int nativePns);
int FDKpsyExperimentContext(int ch,int sequence,int shape,int pns,int tns);
void FDKpsyExperimentBeginFrame(void);
void FDKpsyExperimentMdct(int ch,const FIXP_DBL *p,int n,int exponent);
void FDKpsyExperimentTonalityOutput(int ch,const FIXP_SGL *p,int n);
void FDKpsyExperimentOutput(int ch,const INT *counts,int windows,const INT *orders,const INT *lengths,
                           int totalBands,int highStart,int lowStart,int stopBand,int merged,const INT *noise,int n);
std::uint64_t FDKpsyExperimentStart(int stage);
void FDKpsyExperimentEnd(int stage,std::uint64_t start);
void FDKpsyExperimentGetProfile(FDK_PSY_PROFILE *profile);
void FDKpsyExperimentDecoderReset(void);
void FDKpsyExperimentDecoderPresent(int flag);
void FDKpsyExperimentDecoderFilter(int order);
void FDKpsyExperimentDecoderGet(FDK_PSY_DECODER_CHECK *result);
}
#ifdef PSY_EXPERIMENT
class FDKPsyExperimentScope {
  int stage_;std::uint64_t start_;
 public:
  explicit FDKPsyExperimentScope(int stage):stage_(stage),start_(FDKpsyExperimentStart(stage)){}
  ~FDKPsyExperimentScope(){FDKpsyExperimentEnd(stage_,start_);}
};
#define PSY_EXPERIMENT_OBSERVE(...) do { __VA_ARGS__; } while(0)
#else
#define PSY_EXPERIMENT_OBSERVE(...) do {} while(0)
#endif
#endif
