#ifndef FDK_QUANT_DEBUG_H
#define FDK_QUANT_DEBUG_H
#ifdef QUANT_DEBUG
#include "quant_debug_api.h"
#include "qc_data.h"
enum { QD_DENSE=0, QD_SFB=1, QD_OFFSETS=2, QD_SPECTRUM=3 };
void FDKquantDebugBeginFrame(void);
void FDKquantDebugBindElement(int, const ELEMENT_INFO *, const PSY_OUT_ELEMENT *, const QC_OUT_ELEMENT *);
void FDKquantDebugSelectChannel(const PSY_OUT_CHANNEL *);
void FDKquantDebugSelectShared(const PSY_OUT_CHANNEL *);
void FDKquantDebugSelectElement(int);
void FDKquantDebugLocation(const char *, const char *, int);
void FDKquantDebugLoop(const char *, const char *, int, int, int);
void FDKquantDebugScalar(const char *, const char *, long long, int, int, int, const char *, int=0);
void FDKquantDebugSharedScalar(const char *, const char *, long long, int, int, int, const char *, int=0);
void FDKquantDebugDbl(const char *, const char *, const FIXP_DBL *, int, int, const char *, int=0, int=QD_DENSE);
void FDKquantDebugInt(const char *, const char *, const INT *, int, int=0, int=QD_DENSE);
void FDKquantDebugShort(const char *, const char *, const SHORT *, int, int=0, int=QD_DENSE);
void FDKquantDebugUInt(const char *, const char *, const UINT *, int, int=0, int=QD_DENSE);
void FDKquantDebugPeBands(const PE_CHANNEL_DATA *, const PE_DATA *, const PSY_OUT_CHANNEL *, const char *);
void FDKquantDebugThreshold(const char *, const PSY_OUT_CHANNEL *, const QC_OUT_CHANNEL *);
void FDKquantDebugBudget(const char *, const QC_STATE *, const QC_OUT *, int=0, int=0);
void FDKquantDebugFinalFrame(const CHANNEL_MAPPING *, const PSY_OUT *, const QC_OUT *, const QC_STATE *);
void FDKquantDebugReconstructAccepted(const PSY_OUT_CHANNEL *, const QC_OUT_CHANNEL *);
void FDKquantDebugRange(const FIXP_DBL *, int, int, int=1);
int FDKquantDebugSfb(void);
int FDKquantDebugLine(void);
void FDKquantDebugLineOffset(int);
int FDKquantDebugWantLines(void);
int FDKquantDebugTrial(int);
int FDKquantDebugScale(void);
int FDKquantDebugSelected(void);
int FDKquantDebugTrialCount(int=-1);
void FDKquantDebugFlags(const char *, const UCHAR *, int);
struct QuantDebugScope {
  const char *kind, *phase; int iteration, candidate, sfb;
  QuantDebugScope(const char *, const char *, int=-1, int=-1, int=-1);
  ~QuantDebugScope();
};
#define QUANT_OBSERVE(...) do { FDKquantDebugLocation(__FILE__,__func__,__LINE__); __VA_ARGS__; } while (0)
#define QV(stage,name,value) QUANT_OBSERVE(FDKquantDebugScalar(stage,name,(long long)(value),32,0,0,"integer"))
#define Q_SHARED(stage,name,value) QUANT_OBSERVE(FDKquantDebugSharedScalar(stage,name,(long long)(value),32,0,0,"integer"))
#define Q_SCOPE(kind,phase,iter,candidate,sfb) QuantDebugScope quantDebugScope(kind,phase,iter,candidate,sfb)
#else
#define QUANT_OBSERVE(...) do {} while (0)
#define QV(...) do {} while (0)
#define Q_SHARED(...) do {} while (0)
#define Q_SCOPE(...) do {} while (0)
#endif
#endif
