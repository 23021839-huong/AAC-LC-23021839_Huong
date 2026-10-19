/* Optional observation-only hooks. No arithmetic in this interface.
 * Configure one AAC-LC mono/stereo encoder per process, on one thread.
 * This research interface is not part of the installed FDK public API. */
#ifndef FDK_MDCT_DEBUG_H
#define FDK_MDCT_DEBUG_H

#include "common_fix.h"

#if defined(_WIN32) && defined(FDK_MDCT_DEBUG_SHARED)
#ifdef FDK_MDCT_DEBUG_BUILD
#define FDK_MDCT_DEBUG_API __declspec(dllexport)
#else
#define FDK_MDCT_DEBUG_API __declspec(dllimport)
#endif
#else
#define FDK_MDCT_DEBUG_API
#endif

extern "C" {
/* frame=-1 selects the earliest native snapshot with maximum PCM RMS.
 * directory must already exist. Return 0 on success, nonzero on error. */
FDK_MDCT_DEBUG_API int FDKmdctDebugConfigure(const char *directory, int channels,
                                          int frame, int channel);
FDK_MDCT_DEBUG_API int FDKmdctDebugWrite(void);
FDK_MDCT_DEBUG_API const char *FDKmdctDebugError(void);

void FDKmdctDebugBegin(const INT_PCM *pcm, int length, int channel,
                       int block_type, int window_shape);
void FDKmdctDebugFold(const FIXP_DBL *data, int length, int exponent, int sub,
                      int fl, int fr, int nl, int nr, const FIXP_WTP *left,
                      const FIXP_WTP *right, const INT_PCM *sub_pcm);
void FDKmdctDebugPre(const FIXP_DBL *data, int length, int exponent);
void FDKmdctDebugFft(const FIXP_DBL *data, int length, int exponent);
void FDKmdctDebugPost(const FIXP_DBL *data, int length, int exponent);
void FDKmdctDebugEnd(const FIXP_DBL *data, int length, int exponent);
}
#endif
