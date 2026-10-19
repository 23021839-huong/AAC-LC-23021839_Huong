/* Research runner API, deliberately independent of private encoder structs. */
#ifndef FDK_PSY_DEBUG_API_H
#define FDK_PSY_DEBUG_API_H
#if defined(_WIN32) && defined(FDK_PSY_DEBUG_SHARED)
#if defined(FDK_PSY_DEBUG_BUILD)
#define FDK_PSY_API __declspec(dllexport)
#else
#define FDK_PSY_API __declspec(dllimport)
#endif
#else
#define FDK_PSY_API
#endif
extern "C" {
FDK_PSY_API int FDKpsyDebugConfigure(const char *path, int first, int end,
                                    int channel, int sampleRate, unsigned stages);
FDK_PSY_API int FDKpsyDebugFinish(void);
FDK_PSY_API const char *FDKpsyDebugError(void);
}
#endif
