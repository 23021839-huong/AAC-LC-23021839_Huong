/* Modified 2026-10-13: research controls/observation only, no replacement DSP. */
#include "psy_experiment.h"
#include <chrono>
#include <cstring>
namespace {
int mode=-1,expectedPns=-1,frame=-1,profileEnabled=0;
FDK_PSY_OBSERVER observer=0;void *context=0;
FDK_PSY_PROFILE profile={};FDK_PSY_DECODER_CHECK decoder={};
FDK_PSY_EVENT events[2]={};char error[256]={};
using Clock=std::chrono::steady_clock;
std::uint64_t now(){return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();}
}
extern "C" int FDKpsyExperimentConfigure(int m,int pns,int timing,FDK_PSY_OBSERVER fn,void *c) {
  if(m < -1 || m>3 || pns < -1 || pns>1 || timing<0 || timing>1)return -1;
  mode=m;expectedPns=pns;profileEnabled=timing;observer=fn;context=c;frame=-1;
  std::memset(events,0,sizeof(events));std::memset(&profile,0,sizeof(profile));error[0]=0;
  return 0;
}
extern "C" const char *FDKpsyExperimentError(){return error;}
extern "C" int FDKpsyExperimentTnsMask(int nativeMask){return mode<0 ? nativeMask : ((mode==0 || mode==2) ? 15 : 0);}
extern "C" int FDKpsyExperimentTonality(int pns){return mode<0 ? pns : (mode==0 || mode==1);}
extern "C" void FDKpsyExperimentBeginFrame(){if(observer){++frame;std::memset(events,0,sizeof(events));}}
extern "C" int FDKpsyExperimentContext(int ch,int sequence,int shape,int pns,int tns) {
  if(ch<0 || ch>1){std::strcpy(error,"UNSUPPORTED: mono/stereo only");return 0;}
  if(expectedPns>=0 && pns!=expectedPns){std::strcpy(error,"UNSUPPORTED: effective PNS configuration differs from native baseline");return 0;}
  if(mode>=0 && pns && (mode==1 || mode==2 || mode==3)) {
    std::strcpy(error,"UNSUPPORTED: independent OFF requires native PNS disabled; no invented tonality substitute or PNS-without-TNS");return 0;
  }
  if(!observer)return 1;
  FDK_PSY_EVENT &e=events[ch];e.frame_index=frame;e.channel=ch;e.sequence=sequence;e.shape=shape;
  e.pns_enabled=pns;e.tns_enabled=tns;e.tonality_enabled=FDKpsyExperimentTonality(pns);
  return 1;
}
extern "C" void FDKpsyExperimentMdct(int ch,const FIXP_DBL *p,int n,int exponent) {
  if(!observer)return;
  std::uint64_t h=14695981039346656037ULL;
  for(int i=0;i<n+1;++i){std::uint32_t v=i==n ? std::uint32_t(exponent) : std::uint32_t(p[i]);
    for(int b=0;b<4;++b){h^=(v>>(8*b))&255;h*=1099511628211ULL;}}
  events[ch].mdct_hash=h;
}
extern "C" void FDKpsyExperimentTonalityOutput(int ch,const FIXP_SGL *p,int n) {
  if(!observer)return;
  events[ch].tonality_applied=1;events[ch].tonality_count=n;
  for(int i=0;i<n && i<51;++i)events[ch].tonality_q15[i]=p[i];
}
extern "C" void FDKpsyExperimentOutput(int ch,const INT *counts,int windows,const INT *orders,const INT *lengths,
                                       int totalBands,int highStart,int lowStart,int stopBand,int merged,const INT *noise,int n) {
  if(!observer)return;
  FDK_PSY_EVENT &e=events[ch];int f=0;
  for(int w=0;w<windows;++w){int syntaxStop=totalBands;
    for(int k=0;k<counts[w] && f<16;++k,++f){
      e.orders[f]=orders[w*2+k];e.tns_applied|=e.orders[f]>0;
      e.start_bands[f]=(k || merged) ? lowStart : highStart;
      e.stop_bands[f]=k ? highStart : stopBand;
      e.syntax_stop_bands[f]=syntaxStop;syntaxStop-=lengths[w*2+k];e.syntax_start_bands[f]=syntaxStop;
    }}
  e.filter_count=f;
  /* LC SHORT has no PNS; avoid reading inactive grouped storage. */
  if(e.sequence!=2)for(int b=0;b<n;++b)e.pns_used+=(noise[b]!=(-2147483647-1));
  observer(&e,context);
}
extern "C" std::uint64_t FDKpsyExperimentStart(int stage){if(!profileEnabled)return 0;++profile.calls[stage];return now();}
extern "C" void FDKpsyExperimentEnd(int stage,std::uint64_t start){if(start)profile.nanoseconds[stage]+=now()-start;}
extern "C" void FDKpsyExperimentGetProfile(FDK_PSY_PROFILE *p){*p=profile;}
extern "C" void FDKpsyExperimentDecoderReset(){std::memset(&decoder,0,sizeof(decoder));}
extern "C" void FDKpsyExperimentDecoderPresent(int flag){decoder.present_flags+=flag!=0;}
extern "C" void FDKpsyExperimentDecoderFilter(int order){++decoder.signaled_filters;decoder.nonzero_orders+=order>0;}
extern "C" void FDKpsyExperimentDecoderGet(FDK_PSY_DECODER_CHECK *p){*p=decoder;}
