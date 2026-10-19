/* Research-only interface: one AAC-LC mono/stereo encoder per process/thread.
 * Not part of the installed public FDK API. No DSP implementation here. */
#ifndef FDK_WINDOW_EXPERIMENT_H
#define FDK_WINDOW_EXPERIMENT_H
#include "common_fix.h"
#if defined(_WIN32) && defined(FDK_WINDOW_EXPERIMENT_SHARED)
#ifdef FDK_WINDOW_EXPERIMENT_BUILD
#define FDK_WINDOW_API __declspec(dllexport)
#else
#define FDK_WINDOW_API __declspec(dllimport)
#endif
#else
#define FDK_WINDOW_API
#endif

enum WINDOW_TEST_MODE {
  WINDOW_NATIVE_DEFAULT = -1,
  WINDOW_SINE_ONLY = 0,
  WINDOW_KBD_ONLY = 1,
  WINDOW_SINE_LONG_KBD_SHORT = 2,
  WINDOW_KBD_LONG_SINE_SHORT = 3
};
struct FDK_WINDOW_EVENT {
  int frame_index, channel, sequence, shape, previous_shape, mode;
  int left_shape, right_shape, left_length, right_length, bootstrap;
};
typedef void (*FDK_WINDOW_OBSERVER)(const FDK_WINDOW_EVENT *, void *);
extern "C" {
FDK_WINDOW_API int FDKwindowExperimentConfigure(int mode, FDK_WINDOW_OBSERVER observer, void *context);
int FDKwindowExperimentShape(int sequence, int native_shape);
void FDKwindowExperimentObserve(int channel, int sequence, int shape, int previous_shape,
                               int length, int previous_right_length, const FIXP_WTP *previous_right);
}
#endif
