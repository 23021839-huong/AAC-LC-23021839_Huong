/* Observation-only research interface; not part of the installed AAC API.
 * One AAC-LC mono/stereo encoder, one thread per process. */
#ifndef FDK_PSY_DEBUG_H
#define FDK_PSY_DEBUG_H

#ifdef PSY_DEBUG
#include "psy_debug_api.h"
#include "FDK_lpc.h"
#include "psy_main.h"
#include "psy_data.h"
#include "psy_configuration.h"
#include "aacenc_pns.h"
extern "C" {
void FDKpsyDebugBeginFrame(void);
void FDKpsyDebugContext(int channel, const PSY_CONFIGURATION *cfg,
                        const PSY_STATIC *state, int exponent);
void FDKpsyDebugSelect(int channel, int window, int exponent);
int FDKpsyDebugExponent(void);
void FDKpsyDebugDbl(const char *stage, const char *name, const FIXP_DBL *data,
                    int count, int exponent, const char *unit, int index = 0);
void FDKpsyDebugSgl(const char *stage, const char *name, const FIXP_SGL *data,
                    int count, int exponent, const char *unit, int index = 0);
void FDKpsyDebugInt(const char *stage, const char *name, const INT *data,
                    int count, int index = 0);
void FDKpsyDebugScalar(const char *stage, const char *name, int value, int index = 0);
void FDKpsyDebugLpc(const char *name, const FIXP_LPC *data, int count, int exponent,
                    int filter);
void FDKpsyDebugBands(const char *phase, const PSY_DATA *data,
                      const PSY_CONFIGURATION *cfg, int stride, int windows);
void FDKpsyDebugTns(const char *phase, const TNS_CONFIG *cfg,
                    const TNS_DATA *data, const TNS_INFO *info, int window);
void FDKpsyDebugOutput(const PSY_OUT_CHANNEL *out, const PSY_OUT_ELEMENT *element, int channels);
}
#define PSY_OBSERVE(...) do { __VA_ARGS__; } while (0)
#else
#define PSY_OBSERVE(...) do { } while (0)
#endif
#endif
