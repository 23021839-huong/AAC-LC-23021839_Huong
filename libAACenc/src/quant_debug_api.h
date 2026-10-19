/* Observation API for a single native AAC-LC encoder per process. */
#ifndef FDK_QUANT_DEBUG_API_H
#define FDK_QUANT_DEBUG_API_H
#if defined(_WIN32) && defined(FDK_QUANT_DEBUG_SHARED)
#if defined(FDK_QUANT_DEBUG_BUILD)
#define FDK_QUANT_API __declspec(dllexport)
#else
#define FDK_QUANT_API __declspec(dllimport)
#endif
#else
#define FDK_QUANT_API
#endif
extern "C" {
FDK_QUANT_API int FDKquantDebugConfigure(const char *, int, int, int, int, int,
                                       unsigned, int, int);
FDK_QUANT_API int FDKquantDebugFinish(void);
FDK_QUANT_API const char *FDKquantDebugError(void);
}
#endif
