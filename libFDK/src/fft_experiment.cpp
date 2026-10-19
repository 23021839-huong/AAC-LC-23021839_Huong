/* Pure radix-2 research kernel, added 2026-10-13.
 * Third-Party Modified Version of the Fraunhofer FDK AAC Codec Library for Android.
 * Native FFT and coefficient ROM files are unchanged. Full FDK license: NOTICE. */
#include "fft_experiment.h"
#include "fft.h"
#include "FDK_tools_rom.h"
#include "scramble.h"
#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <time.h>
#endif

namespace {
int selected_mode=FFT_ORIGINAL, profiling=0, encoder_mdct_depth=0;
FDK_FFT_PROFILE profile_data={};
#ifdef SINETABLE_16BIT
const int coefficient_bits=15;
#else
const int coefficient_bits=31;
#endif
// Portable arithmetic floor shift. All callers are bounded well above INT64_MIN.
inline INT64 floor_shift(INT64 value, int bits) {
  return value>=0 ? value>>bits : -(((-value)+((INT64(1)<<bits)-1))>>bits);
}
inline FIXP_DBL narrow(INT64 value, FDK_FFT_DIAGNOSTICS *d) {
  if (value>2147483647LL) { if(d) ++d->saturations; return FIXP_DBL(2147483647); }
  if (value<(-2147483647LL-1)) { if(d) ++d->saturations; return FIXP_DBL(-2147483647-1); }
  return FIXP_DBL(value);
}
int guard_shift(int length, const FIXP_DBL *x) {
  INT64 peak=0;
  for(int i=0;i<2*length;++i) {
    INT64 value=x[i]; if(value<0) value=-value;
    if(value>peak) peak=value;
  }
  int shift=0;
  while(peak>(INT64(1)<<29)) { peak=(peak+1)>>1; ++shift; }
  return shift;
}
void prescale(int length, FIXP_DBL *x, int shift) {
  if(shift) for(int i=0;i<2*length;++i) x[i]=FIXP_DBL(floor_shift(x[i],shift));
}
inline INT64 half_product(FIXP_DBL value, FIXP_STB coefficient) {
  // FDK fMultDiv2 semantics: Q31*Q15 >>16 or Q31*Q31 >>32, each product floored.
  return floor_shift(INT64(value)*INT64(coefficient),coefficient_bits+1);
}
// Compute (br+j*bi)*exp(-j*angle)/2 using the native ROM and octant symmetry.
// Negations follow product truncation, matching the native sign/rounding order.
void rotated_half(FIXP_DBL br,FIXP_DBL bi,int angle,INT64 &tr,INT64 &ti) {
  if(angle==0) { tr=floor_shift(br,1); ti=floor_shift(bi,1); return; }
  if(angle==512) { tr=floor_shift(bi,1); ti=-floor_shift(br,1); return; }
  int index;
  if(angle<=256) index=angle;
  else if(angle<512) index=512-angle;
  else if(angle<=768) index=angle-512;
  else index=1024-angle;
  const FIXP_STP pair=SineTable512[index];
  const INT64 rc=half_product(br,pair.v.re), rs=half_product(br,pair.v.im);
  const INT64 ic=half_product(bi,pair.v.re), is=half_product(bi,pair.v.im);
  if(angle<=256) { tr=rc+is; ti=ic-rs; }
  else if(angle<512) { tr=rs+ic; ti=is-rc; }
  else if(angle<=768) { tr=ic-rs; ti=-(rc+is); }
  else { tr=is-rc; ti=-(rs+ic); }
}
int radix2(int length,FIXP_DBL *x,int *exponent,FDK_FFT_DIAGNOSTICS *diagnostics) {
  if((length!=64 && length!=512) || !x || !exponent) return -1;
  const int stages=length==64 ? 6 : 9;
  const int extra=guard_shift(length,x);
  if(INT64(*exponent)+extra+stages-1>2147483647LL) return -1;
  FDK_FFT_DIAGNOSTICS d={}; d.extra_prescale=extra; d.coefficient_fraction_bits=coefficient_bits;
  prescale(length,x,extra);
  scramble(x,length);
  for(int span=2;span<=length;span*=2) {
    const int half=span/2;
    for(int offset=0;offset<length;offset+=span) {
      for(int j=0;j<half;++j) {
        const int upper=2*(offset+j), lower=upper+2*half;
        const INT64 ur=x[upper], ui=x[upper+1];
        INT64 tr,ti;
        if(span==2) { tr=x[lower]; ti=x[lower+1]; }
        else rotated_half(x[lower],x[lower+1],j*(2048/span),tr,ti);
        const INT64 ar=span==2 ? ur : floor_shift(ur,1);
        const INT64 ai=span==2 ? ui : floor_shift(ui,1);
        x[upper]=narrow(ar+tr,&d); x[upper+1]=narrow(ai+ti,&d);
        x[lower]=narrow(ar-tr,&d); x[lower+1]=narrow(ai-ti,&d);
        ++d.radix2_butterflies; // Actual executed binary butterflies, no radix-4 call.
      }
    }
    ++d.stages;
  }
  *exponent+=extra+stages-1;
  if(diagnostics) *diagnostics=d;
  return 0;
}
INT64 ticks() {
#if defined(_WIN32)
  LARGE_INTEGER value; QueryPerformanceCounter(&value); return value.QuadPart;
#else
  timespec value; clock_gettime(CLOCK_MONOTONIC,&value);
  return INT64(value.tv_sec)*1000000000LL+value.tv_nsec;
#endif
}
double tick_frequency() {
#if defined(_WIN32)
  LARGE_INTEGER value; QueryPerformanceFrequency(&value); return double(value.QuadPart);
#else
  return 1000000000.0;
#endif
}
double clock_frequency=0;
}
extern "C" int FDKfftExperimentConfigure(int mode,int profile) {
  if((mode!=FFT_ORIGINAL && mode!=FFT_RADIX2_ONLY) || (profile!=0 && profile!=1) || encoder_mdct_depth) return -1;
  selected_mode=mode; profiling=profile; profile_data=FDK_FFT_PROFILE{};
  if(profile) clock_frequency=tick_frequency();
  return 0;
}
extern "C" void FDKfftExperimentGetProfile(FDK_FFT_PROFILE *out) { if(out) *out=profile_data; }
extern "C" double FDKfftExperimentClockPairMeanNs(void) {
  const double frequency=tick_frequency(); INT64 sum=0;
  for(int i=0;i<10000;++i) { INT64 begin=ticks(); INT64 end=ticks(); sum+=end-begin; }
  return double(sum)*1e9/frequency/10000.0;
}
extern "C" int FDKfftExperimentTransform(int mode,int length,FIXP_DBL *x,int *exponent,FDK_FFT_DIAGNOSTICS *out) {
  if((length!=64 && length!=512) || !x || !exponent || (mode!=0 && mode!=1)) return -1;
  if(mode==FFT_RADIX2_ONLY) return radix2(length,x,exponent,out);
  const int stages=length==64 ? 6 : 9, extra=guard_shift(length,x);
  if(INT64(*exponent)+extra+stages-1>2147483647LL) return -1;
  prescale(length,x,extra); *exponent+=extra;
  fft(length,x,exponent); // Unchanged native code, safe normalized validation input.
  if(out) { *out=FDK_FFT_DIAGNOSTICS{}; out->stages=stages; out->extra_prescale=extra;
    out->coefficient_fraction_bits=coefficient_bits;
    out->radix4_butterflies=length/4; out->radix2_butterflies=INT64(length/2)*(stages-2); }
  return 0;
}
extern "C" void FDKfftExperimentEnterEncoderMdct(void) { ++encoder_mdct_depth; }
extern "C" void FDKfftExperimentLeaveEncoderMdct(void) { --encoder_mdct_depth; }
extern "C" void FDKfftExperimentMdctFFT(int length,FIXP_DBL *x,int *exponent) {
  if(!encoder_mdct_depth) { fft(length,x,exponent); return; }
  if(length!=64 && length!=512) {
    if(profiling) ++profile_data.unexpected_lengths;
    fft(length,x,exponent); return;
  }
  FDK_FFT_DIAGNOSTICS d={}; const int before=*exponent;
  INT64 begin=profiling ? ticks() : 0;
  if(selected_mode==FFT_RADIX2_ONLY) {
    int status=radix2(length,x,exponent,&d); FDK_ASSERT(status==0); (void)status;
  } else fft(length,x,exponent);
  INT64 end=profiling ? ticks() : 0;
  if(profiling) {
    const double elapsed=double(end-begin)*1000/clock_frequency;
    if(length==64) { ++profile_data.calls_64; profile_data.time_64_ms+=elapsed; profile_data.exponent_increment_64=*exponent-before; }
    else { ++profile_data.calls_512; profile_data.time_512_ms+=elapsed; profile_data.exponent_increment_512=*exponent-before; }
    if(selected_mode==FFT_ORIGINAL) { d.radix4_butterflies=length/4; d.radix2_butterflies=INT64(length/2)*((length==64 ? 6 : 9)-2); }
    profile_data.radix2_butterflies+=d.radix2_butterflies; profile_data.radix4_butterflies+=d.radix4_butterflies;
    profile_data.saturations+=d.saturations; if(d.extra_prescale) ++profile_data.extra_prescale_calls;
  }
}
