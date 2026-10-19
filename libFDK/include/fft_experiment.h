/* Research-only FFT interface. One encoder/thread per process.
 * Third-Party Modified Version of the Fraunhofer FDK AAC Codec Library for Android.
 * Added 2026-10-13; native FFT/ROM unchanged. See NOTICE for the FDK license. */
#ifndef FDK_FFT_EXPERIMENT_H
#define FDK_FFT_EXPERIMENT_H
#include "common_fix.h"
#if defined(_WIN32) && defined(FDK_FFT_EXPERIMENT_SHARED)
#ifdef FDK_FFT_EXPERIMENT_BUILD
#define FDK_FFT_API __declspec(dllexport)
#else
#define FDK_FFT_API __declspec(dllimport)
#endif
#else
#define FDK_FFT_API
#endif
enum FFT_TEST_MODE { FFT_ORIGINAL=0, FFT_RADIX2_ONLY=1 };
struct FDK_FFT_DIAGNOSTICS {
  int stages, extra_prescale, coefficient_fraction_bits;
  INT64 radix2_butterflies, radix4_butterflies, saturations;
};
struct FDK_FFT_PROFILE {
  INT64 calls_64, calls_512, unexpected_lengths;
  INT64 radix2_butterflies, radix4_butterflies, saturations, extra_prescale_calls;
  double time_64_ms, time_512_ms;
  int exponent_increment_64, exponent_increment_512;
};
extern "C" {
FDK_FFT_API int FDKfftExperimentConfigure(int mode, int profile);
FDK_FFT_API void FDKfftExperimentGetProfile(FDK_FFT_PROFILE *profile);
FDK_FFT_API double FDKfftExperimentClockPairMeanNs(void);
// Validation-only direct transform: explicitly guard full-range inputs in BOTH modes.
FDK_FFT_API int FDKfftExperimentTransform(int mode, int length, FIXP_DBL *data,
                                        int *exponent, FDK_FFT_DIAGNOSTICS *diagnostics);
void FDKfftExperimentEnterEncoderMdct(void);
void FDKfftExperimentLeaveEncoderMdct(void);
void FDKfftExperimentMdctFFT(int length, FIXP_DBL *data, int *exponent);
}
#endif
