/* Integer-only sink. Never writes native buffers or controls codec decisions. */
#include "quant_debug.h"
#include "aacEnc_rom.h"
#include <cstdio>
#include <cstring>
#include <cstdint>

namespace {
struct Context {
  const PSY_OUT_CHANNEL *psy;
  const QC_OUT_CHANNEL *qc;
  int element, channel, block, shape, scale, sfbCnt, stride, active, grouping;
  int starts[MAX_GROUPED_SFB], stops[MAX_GROUPED_SFB];
  int validBands[MAX_GROUPED_SFB], validOffsets[MAX_GROUPED_SFB+1], validLines[1024];
  int groupLen[4];
};
struct State {
  FILE *file; int frame, first, end, selector, rate, bitrate, current;
  unsigned stages; int iterations, lines, selected, trial, baseLine, localLine, trialCount;
  const char *kind, *phase, *source, *function;
  int iteration, candidate, sfb, sourceLine;
  Context context[2]; char error[256]; unsigned long long sequence;
} g;
void fail(const char *message) { if (!g.error[0]) std::snprintf(g.error,sizeof(g.error),"%s",message); }
unsigned stage_bit(const char *stage) {
  const char *names[]={"form_factor","pe","bit_allocation","threshold","scalefactor","global_gain","quantization","iterations"};
  for(int i=0;i<8;i++) if(!std::strcmp(stage,names[i])) return 1u<<i;
  return 0;
}
bool active(const char *stage) {
  return g.file && !g.error[0] && g.frame>=g.first && g.frame<g.end &&
    g.current>=0 && g.current<2 && g.context[g.current].psy &&
    (g.selector<0 || g.selector==g.current) &&
    (!stage_bit(stage) || (g.stages&stage_bit(stage))) &&
    (std::strcmp(stage,"iterations") || g.iterations) &&
    (g.iterations || g.candidate<0 || !std::strcmp(stage,"final") || !std::strcmp(stage,"build") || !std::strcmp(stage,"input") || !std::strcmp(stage,"context"));
}
void quoted(const char *text) {
  std::fputc('"',g.file);
  for(const unsigned char *p=(const unsigned char *)(text?text:"");*p;p++) {
    if(*p=='"' || *p=='\\') std::fputc('\\',g.file);
    if(*p<32) std::fprintf(g.file,"\\u%04x",*p); else std::fputc(*p,g.file);
  }
  std::fputc('"',g.file);
}
bool valid(const Context &c,int layout,int i) {
  if(layout==QD_SFB) return i<c.sfbCnt && c.validBands[i];
  if(layout==QD_OFFSETS) return i<=c.sfbCnt && c.validOffsets[i];
  if(layout==QD_SPECTRUM) return i<1024 && c.validLines[i];
  return true;
}
template<class T> void record(const char *stage,const char *name,const T *data,int count,
 int fraction,int exponent,const char *unit,int index,int layout,bool isSigned=true,int width=0,bool shared=false) {
  if(!active(stage)) return;
  if(!data || count<0 || count>2048) {fail("Invalid Quant observation dimensions");return;}
  const Context &c=g.context[g.current];
  std::fprintf(g.file,"{\"schema_version\":1,\"sequence\":%llu,\"frame\":%d,\"element\":%d,\"channel\":%d,\"stage\":",++g.sequence,g.frame,c.element,c.channel);
  quoted(stage);std::fputs(",\"name\":",g.file);quoted(name);
  std::fputs(",\"value_scope\":",g.file);quoted(shared?"element":"channel");
  std::fputs(",\"loop_kind\":",g.file);quoted(g.kind);std::fputs(",\"phase\":",g.file);quoted(g.phase);
  std::fprintf(g.file,",\"iteration\":%d,\"candidate\":%d,\"sfb\":%d,\"index\":%d,\"count\":%d,\"bit_width\":%d,\"signed\":%s,\"fraction_bits\":%d,\"exponent\":%d,\"unit\":",
    g.iteration,g.candidate,g.sfb,index,count,width?width:(int)sizeof(T)*8,isSigned?"true":"false",fraction,exponent);
  quoted(unit);
  std::fprintf(g.file,",\"sample_rate\":%d,\"bitrate\":%d,\"frame_length\":1024,\"block_type\":%d,\"window_shape\":%d,\"mdct_scale\":%d,\"sfb_count\":%d,\"sfb_per_group\":%d,\"max_sfb_per_group\":%d,\"grouping_mask\":%d,\"group_lengths\":[%d,%d,%d,%d],\"source\":",
    g.rate,g.bitrate,c.block,c.shape,c.scale,c.sfbCnt,c.stride,c.active,c.grouping,c.groupLen[0],c.groupLen[1],c.groupLen[2],c.groupLen[3]);
  quoted(g.source);std::fputs(",\"function\":",g.file);quoted(g.function);
  std::fprintf(g.file,",\"source_line\":%d,\"stage_mask\":%u,\"iteration_log\":%s,\"line_log\":%s,\"raw\":[",g.sourceLine,g.stages,g.iterations?"true":"false",g.lines?"true":"false");
  for(int i=0;i<count;i++) {
    if(i)std::fputc(',',g.file);
    if(!valid(c,layout,i))std::fputs("null",g.file);else std::fprintf(g.file,"%lld",(long long)data[i]);
  }
  std::fputs("],\"raw_hex\":[",g.file);
  for(int i=0;i<count;i++) {
    if(i)std::fputc(',',g.file);
    if(!valid(c,layout,i))std::fputs("null",g.file);
    else {
      unsigned long long mask=(width?width:(int)sizeof(T)*8)==64?~0ull:((1ull<<(width?width:(int)sizeof(T)*8))-1);
      std::fprintf(g.file,"\"%0*llX\"",(width?width:(int)sizeof(T)*8)/4,(unsigned long long)data[i]&mask);
    }
  }
  std::fputs("],\"valid_indices\":[",g.file);int written=0;
  for(int i=0;i<count;i++)if(valid(c,layout,i))std::fprintf(g.file,"%s%d",written++?",":"",i);
  std::fputs("]}\n",g.file);if(std::ferror(g.file))fail("Cannot write Quant trace");
}
void named(const char *stage,const char *phase,const char *name,const FIXP_DBL *p,int n,int e,const char *unit) {
  char field[120];std::snprintf(field,sizeof(field),"%s.%s",phase,name);
  FDKquantDebugDbl(stage,field,p,n,e,unit,0,QD_SFB);
}
}
extern "C" int FDKquantDebugConfigure(const char *path,int first,int end,int channel,int rate,int bitrate,unsigned stages,int iterations,int lines) {
  if(g.file)std::fclose(g.file);std::memset(&g,0,sizeof(g));g.frame=-1;g.current=-1;
  g.iteration=g.candidate=g.sfb=-1;g.kind="none";g.phase="none";g.source="";g.function="";
  if(!path || first<0 || end<=first || channel < -1 || channel>1 || rate<=0 || bitrate<=0 || stages>255) {fail("Invalid Quant selection");return 1;}
  g.first=first;g.end=end;g.selector=channel;g.rate=rate;g.bitrate=bitrate;g.stages=stages;g.iterations=iterations;g.lines=lines;
  g.file=std::fopen(path,"w");if(!g.file){fail("Cannot open Quant trace");return 1;}return 0;
}
extern "C" const char *FDKquantDebugError(void) {return g.error;}
extern "C" int FDKquantDebugFinish(void) {
  if(g.file){if(std::ferror(g.file))fail("Quant trace write failed");if(std::fclose(g.file))fail("Quant trace close failed");g.file=NULL;}
  if(!g.selected)fail("No requested native frame/channel observed");
  if(g.end>g.frame+1)fail("Requested frame range exceeds native encoder stream");
  return g.error[0]?1:0;
}
void FDKquantDebugBeginFrame(void) {
  if(!g.file)return;++g.frame;g.current=-1;g.trial=0;g.iteration=g.candidate=g.sfb=-1;g.kind="none";g.phase="input";
}
void FDKquantDebugLocation(const char *file,const char *function,int line) {g.source=file;g.function=function;g.sourceLine=line;}
void FDKquantDebugSelectChannel(const PSY_OUT_CHANNEL *p) {
  if(!g.file)return;for(int i=0;i<2;i++)if(g.context[i].psy==p){g.current=i;return;}
  fail("Unregistered Quant channel");
}
void FDKquantDebugSelectElement(int element) {
  for(int i=0;i<2;i++)if(g.context[i].psy && g.context[i].element==element && (g.selector<0 || g.selector==i)){g.current=i;return;}
}
void FDKquantDebugSelectShared(const PSY_OUT_CHANNEL *p) {
  FDKquantDebugSelectChannel(p);if(g.current>=0)FDKquantDebugSelectElement(g.context[g.current].element);
}
void FDKquantDebugFlags(const char *phase,const UCHAR *p,int count){record("threshold",phase,p,count,0,0,"avoid_hole_flag",0,QD_SFB,false);}
void FDKquantDebugScalar(const char *s,const char *n,long long v,int w,int f,int e,const char *u,int i) {record(s,n,&v,1,f,e,u,i,QD_DENSE,true,w);}
void FDKquantDebugSharedScalar(const char *s,const char *n,long long v,int w,int f,int e,const char *u,int i) {
  if(!g.file || g.current<0 || !g.context[g.current].psy)return;
  const int previous=g.current,element=g.context[previous].element;
  // Copy the observation (not codec state) to each selected channel's report.
  for(int ch=0;ch<2;ch++)if(g.context[ch].psy && g.context[ch].element==element){
    g.current=ch;record(s,n,&v,1,f,e,u,i,QD_DENSE,true,w,true);
  }
  g.current=previous;
}
void FDKquantDebugDbl(const char *s,const char *n,const FIXP_DBL *p,int k,int e,const char *u,int i,int l) {record(s,n,p,k,31,e,u,i,l);}
void FDKquantDebugInt(const char *s,const char *n,const INT *p,int k,int i,int l) {record(s,n,p,k,0,0,"integer",i,l);}
void FDKquantDebugShort(const char *s,const char *n,const SHORT *p,int k,int i,int l) {record(s,n,p,k,0,0,"quantized_integer",i,l);}
void FDKquantDebugUInt(const char *s,const char *n,const UINT *p,int k,int i,int l) {record(s,n,p,k,0,0,"unsigned_integer",i,l,false);}
void FDKquantDebugBindElement(int element,const ELEMENT_INFO *info,const PSY_OUT_ELEMENT *psy,const QC_OUT_ELEMENT *qc) {
  if(!g.file)return;
  for(int local=0;local<info->nChannelsInEl;local++) {
    int ch=info->ChannelIndex[local];if(ch<0 || ch>1){fail("Quant trace supports mono/stereo only");return;}
    Context &c=g.context[ch];std::memset(&c,0,sizeof(c));
    const PSY_OUT_CHANNEL *p=psy->psyOutChannel[local];c.psy=p;c.qc=qc->qcOutChannel[local];c.channel=ch;c.element=element;
    c.block=p->lastWindowSequence;c.shape=p->windowShape;c.scale=p->mdctScale;c.sfbCnt=p->sfbCnt;c.stride=p->sfbPerGroup;c.active=p->maxSfbPerGroup;c.grouping=p->groupingMask;
    if(c.sfbCnt<0 || c.sfbCnt>MAX_GROUPED_SFB || c.stride<=0 || c.active<0 || c.active>c.stride){fail("Invalid Quant SFB geometry");return;}
    int groups=c.sfbCnt/c.stride;
    if(groups>4){fail("Quant grouping exceeds context capacity");return;}
    for(int group=0;group<groups;group++)c.groupLen[group]=c.block==SHORT_WINDOW?p->groupLen[group]:1;
    for(int base=0;base<c.sfbCnt;base+=c.stride)for(int band=0;band<c.active;band++) {
      int s=base+band,start=p->sfbOffsets[s],stop=p->sfbOffsets[s+1];
      if(start<0 || stop<start || stop>1024){fail("Invalid Quant SFB offsets");return;}
      c.validBands[s]=1;c.validOffsets[s]=c.validOffsets[s+1]=1;c.starts[s]=start;c.stops[s]=stop;
      for(int line=start;line<stop;line++)c.validLines[line]=1;
    }
    g.current=ch;
    if(active("context"))++g.selected;
    FDKquantDebugScalar("build","quant_table_bits",sizeof(FIXP_QTD)*8,32,0,0,"integer");
    record("build","quant_table_q",FDKaacEnc_quantTableQ,4,sizeof(FIXP_QTD)*8-1,0,"coefficient",0,QD_DENSE);
    record("build","quant_table_e",FDKaacEnc_quantTableE,4,sizeof(FIXP_QTD)*8-1,0,"coefficient",0,QD_DENSE);
    record("build","pow34_rom",FDKaacEnc_mTab_3_4,512,sizeof(FIXP_QTD)*8-1,0,"coefficient",0,QD_DENSE);
    record("build","inverse_rom",FDKaacEnc_mTab_4_3Elc,512,31,0,"coefficient",0,QD_DENSE);
    record("build","inverse_exponent_mantissa",&FDKaacEnc_specExpMantTableCombElc[0][0],56,31,0,"coefficient",0,QD_DENSE);
    record("build","inverse_exponent_shift",&FDKaacEnc_specExpTableComb[0][0],56,0,0,"integer",0,QD_DENSE,false);
    FDKquantDebugScalar("context","sfb_count",c.sfbCnt,32,0,0,"integer");
    FDKquantDebugInt("input","offsets",p->sfbOffsets,c.sfbCnt+1,0,QD_OFFSETS);
    // LONG MDCT is initialized over 1024 lines; SHORT grouped padding is not.
    FDKquantDebugDbl("input","spectrum",p->mdctSpectrum,1024,p->mdctScale,"pcm",0,c.block==SHORT_WINDOW?QD_SPECTRUM:QD_DENSE);
    FDKquantDebugDbl("input","energy",p->sfbEnergy,c.sfbCnt,2*p->mdctScale,"pcm_squared",0,QD_SFB);
    FDKquantDebugDbl("input","energy_ld",p->sfbEnergyLdData,c.sfbCnt,2*p->mdctScale,"ld64",0,QD_SFB);
    FDKquantDebugDbl("input","threshold_ld",p->sfbThresholdLdData,c.sfbCnt,2*p->mdctScale,"ld64",0,QD_SFB);
    FDKquantDebugDbl("input","min_snr_ld",p->sfbMinSnrLdData,c.sfbCnt,0,"ld64",0,QD_SFB);
    FDKquantDebugDbl("input","spread_energy",p->sfbSpreadEnergy,c.sfbCnt,2*p->mdctScale,"pcm_squared",0,QD_SFB);
    FDKquantDebugInt("input","noise_nrg",p->noiseNrg,c.sfbCnt,0,QD_SFB);
    FDKquantDebugInt("input","is_book",p->isBook,c.sfbCnt,0,QD_SFB);
    FDKquantDebugInt("input","is_scale",p->isScale,c.sfbCnt,0,QD_SFB);
    FDKquantDebugScalar("input","common_window",psy->commonWindow,32,0,0,"integer");
    if(info->nChannelsInEl==2){FDKquantDebugScalar("input","ms_digest",psy->toolsInfo.msDigest,32,0,0,"integer");FDKquantDebugInt("input","ms_mask",psy->toolsInfo.msMask,c.sfbCnt,0,QD_SFB);}
    for(int w=0;w<(c.block==SHORT_WINDOW?8:1);w++){
      FDKquantDebugScalar("input","tns_num_filters",p->tnsInfo.numOfFilters[w],32,0,0,"integer",w);
      if(p->tnsInfo.numOfFilters[w]>0)FDKquantDebugScalar("input","tns_coef_res",p->tnsInfo.coefRes[w],32,0,0,"integer",w);
      for(int filter=0;filter<p->tnsInfo.numOfFilters[w];filter++){
        int id=w*MAX_NUM_OF_FILTERS+filter,order=p->tnsInfo.order[w][filter];
        FDKquantDebugScalar("input","tns_order",order,32,0,0,"integer",id);
        FDKquantDebugScalar("input","tns_length",p->tnsInfo.length[w][filter],32,0,0,"integer",id);
        if(order>0){
          FDKquantDebugScalar("input","tns_direction",p->tnsInfo.direction[w][filter],32,0,0,"integer",id);
          FDKquantDebugInt("input","tns_coefficients",p->tnsInfo.coef[w][filter],order,id,QD_DENSE);
        }
      }
    }
  }
}
void FDKquantDebugLoop(const char *kind,const char *phase,int iteration,int candidate,int sfb) {
  g.kind=kind;g.phase=phase;g.iteration=iteration;g.candidate=candidate;g.sfb=sfb;
}
QuantDebugScope::QuantDebugScope(const char *k,const char *p,int i,int c,int s) {
  kind=g.kind;phase=g.phase;iteration=g.iteration;candidate=g.candidate;sfb=g.sfb;FDKquantDebugLoop(k,p,i,c,s);
}
QuantDebugScope::~QuantDebugScope(){FDKquantDebugLoop(kind,phase,iteration,candidate,sfb);}
int FDKquantDebugScale(void){return g.current>=0?g.context[g.current].scale:0;}
int FDKquantDebugSelected(void){return active("final");}
int FDKquantDebugTrialCount(int n){if(n>=0)g.trialCount=n;return g.trialCount;}
int FDKquantDebugTrial(int sfb){g.sfb=sfb;g.candidate=++g.trial;return g.candidate;}
int FDKquantDebugSfb(void){return g.sfb;}
void FDKquantDebugRange(const FIXP_DBL *p,int n,int gain,int emit) {
  if(!g.file || g.current<0)return;
  const Context &c=g.context[g.current];std::uintptr_t addr=(std::uintptr_t)p,base=(std::uintptr_t)c.qc->mdctSpectrum;
  if(addr>=base && addr<base+1024*sizeof(FIXP_DBL))g.baseLine=(int)((addr-base)/sizeof(FIXP_DBL));else g.baseLine=0;
  for(int b=0;b<c.sfbCnt;b++)if(c.validBands[b] && g.baseLine>=c.starts[b] && g.baseLine<c.stops[b]){g.sfb=b;break;}
  if(emit && (n>1 || g.lines)){
    FDKquantDebugScalar("iterations","qss",gain,32,0,0,"integer",g.baseLine);
    FDKquantDebugScalar("iterations","line_count",n,32,0,0,"integer",g.baseLine);
  }
}
void FDKquantDebugLineOffset(int i){g.localLine=i;}
int FDKquantDebugLine(void){return g.baseLine+g.localLine;}
int FDKquantDebugWantLines(void){return g.lines && active("quantization");}
void FDKquantDebugThreshold(const char *phase,const PSY_OUT_CHANNEL *p,const QC_OUT_CHANNEL *q) {
  FDKquantDebugSelectChannel(p);
  named("threshold",phase,"threshold_ld",q->sfbThresholdLdData,p->sfbCnt,2*p->mdctScale,"ld64");
  named("threshold",phase,"energy_ld",q->sfbEnergyLdData,p->sfbCnt,2*p->mdctScale,"ld64");
  named("threshold",phase,"weighted_energy_ld",q->sfbWeightedEnergyLdData,p->sfbCnt,2*p->mdctScale,"ld64");
  named("threshold",phase,"min_snr_ld",q->sfbMinSnrLdData,p->sfbCnt,0,"ld64");
}
void FDKquantDebugPeBands(const PE_CHANNEL_DATA *p,const PE_DATA *all,const PSY_OUT_CHANNEL *psy,const char *phase) {
  FDKquantDebugSelectChannel(psy);char name[96];
  std::snprintf(name,sizeof(name),"%s.sfb_pe",phase);record("pe",name,p->sfbPe,psy->sfbCnt,PE_CONSTPART_SHIFT,0,"pe",0,QD_SFB);
  std::snprintf(name,sizeof(name),"%s.relevant_lines",phase);FDKquantDebugInt("pe",name,p->sfbNLines,psy->sfbCnt,0,QD_SFB);
  std::snprintf(name,sizeof(name),"%s.active_lines",phase);FDKquantDebugInt("pe",name,p->sfbNActiveLines,psy->sfbCnt,0,QD_SFB);
  std::snprintf(name,sizeof(name),"%s.channel_pe",phase);FDKquantDebugScalar("pe",name,p->pe,32,0,0,"pe");
  if(all){std::snprintf(name,sizeof(name),"%s.element_pe",phase);FDKquantDebugScalar("pe",name,all->pe,32,0,0,"pe");FDKquantDebugScalar("pe","offset",all->offset,32,0,0,"pe");}
}
void FDKquantDebugBudget(const char *phase,const QC_STATE *s,const QC_OUT *q,int available,int average) {
  if(!g.file)return;char name[96];
  for(int ch=0;ch<2;ch++)if(g.context[ch].psy){g.current=ch;int element=g.context[ch].element;
    const QC_OUT_ELEMENT *el=q->qcElement[element];const ELEMENT_BITS *bits=s->elementBits[element];
#define BUD(field,value) do{std::snprintf(name,sizeof(name),"%s.%s",phase,field);FDKquantDebugScalar("bit_allocation",name,value,32,0,0,"bits");}while(0)
    if(!std::strcmp(phase,"granted")){BUD("average_bits",average);BUD("available_bits",available);}
    BUD("reservoir",s->bitResTot);BUD("reservoir_capacity",s->bitResTotMax);
    BUD("element_reservoir",bits->bitResLevelEl);BUD("element_reservoir_capacity",bits->maxBitResBitsEl);
    BUD("granted_dyn_bits",el->grantedDynBits);BUD("static_bits",el->staticBitsUsed);BUD("extension_bits",el->extBitsUsed);
    if(std::strcmp(phase,"granted")){BUD("used_dyn_bits",el->dynBitsUsed);BUD("total_bits",q->totalBits);BUD("fill_bits",q->totFillBits);BUD("alignment_bits",q->alignBits);}
    BUD("header_bits",s->globHdrBits);
    BUD("granted_pe",el->grantedPe);BUD("granted_pe_corrected",el->grantedPeCorr);
#undef BUD
  }
}
void FDKquantDebugFinalFrame(const CHANNEL_MAPPING *cm,const PSY_OUT *psy,const QC_OUT *qc,const QC_STATE *state) {
  if(!g.file)return;g.kind="final";g.phase="accepted";g.iteration=g.candidate=g.sfb=-1;
  for(int el=0;el<cm->nElements;el++)for(int local=0;local<cm->elInfo[el].nChannelsInEl;local++) {
    const PSY_OUT_CHANNEL *p=psy->psyOutElement[el]->psyOutChannel[local];const QC_OUT_CHANNEL *q=qc->qcElement[el]->qcOutChannel[local];FDKquantDebugSelectChannel(p);
    FDKquantDebugScalar("final","global_gain",q->globalGain,32,0,0,"integer");
    FDKquantDebugInt("final","scf_relative",q->scf,p->sfbCnt,0,QD_SFB);
    FDKquantDebugShort("final","quantized_spectrum",q->quantSpec,1024,0,QD_SPECTRUM);
    FDKquantDebugUInt("final","max_in_sfb",q->maxValueInSfb,p->sfbCnt,0,QD_SFB);
    FDKquantDebugDbl("final","spectrum_before_quant",q->mdctSpectrum,1024,p->mdctScale,"pcm",0,p->lastWindowSequence==SHORT_WINDOW?QD_SPECTRUM:QD_DENSE);
    if(FDKquantDebugSelected())FDKquantDebugReconstructAccepted(p,q);
    FDKquantDebugInt("final","noise_nrg",p->noiseNrg,p->sfbCnt,0,QD_SFB);
    FDKquantDebugScalar("final","huffman_bits",q->sectionData.huffmanBits,32,0,0,"bits");
    FDKquantDebugScalar("final","side_info_bits",q->sectionData.sideInfoBits,32,0,0,"bits");
    FDKquantDebugScalar("final","scalefactor_bits",q->sectionData.scalefacBits,32,0,0,"bits");
    FDKquantDebugScalar("final","noise_bits",q->sectionData.noiseNrgBits,32,0,0,"bits");
    for(int i=0;i<q->sectionData.noOfSections;i++) {
      INT section[3]={q->sectionData.huffsection[i].sfbStart,q->sectionData.huffsection[i].sfbCnt,q->sectionData.huffsection[i].codeBook};
      FDKquantDebugInt("final","section",section,3,i,QD_DENSE);
    }
  }
  FDKquantDebugBudget("committed",state,qc);
}
