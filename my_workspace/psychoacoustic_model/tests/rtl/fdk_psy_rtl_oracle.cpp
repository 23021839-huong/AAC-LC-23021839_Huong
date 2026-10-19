// Test-only native FDK oracle. No codec source is modified by this harness.
// Frontend orchestration follows psy_main.cpp; arithmetic and band operations
// call the actual native FDK helpers. This is not an ARM or full-encoder oracle.
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include "band_nrg.h"
#include "spreading.h"
#include "pre_echo_control.h"
#include "psy_configuration.h"
#include "aacEnc_rom.h"

// Memory/vector glue only. The exercised codec helpers remain native source.
void FDKmemcpy(void* dst, const void* src, const UINT size) { std::memcpy(dst,src,size); }
void LdDataVector(FIXP_DBL* src, FIXP_DBL* dst, INT count) {
  for (int i=0;i<count;++i) dst[i]=CalcLdData(src[i]);
}

static uint32_t rng_state=0x61aacc02u;
static uint32_t random_word() {
  rng_state^=rng_state<<13; rng_state^=rng_state>>17; rng_state^=rng_state<<5;
  return rng_state;
}
static FIXP_DBL word(uint32_t v) { return static_cast<FIXP_DBL>(static_cast<int32_t>(v)); }
static void hex(std::ostream& f, FIXP_DBL v) {
  f<<std::hex<<std::setw(8)<<std::setfill('0')<<static_cast<uint32_t>(v)<<std::dec<<' ';
}
static void primitive_vectors(const std::string& path) {
  std::ofstream f(path);
  std::vector<uint32_t> values={0,1,2,3,0x7fffffff,0x80000000,0xffffffff,
      0x40000000,0xc0000000,0x00010000,0xffff0000,0x0000ffff};
  for(int i=0;i<2048;++i) values.push_back(random_word());
  for(auto u:values) {
    FIXP_DBL a=word(u), b=word(random_word());
    FIXP_SGL c=static_cast<FIXP_SGL>(static_cast<uint16_t>(b));
    FIXP_DBL expected[]={fMult(a,b),fMultDiv2(a,b),fMult(a,c),
      fMultDiv2(a,c),static_cast<FIXP_DBL>(CountLeadingBits(a)),
      static_cast<FIXP_DBL>(CntLeadingZeros(a)),CalcLdData(a)};
    for(int op=0;op<7;++op) {
      f<<op<<' '; hex(f,a); hex(f,b); hex(f,expected[op]); f<<'\n';
    }
  }
}

struct Frontend {
  int channels, short_block, exponent, bands, lowpass, shift=0, out_scale=0;
  bool zero=true;
  std::vector<int> offsets;
  std::vector<FIXP_DBL> input, spectrum, energy, ld, threshold;
  std::vector<int> headroom;
};
static int slot(int c,int w,int b) { return c*120+w*15+b; }
static int bank(const Frontend& x,int c,int w,int b) {
  return x.short_block?slot(c,w,b):c*120+b;
}
static void calculate(Frontend& x) {
  const int windows=x.short_block?8:1, length=x.short_block?128:1024;
  x.spectrum=x.input;
  x.energy.assign(240,0); x.ld.assign(240,0); x.threshold.assign(240,0);
  x.headroom.assign(240,0);
  for(int c=0;c<x.channels;++c) for(int w=0;w<windows;++w) {
    for(int i=0;i<length;++i) {
      auto& v=x.spectrum[c*1024+w*length+i];
      if(i>=x.lowpass) v=0;
      if(v) x.zero=false;
    }
  }
  x.out_scale=x.exponent;
  if(x.zero) {
    x.out_scale=0;
    for(int c=0;c<x.channels;++c) for(int w=0;w<windows;++w)
      for(int b=0;b<x.bands;++b) x.ld[bank(x,c,w,b)]=FL2FXCONST_DBL(-1.0f);
    return;
  }
  int minimum=31, nrg_shift=31;
  FIXP_DBL maximum=0;
  for(int c=0;c<x.channels;++c) for(int w=0;w<windows;++w) {
    const int start=bank(x,c,w,0);
    FDKaacEnc_CalcSfbMaxScaleSpec(&x.spectrum[c*1024+w*length],x.offsets.data(),
                                &x.headroom[start],x.bands);
    for(int b=0;b<x.bands;++b) minimum=std::min(minimum,x.headroom[start+b]);
  }
  for(int c=0;c<x.channels;++c) for(int w=0;w<windows;++w) {
    const int start=bank(x,c,w,0);
    FIXP_DBL current=FDKaacEnc_CheckBandEnergyOptim(&x.spectrum[c*1024+w*length],
      &x.headroom[start],x.offsets.data(),x.bands,&x.energy[start],&x.ld[start],minimum-4);
    maximum=std::max(maximum,current);
  }
  if(maximum) nrg_shift=(CountLeadingBits(maximum)>>1)+(minimum-4);
  if(x.short_block) --nrg_shift;
  x.shift=std::min(std::min(minimum,nrg_shift),x.exponent+3);
  if(x.shift<0||x.shift>30) throw std::runtime_error("fixture exceeds frontend scale domain");
  const FIXP_DBL ld_shift=x.shift*FL2FXCONST_DBL(2.0/64);
  for(int c=0;c<x.channels;++c) for(int w=0;w<windows;++w) {
    for(int b=0;b<x.bands;++b) {
      const int i=bank(x,c,w,b);
      int scale=std::min((std::max(0,x.headroom[i]-4)-x.shift)*2,31);
      x.energy[i]=scaleValue(x.energy[i],-scale);
      x.threshold[i]=fMult(x.energy[i],C_RATIO);
      x.ld[i]+=ld_shift;
      x.headroom[i]-=x.shift;
    }
    for(int i=0;i<x.lowpass;++i) x.spectrum[c*1024+w*length+i]<<=x.shift;
  }
  x.out_scale=x.exponent-x.shift;
}
static std::vector<int> layout(bool is_short,bool use_32k) {
  std::vector<int> o={0};
  if(is_short) {
    const auto& t=p_FDKaacEnc_48000_short_128;
    for(int i=0;i<t.sfbCnt;++i) o.push_back(o.back()+t.sfbWidth[i]);
  } else {
    const auto& t=use_32k?p_FDKaacEnc_32000_long_1024:p_FDKaacEnc_48000_long_1024;
    for(int i=0;i<t.sfbCnt;++i) o.push_back(o.back()+t.sfbWidth[i]);
  }
  return o;
}
static void frontend_vectors(const std::string& path) {
  std::ofstream f(path);
  constexpr int cases=32;
  f<<cases<<'\n';
  for(int k=0;k<cases;++k) {
    Frontend x;
    x.channels=1+(k%3==0); x.short_block=(k/8)%2; x.exponent=x.short_block?9:12;
    x.offsets=layout(x.short_block,k>=16);
    const int length=x.short_block?128:1024, pattern=k%8;
    x.lowpass=(k%4==3)?length*3/4+1:length;
    x.bands=1;
    while(x.bands<static_cast<int>(x.offsets.size())-1&&x.offsets[x.bands]<x.lowpass) ++x.bands;
    x.offsets.resize(x.bands+1); x.input.resize(1024*x.channels);
    for(int c=0;c<x.channels;++c) for(int i=0;i<1024;++i) {
      int32_t v=static_cast<int32_t>(random_word())>>8;
      if(pattern==0) v=0;
      if(pattern==1) v=(i==7)?(1<<25):0;
      if(pattern==2) v=(i%2?-1:1)*(1<<22);
      if(pattern==4) v=(i%2?-1:1);
      if(pattern==5) v=((i%length)>=x.lowpass)?v:0;
      if(pattern==6) v=(i/128==3)?v:0;
      if(pattern==7&&c==1) v=-static_cast<int32_t>(x.input[i]);
      x.input[c*1024+i]=v;
    }
    calculate(x);
    f<<x.channels<<' '<<x.short_block<<' '<<x.exponent<<' '<<x.bands<<' '<<x.lowpass<<'\n';
    for(int o:x.offsets) f<<o<<' '; f<<'\n';
    for(auto v:x.input) { hex(f,v); f<<'\n'; }
    f<<x.out_scale<<' '<<x.shift<<' '<<int(x.zero)<<'\n';
    for(auto v:x.spectrum) { hex(f,v); f<<'\n'; }
    for(int c=0;c<x.channels;++c) for(int w=0;w<(x.short_block?8:1);++w)
      for(int b=0;b<x.bands;++b) {
        int i=bank(x,c,w,b);
        f<<x.headroom[i]<<' '; hex(f,x.energy[i]); hex(f,x.ld[i]); hex(f,x.threshold[i]); f<<'\n';
      }
  }
}

static void masking_vectors(const std::string& path) {
  std::ofstream f(path);
  constexpr int cases=40;
  f<<cases<<'\n';
  // A sequence of window operations: external history is exactly the scheduler
  // boundary, including sequential short windows and START/STOP resets.
  for(int k=0;k<cases;++k) {
    int bands=(k%5==0)?1:((k%3==0)?51:14);
    int block=k%4, exponent=(block==2)?3:6, previous=exponent+(k%3)-1;
    int pcm_shift=2*exponent+16+(block==2?(k%8)*16:0);
    int lfe=(k%11==0), calc=(k%7!=0);
    if(k==38) exponent=-2,previous=-1,pcm_shift=-4;
    if(k==39) exponent=0,previous=1,pcm_shift=16;
    FIXP_DBL clip=(block==2)?(word(0x773593ff)>>6):word(0x773593ff);
    std::vector<FIXP_DBL> energy(bands),thr(bands),hist(bands),pcm(bands),lo(bands),hi(bands),elo(bands),ehi(bands);
    for(int b=0;b<bands;++b) {
      energy[b]=(random_word()&0x0fffffffu);
      thr[b]=(random_word()&0x00ffffffu);
      hist[b]=(random_word()&0x0001ffffu);
      pcm[b]=(b+1)*0x547062;
      lo[b]=word(0x20000000u+(random_word()&0x1fffffffu));
      hi[b]=word(0x40000000u+(random_word()&0x1fffffffu));
      elo[b]=word(0x30000000u+(random_word()&0x1fffffffu));
      ehi[b]=word(0x50000000u+(random_word()&0x1fffffffu));
      if(k==37) thr[b]=energy[b]=hist[b]=0;
    }
    f<<bands<<' '<<block<<' '<<exponent<<' '<<pcm_shift<<' '<<lfe<<' '<<previous<<' '<<calc<<' '; hex(f,clip); f<<'\n';
    for(int b=0;b<bands;++b) {
      for(auto v:{energy[b],thr[b],hist[b],pcm[b],lo[b],hi[b],elo[b],ehi[b]}) hex(f,v);
      f<<'\n';
    }
    int clip_shift=2*exponent-THR_SHIFTBITS;
    FIXP_DBL scaled_clip;
    if(clip_shift>=0) scaled_clip=clip>>clip_shift;
    else if(clip_shift>=-(block==2?6:0)) scaled_clip=clip<<-clip_shift;
    else scaled_clip=MAXVAL_DBL;
    for(auto& v:thr) v=std::min(v,scaled_clip);
    FDKaacEnc_SpreadingMax(bands,lo.data(),hi.data(),thr.data());
    for(int b=0;b<bands;++b) thr[b]=std::max(thr[b]>>THR_SHIFTBITS,
      scaleValue(pcm[b],pcm_shift>=0?-std::min(31,pcm_shift):std::min(31,-pcm_shift)));
    if(!lfe) {
      if(block==3) {
        std::fill(hist.begin(),hist.end(),MAXVAL_DBL); previous=0; calc=0;
      }
      FDKaacEnc_PreEchoControl(hist.data(),calc,bands,2,(FIXP_SGL)0x0148,thr.data(),exponent,&previous);
      calc=1;
      if(block==1) {
        std::fill(hist.begin(),hist.end(),MAXVAL_DBL); previous=0; calc=0;
      }
    }
    FDKaacEnc_SpreadingMax(bands,elo.data(),ehi.data(),energy.data());
    f<<previous<<' '<<calc<<'\n';
    for(int b=0;b<bands;++b) {
      hex(f,thr[b]); hex(f,std::max(CalcLdData(thr[b]),FL2FXCONST_DBL(-0.515625f)));
      hex(f,energy[b]); hex(f,hist[b]); f<<'\n';
    }
  }
}
int main(int argc,char** argv) {
  try {
    static_assert(sizeof(FIXP_DBL)==4,"FDK words must be 32-bit");
#ifndef LDCOEFF_16BIT
    throw std::runtime_error("oracle architecture must select LDCOEFF_16BIT");
#endif
    if(argc!=2) throw std::runtime_error("usage: fdk_psy_rtl_oracle OUTPUT_DIRECTORY");
    std::string dir=argv[1];
    primitive_vectors(dir+"/primitives.txt"); frontend_vectors(dir+"/frontend.txt");
    masking_vectors(dir+"/masking.txt");
    std::cout<<"PASS: generated native FDK helper vectors (LDCOEFF_16BIT)\n";
    return 0;
  } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
