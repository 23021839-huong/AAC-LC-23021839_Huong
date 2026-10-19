/* Integer-only observation hooks: never write to native encoder buffers. */
#include "psy_debug.h"
#include <cstdio>
#include <cstring>

namespace {
struct Context {
  int block, shape, length, windows, exponent, activeBands, tableBands, codedBands;
  int activeLines, groups, groupLengths[4];
};
struct State {
  FILE *file;
  int frame, first, end, channel, sampleRate, currentChannel, window, selected;
  unsigned stages;
  Context context[2];
  char error[256];
};
State g;
void fail(const char *s) {
  if (!g.error[0]) std::snprintf(g.error, sizeof(g.error), "%s", s);
}
unsigned stage_bit(const char *s) {
  const char *names[] = {"sfb", "energy", "masking", "tonality", "tns", "pns"};
  for (int i = 0; i < 6; ++i) if (!std::strcmp(s, names[i])) return 1u << i;
  return 0;
}
bool active(const char *stage) {
  return g.file && !g.error[0] && g.frame >= g.first && g.frame < g.end &&
    (g.channel < 0 || g.channel == g.currentChannel) &&
    (!stage_bit(stage) || (g.stages & stage_bit(stage)));
}
bool masked_buffer(const Context &c,const char *stage,const char *name,int count) {
  if (!std::strcmp(stage,"output") && !std::strcmp(name,"ms_mask")) return true;
  if (c.windows!=8) return false;
  return (!std::strcmp(stage,"output") && (count>2)) ||
         (!std::strcmp(stage,"pns") && !std::strcmp(name,"final.noise_nrg"));
}
bool valid_at(const Context &c,const char *name,int count,int i) {
  if (!std::strcmp(name,"spectrum")) {
    int base=0;
    for (int group=0;group<c.groups;++group) {
      if (i>=base && i<base+c.activeLines*c.groupLengths[group]) return true;
      base+=128*c.groupLengths[group];
    }
    return false;
  }
  if (!std::strcmp(name,"ms_mask")) return (i%c.tableBands)<c.codedBands;
  if (!std::strcmp(name,"offsets")) return (i%c.tableBands)<=c.activeBands || i==count-1;
  return (i%c.tableBands)<c.activeBands;
}
template<class T> void record(const char *stage, const char *name, const T *data,
                              int count, int fraction, int exponent,
                              const char *unit, int index) {
  if (!active(stage)) return;
  if (!data || count < 0 || count > 2048 || g.currentChannel < 0 || g.currentChannel > 1) {
    fail("Invalid Psy observation buffer dimensions"); return;
  }
  const Context &c = g.context[g.currentChannel];
  const bool filterRecord = !std::strcmp(stage,"tns") &&
    (std::strstr(name,"quantized_coef") || std::strstr(name,"reflection_") ||
     !std::strcmp(name,"decoded_parcor") || !std::strcmp(name,"lpc") ||
     !std::strcmp(name,"gain_m") || !std::strcmp(name,"filter_start_line") ||
     !std::strcmp(name,"filter_stop_line") || !std::strcmp(name,"filter_initial_state") ||
     !std::strcmp(name,"filter_final_state") ||
     std::strstr(name,".order") || std::strstr(name,".direction") || std::strstr(name,".length"));
  const int baseIndex=filterRecord ? 0 : index;
  std::fprintf(g.file,
    "{\"schema_version\":1,\"frame\":%d,\"channel\":%d,\"window\":%d,"
    "\"block_type\":%d,\"window_shape\":%d,\"sample_rate\":%d,"
    "\"frame_length\":1024,\"window_length\":%d,\"windows\":%d,"
    "\"stage\":\"%s\",\"name\":\"%s\",\"count\":%d,\"index\":%d,"
    "\"bit_width\":%d,\"fraction_bits\":%d,\"exponent\":%d,"
    "\"unit\":\"%s\",\"raw\":[",
    g.frame,g.currentChannel,g.window,c.block,c.shape,g.sampleRate,c.length,c.windows,
    stage,name,count,baseIndex,(int)sizeof(T)*8,fraction,exponent,unit);
  const bool masked=masked_buffer(c,stage,name,count);
  for (int i = 0; i < count; ++i) {
    if (masked && !valid_at(c,name,count,i))
      std::fprintf(g.file,"%snull",i ? "," : ""); /* never read undefined native padding */
    else
      std::fprintf(g.file, "%s%ld",i ? "," : "",(long)data[i]);
  }
  std::fprintf(g.file,"]");
  if (filterRecord) std::fprintf(g.file,",\"filter\":%d",index);
  if (masked) {
    if (!std::strcmp(name,"spectrum"))
      std::fprintf(g.file,",\"valid_lines_per_window\":%d,\"valid_indices\":[",c.activeLines);
    else
      std::fprintf(g.file,",\"group_stride\":%d,\"valid_count_per_group\":%d,\"valid_indices\":[",
                   c.tableBands,!std::strcmp(name,"ms_mask") ? c.codedBands : c.activeBands);
    int emitted=0;
    for (int i=0;i<count;++i) {
      if (valid_at(c,name,count,i)) std::fprintf(g.file,"%s%d",emitted++ ? "," : "",i);
    }
    std::fprintf(g.file,"]");
  }
  std::fprintf(g.file,"}\n");
  if (std::ferror(g.file)) fail("Cannot write Psy trace");
}
void named(const char *stage, const char *phase, const char *field, const FIXP_DBL *p,
            int n, int e, const char *unit) {
  char name[96]; std::snprintf(name,sizeof(name),"%s.%s",phase,field);
  FDKpsyDebugDbl(stage,name,p,n,e,unit);
}
}

extern "C" int FDKpsyDebugConfigure(const char *path, int first, int end,
                                     int channel, int rate, unsigned stages) {
  if (g.file) std::fclose(g.file);
  std::memset(&g,0,sizeof(g)); g.frame=-1;
  if (!path || first < 0 || end <= first || channel < -1 || channel > 1 || rate <= 0 || stages > 63) {
    fail("Invalid Psy trace selection"); return 1;
  }
  g.first=first; g.end=end; g.channel=channel; g.sampleRate=rate; g.stages=stages;
  g.file=std::fopen(path,"w");
  if (!g.file) { fail("Cannot open Psy JSONL trace"); return 1; }
  return 0;
}
extern "C" const char *FDKpsyDebugError(void) { return g.error; }
extern "C" int FDKpsyDebugFinish(void) {
  if (g.file) {
    if (std::ferror(g.file)) fail("Psy trace write failed");
    if (std::fclose(g.file)) fail("Psy trace close failed");
    g.file=NULL;
  }
  if (!g.selected) fail("No requested native frame/channel was observed");
  if (g.end > g.frame+1) fail("Requested frame range exceeds native encoder stream");
  return g.error[0] ? 1 : 0;
}
extern "C" void FDKpsyDebugBeginFrame(void) { if (g.file) ++g.frame; }
extern "C" int FDKpsyDebugExponent(void) { return g.context[g.currentChannel].exponent; }
extern "C" void FDKpsyDebugSelect(int ch,int w,int e) {
  if (!g.file) return;
  if (ch<0 || ch>1) { fail("Psy trace supports mono/stereo only"); return; }
  g.currentChannel=ch; g.window=w; g.context[ch].exponent=e;
}
extern "C" void FDKpsyDebugDbl(const char *s,const char *n,const FIXP_DBL *p,int k,
                               int e,const char *u,int i) { record(s,n,p,k,31,e,u,i); }
extern "C" void FDKpsyDebugSgl(const char *s,const char *n,const FIXP_SGL *p,int k,
                               int e,const char *u,int i) { record(s,n,p,k,15,e,u,i); }
extern "C" void FDKpsyDebugInt(const char *s,const char *n,const INT *p,int k,int i) {
  record(s,n,p,k,0,0,"integer",i);
}
extern "C" void FDKpsyDebugScalar(const char *s,const char *n,int v,int i) {
  FDKpsyDebugInt(s,n,&v,1,i);
}
extern "C" void FDKpsyDebugLpc(const char *n,const FIXP_LPC *p,int k,int e,int f) {
  record("tns",n,p,k,(int)sizeof(FIXP_LPC)*8-1,e,"coefficient",f);
}
extern "C" void FDKpsyDebugContext(int ch,const PSY_CONFIGURATION *cfg,
                                   const PSY_STATIC *state,int e) {
  if (!g.file) return;
  if (ch<0 || ch>1) { fail("Psy trace supports mono/stereo only"); return; }
  Context &c=g.context[ch];
  c.block=state->blockSwitchingControl.lastWindowSequence;
  c.shape=state->blockSwitchingControl.windowShape;
  c.windows=c.block==SHORT_WINDOW ? 8 : 1;
  c.length=1024/c.windows;
  c.activeBands=state->isLFE ? cfg->sfbActiveLFE : cfg->sfbActive;
  c.tableBands=cfg->sfbCnt;
  c.codedBands=c.activeBands;
  c.activeLines=cfg->sfbOffset[c.activeBands];
  c.groups=state->blockSwitchingControl.noOfGroups;
  std::memcpy(c.groupLengths,state->blockSwitchingControl.groupLen,sizeof(c.groupLengths));
  FDKpsyDebugSelect(ch,-1,e);
  if (active("context")) ++g.selected;
  FDKpsyDebugScalar("context","mdct_exponent",e);
  FDKpsyDebugScalar("context","sfb_count",cfg->sfbCnt);
  FDKpsyDebugScalar("context","sfb_active",cfg->sfbActive);
  FDKpsyDebugScalar("context","lowpass_line",cfg->lowpassLine);
  FDKpsyDebugScalar("context","tns_enabled",cfg->tnsConf.tnsActive);
  FDKpsyDebugScalar("context","pns_enabled",cfg->pnsConf.usePns);
  FDKpsyDebugScalar("context","allow_ms",cfg->allowMS);
  FDKpsyDebugScalar("context","allow_is",cfg->allowIS);
  FDKpsyDebugScalar("context","is_lfe",state->isLFE);
  FDKpsyDebugScalar("context","group_count",state->blockSwitchingControl.noOfGroups);
  FDKpsyDebugInt("context","group_lengths",state->blockSwitchingControl.groupLen,
                 state->blockSwitchingControl.noOfGroups);
  FDKpsyDebugInt("context","offsets",cfg->sfbOffset,cfg->sfbCnt+1);
  FDKpsyDebugInt("sfb","offsets",cfg->sfbOffset,cfg->sfbCnt+1);
  FDKpsyDebugScalar("masking","max_allowed_increase",cfg->maxAllowedIncreaseFactor);
  FDKpsyDebugSgl("masking","min_remaining_factor",&cfg->minRemainingThresholdFactor,1,0,"factor");
  FDKpsyDebugDbl("masking","clip_energy_config",&cfg->clipEnergy,1,0,"pcm_squared");
  FDKpsyDebugDbl("masking","mask_low_factor",cfg->sfbMaskLowFactor,cfg->sfbCnt,0,"factor");
  FDKpsyDebugDbl("masking","mask_high_factor",cfg->sfbMaskHighFactor,cfg->sfbCnt,0,"factor");
  FDKpsyDebugDbl("masking","pcm_floor_config",cfg->sfbPcmQuantThreshold,cfg->sfbCnt,-16,"pcm_squared");
  FDKpsyDebugDbl("masking","spread_energy_low_factor",cfg->sfbMaskLowFactorSprEn,cfg->sfbCnt,0,"factor");
  FDKpsyDebugDbl("masking","spread_energy_high_factor",cfg->sfbMaskHighFactorSprEn,cfg->sfbCnt,0,"factor");
  FDKpsyDebugDbl("context","min_snr_ld_config",cfg->sfbMinSnrLdData,cfg->sfbCnt,0,"ld64");
  FDKpsyDebugDbl("tns","acf_window_high",cfg->tnsConf.acfWindow[0],cfg->tnsConf.maxOrder+4,0,"factor");
  FDKpsyDebugDbl("tns","acf_window_low",cfg->tnsConf.acfWindow[1],cfg->tnsConf.maxOrder+4,0,"factor");
  FDKpsyDebugInt("tns","limit_orders",cfg->tnsConf.confTab.tnsLimitOrder,2);
  FDKpsyDebugInt("tns","acf_split",cfg->tnsConf.confTab.acfSplit,2);
  if (cfg->pnsConf.usePns) {
    FDKpsyDebugScalar("pns","algorithm_flags",cfg->pnsConf.np.detectionAlgorithmFlags);
    FDKpsyDebugScalar("pns","gain_threshold",cfg->pnsConf.np.tnsGainThreshold);
    FDKpsyDebugScalar("pns","gain_pns_threshold",cfg->pnsConf.np.tnsPNSGainThreshold);
    FDKpsyDebugDbl("pns","ref_power",&cfg->pnsConf.np.refPower,1,0,"internal");
    FDKpsyDebugDbl("pns","ref_tonality",&cfg->pnsConf.np.refTonality,1,0,"factor");
    FDKpsyDebugSgl("pns","power_curve",cfg->pnsConf.np.powDistPSDcurve,cfg->sfbActive,0,"factor");
    FDKpsyDebugSgl("pns","gap_fill_threshold",&cfg->pnsConf.np.gapFillThr,1,0,"factor");
  }
}
extern "C" void FDKpsyDebugBands(const char *phase,const PSY_DATA *p,
                                 const PSY_CONFIGURATION *cfg,int stride,int windows) {
  if (!active("energy") && !active("masking")) return;
  for (int w=0;w<windows;++w) {
    FDKpsyDebugSelect(g.currentChannel,w,p->mdctScale);
    named("energy",phase,"energy",p->sfbEnergy.Long+w*stride,p->sfbActive,2*p->mdctScale,"pcm_squared");
    /* SHORT TNS recomputes linear energy only; its LD is refreshed after grouping. */
    if (windows==1 || std::strcmp(phase,"post_tns"))
      named("energy",phase,"energy_ld",p->sfbEnergyLdData.Long+w*stride,p->sfbActive,2*p->mdctScale,"ld64");
    char n[96];std::snprintf(n,sizeof(n),"%s.headroom",phase);
    FDKpsyDebugInt("energy",n,p->sfbMaxScaleSpec.Long+w*stride,p->sfbActive);
    named("masking",phase,"seed",p->sfbThreshold.Long+w*stride,p->sfbActive,2*p->mdctScale-THR_SHIFTBITS,"pcm_squared");
  }
  (void)cfg;
}
extern "C" void FDKpsyDebugTns(const char *phase,const TNS_CONFIG *cfg,
                               const TNS_DATA *data,const TNS_INFO *info,int w) {
  if (!active("tns")) return;
  g.window=w;
  char n[96];
#define SCALAR(field,value) do {std::snprintf(n,sizeof(n),"%s.%s",phase,field);FDKpsyDebugScalar("tns",n,value);} while(0)
  SCALAR("enabled",cfg->tnsActive);
  SCALAR("max_order",cfg->maxOrder);
  SCALAR("coef_res",cfg->coefRes);
  SCALAR("num_filters",info->numOfFilters[w]);
  SCALAR("filters_merged",data->filtersMerged);
  SCALAR("lpc_stop_line",cfg->lpcStopLine);
  SCALAR("lpc_stop_band",cfg->lpcStopBand);
  std::snprintf(n,sizeof(n),"%s.start_lines",phase);FDKpsyDebugInt("tns",n,cfg->lpcStartLine,2);
  std::snprintf(n,sizeof(n),"%s.start_bands",phase);FDKpsyDebugInt("tns",n,cfg->lpcStartBand,2);
  std::snprintf(n,sizeof(n),"%s.thresh_on",phase);FDKpsyDebugInt("tns",n,cfg->confTab.threshOn,2);
  const TNS_SUBBLOCK_INFO *b=g.context[g.currentChannel].block==SHORT_WINDOW ?
    &data->dataRaw.Short.subBlockInfo[w] : &data->dataRaw.Long.subBlockInfo;
  std::snprintf(n,sizeof(n),"%s.active",phase);FDKpsyDebugInt("tns",n,b->tnsActive,2);
  std::snprintf(n,sizeof(n),"%s.gain_x1000",phase);FDKpsyDebugInt("tns",n,b->predictionGain,2);
  for (int f=0;f<info->numOfFilters[w];++f) {
    std::snprintf(n,sizeof(n),"%s.order",phase);FDKpsyDebugScalar("tns",n,info->order[w][f],f);
    std::snprintf(n,sizeof(n),"%s.direction",phase);FDKpsyDebugScalar("tns",n,info->direction[w][f],f);
    std::snprintf(n,sizeof(n),"%s.length",phase);FDKpsyDebugScalar("tns",n,info->length[w][f],f);
    std::snprintf(n,sizeof(n),"%s.quantized_coef",phase);FDKpsyDebugInt("tns",n,info->coef[w][f],info->order[w][f],f);
  }
#undef SCALAR
}
extern "C" void FDKpsyDebugOutput(const PSY_OUT_CHANNEL *p,const PSY_OUT_ELEMENT *element,int channels) {
  if (!active("output")) return;
  g.window=-1;g.context[g.currentChannel].exponent=p->mdctScale;
  g.context[g.currentChannel].codedBands=p->maxSfbPerGroup;
  g.context[g.currentChannel].tableBands=p->sfbPerGroup;
  FDKpsyDebugScalar("output","sfb_count",p->sfbCnt);
  FDKpsyDebugScalar("output","sfb_per_group",p->sfbPerGroup);
  FDKpsyDebugScalar("output","max_sfb_per_group",p->maxSfbPerGroup);
  FDKpsyDebugScalar("output","grouping_mask",p->groupingMask);
  FDKpsyDebugInt("output","offsets",p->sfbOffsets,p->sfbCnt+1);
  FDKpsyDebugDbl("output","spectrum",p->mdctSpectrum,1024,p->mdctScale,"pcm");
  FDKpsyDebugDbl("output","energy",p->sfbEnergy,p->sfbCnt,2*p->mdctScale,"pcm_squared");
  FDKpsyDebugDbl("output","spread_energy",p->sfbSpreadEnergy,p->sfbCnt,2*p->mdctScale,"pcm_squared");
  FDKpsyDebugDbl("output","energy_ld",p->sfbEnergyLdData,p->sfbCnt,2*p->mdctScale,"ld64");
  FDKpsyDebugDbl("output","threshold_ld",p->sfbThresholdLdData,p->sfbCnt,2*p->mdctScale,"ld64");
  FDKpsyDebugDbl("output","min_snr_ld",p->sfbMinSnrLdData,p->sfbCnt,0,"ld64");
  FDKpsyDebugInt("output","noise_nrg",p->noiseNrg,p->sfbCnt);
  FDKpsyDebugInt("pns","final.noise_nrg",p->noiseNrg,p->sfbCnt);
  FDKpsyDebugInt("output","is_book",p->isBook,p->sfbCnt);
  FDKpsyDebugInt("output","is_scale",p->isScale,p->sfbCnt);
  if (channels==2) {
    FDKpsyDebugScalar("output","common_window",element->commonWindow);
    FDKpsyDebugScalar("output","ms_digest",element->toolsInfo.msDigest);
    FDKpsyDebugInt("output","ms_mask",element->toolsInfo.msMask,p->sfbCnt);
  }
  /* Mono toolsInfo is not a defined stereo result; do not read its mask. */
}
