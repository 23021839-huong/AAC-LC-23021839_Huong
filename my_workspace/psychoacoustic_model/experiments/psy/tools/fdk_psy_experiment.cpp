// Real native FDK AAC-LC encode/decode. Timers wrap only aacEncEncode calls.
#include "aacenc_lib.h"
#include "aacdecoder_lib.h"
#include "psy_experiment.h"
#include "wav_pcm.h"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs = std::filesystem;
namespace {
#ifdef PSY_EXPERIMENT
constexpr bool controls_compiled=true;
#else
constexpr bool controls_compiled=false;
#endif
const char *modes[] = {"PSY_TONALITY_ON_TNS_ON","PSY_TONALITY_ON_TNS_OFF","PSY_TONALITY_OFF_TNS_ON","PSY_TONALITY_OFF_TNS_OFF"};
const char *sequences[] = {"ONLY_LONG_SEQUENCE", "LONG_START_SEQUENCE", "EIGHT_SHORT_SEQUENCE", "LONG_STOP_SEQUENCE"};
std::string observed_count(int value) { return controls_compiled ? std::to_string(value) : "null"; }
struct Options {fs::path input="my_workspace/INPUT/data/abc_votay.wav",output="my_workspace/psychoacoustic_model/experiments/psy/native";int mode=-1,runs=10,profiles=10,pns=-1;};
Options parse(int argc,char **argv) {
 Options o;
 for(int i=1;i<argc;++i){std::string a=argv[i];
  if(a=="--help"){std::cout<<"fdk_psy_experiment --input WAV --output-dir DIR --mode BASELINE|PSY_TONALITY_ON_TNS_ON|PSY_TONALITY_ON_TNS_OFF|PSY_TONALITY_OFF_TNS_ON|PSY_TONALITY_OFF_TNS_OFF --runs N --profile-runs N --expected-pns -1|0|1 --bitrate 64000\n";std::exit(0);}
  if(++i>=argc)throw std::runtime_error("Missing value for "+a);std::string v=argv[i];
  if(a=="--input")o.input=v;else if(a=="--output-dir")o.output=v;
  else if(a=="--mode"){o.mode=-2;if(v=="BASELINE")o.mode=-1;for(int j=0;j<4;++j)if(v==modes[j])o.mode=j;if(o.mode==-2)throw std::runtime_error("Invalid Psy mode");}
  else {std::size_t used=0;int n=std::stoi(v,&used);if(used!=v.size())throw std::runtime_error("Invalid integer");
   if(a=="--runs")o.runs=n;else if(a=="--profile-runs")o.profiles=n;else if(a=="--expected-pns")o.pns=n;
   else if(a=="--bitrate"){if(n!=64000)throw std::runtime_error("Controlled bitrate must be64000");}
   else throw std::runtime_error("Unknown option: "+a);}
 }
 if(o.runs<1 || o.runs>1000 || o.profiles<1 || o.profiles>1000 || o.pns < -1 || o.pns>1)throw std::runtime_error("Invalid runs/profile/PNS selection");
 return o;
}
void enc_check(AACENC_ERROR status, const char *action) {
  if (status != AACENC_OK) {
    std::ostringstream s; s << action << ": FDK encoder error 0x" << std::hex << int(status);
    throw std::runtime_error(s.str());
  }
}
void dec_check(AAC_DECODER_ERROR status, const char *action) {
  if (status != AAC_DEC_OK) {
    std::ostringstream s; s << action << ": FDK decoder error 0x" << std::hex << int(status);
    throw std::runtime_error(s.str());
  }
}
struct Encoder { HANDLE_AACENCODER handle=nullptr; ~Encoder(){if(handle) aacEncClose(&handle);} };
struct Decoder { HANDLE_AACDECODER handle=nullptr; ~Decoder(){if(handle) aacDecoder_Close(handle);} };
struct Encoded {
  std::vector<unsigned char> bytes;
  std::vector<FDK_PSY_EVENT> trace;
  AACENC_InfoStruct info{};
  double milliseconds=0;
  unsigned packets=0;
  FDK_PSY_PROFILE profile{};
};
void observe(const FDK_PSY_EVENT *event, void *context) {
  static_cast<std::vector<FDK_PSY_EVENT>*>(context)->push_back(*event);
}
Encoded encode(TraceWav &wav, int mode, bool collect_trace, int expected_pns=-1, int profile_flag=0) {
  Encoded result;
  result.bytes.reserve((wav.sample_frames/1024+10)*8192);
  result.trace.reserve((wav.sample_frames/1024+10)*wav.channels);
#ifdef PSY_EXPERIMENT
  if(FDKpsyExperimentConfigure(mode,expected_pns,profile_flag,collect_trace ? observe : nullptr,&result.trace))throw std::runtime_error("Psy controls rejected");
#else
  if(mode!=-1)throw std::runtime_error("UNSUPPORTED: baseline build has no Psy control");
#endif
  Encoder e;
  enc_check(aacEncOpen(&e.handle,0,wav.channels), "open");
  enc_check(aacEncoder_SetParam(e.handle,AACENC_AOT,2), "AOT");
  enc_check(aacEncoder_SetParam(e.handle,AACENC_SAMPLERATE,wav.sample_rate), "sample rate");
  enc_check(aacEncoder_SetParam(e.handle,AACENC_CHANNELMODE,wav.channels==1 ? MODE_1 : MODE_2), "channels");
  enc_check(aacEncoder_SetParam(e.handle,AACENC_CHANNELORDER,1), "WAV order");
  enc_check(aacEncoder_SetParam(e.handle,AACENC_GRANULE_LENGTH,1024), "granule");
  enc_check(aacEncoder_SetParam(e.handle,AACENC_BITRATE,64000), "bitrate");
  enc_check(aacEncoder_SetParam(e.handle,AACENC_BITRATEMODE,0), "CBR mode");
  enc_check(aacEncoder_SetParam(e.handle,AACENC_TRANSMUX,TT_MP4_ADTS), "ADTS");
  enc_check(aacEncoder_SetParam(e.handle,AACENC_AFTERBURNER,1), "afterburner");
  enc_check(aacEncEncode(e.handle,nullptr,nullptr,nullptr,nullptr), "init");
  enc_check(aacEncInfo(e.handle,&result.info), "info");
  if (result.info.frameLength != 1024) throw std::runtime_error("AAC-LC frame length is not 1024");
  std::vector<unsigned char> out(std::max<unsigned>(result.info.maxOutBufBytes,8192));
  std::size_t pos=0; int flush_calls=0;
  using Clock=std::chrono::steady_clock;
  for (;;) {
    bool flush=pos==wav.pcm.size();
    int count=flush ? 0 : int(std::min<std::size_t>(wav.pcm.size()-pos,1024*wav.channels));
    void *ip=flush ? nullptr : static_cast<void*>(wav.pcm.data()+pos), *op=out.data();
    int iid=IN_AUDIO_DATA, isize=count*sizeof(INT_PCM), iesize=sizeof(INT_PCM);
    int oid=OUT_BITSTREAM_DATA, osize=int(out.size()), oesize=1;
    AACENC_BufDesc in{}, output{};
    in.numBufs=1; in.bufs=&ip; in.bufferIdentifiers=&iid; in.bufSizes=&isize; in.bufElSizes=&iesize;
    output.numBufs=1; output.bufs=&op; output.bufferIdentifiers=&oid; output.bufSizes=&osize; output.bufElSizes=&oesize;
    AACENC_InArgs ia{}; AACENC_OutArgs oa{}; ia.numInSamples=flush ? -1 : count;
    auto begin=Clock::now();
    auto status=aacEncEncode(e.handle,&in,&output,&ia,&oa);
    auto end=Clock::now();
    result.milliseconds+=std::chrono::duration<double,std::milli>(end-begin).count();
    if (status==AACENC_ENCODE_EOF) break;
    enc_check(status,"encode");
    if (oa.numOutBytes<0 || oa.numOutBytes>osize || oa.numInSamples<0 || oa.numInSamples>count)
      throw std::runtime_error("Encoder buffer accounting error");
    if (oa.numOutBytes) {
      result.bytes.insert(result.bytes.end(),out.begin(),out.begin()+oa.numOutBytes);
      ++result.packets;
    }
    pos+=oa.numInSamples;
    if (!flush && !oa.numInSamples && !oa.numOutBytes) throw std::runtime_error("Encoder made no progress");
    if (flush && ++flush_calls>64) throw std::runtime_error("Encoder flush did not terminate");
  }
#ifdef PSY_EXPERIMENT
  FDKpsyExperimentGetProfile(&result.profile);
#endif
  return result;
}
struct Decoded {
  std::vector<INT_PCM> pcm;
  int sample_rate=0, channels=0, frames=0, additional_delay=0, flush_samples=0;
  FDK_PSY_DECODER_CHECK tns_check{};
};
Decoded decode(std::vector<unsigned char> &bytes) {
#ifdef PSY_EXPERIMENT
  FDKpsyExperimentDecoderReset();
#endif
  Decoder d; d.handle=aacDecoder_Open(TT_MP4_ADTS,1);
  if (!d.handle) throw std::runtime_error("Decoder open failed");
  dec_check(aacDecoder_SetParam(d.handle,AAC_PCM_OUTPUT_CHANNEL_MAPPING,1),"decoder WAV order");
  dec_check(aacDecoder_SetParam(d.handle,AAC_PCM_LIMITER_ENABLE,0),"disable PCM limiter");
  // Spectral muting has no concealment lookahead; every decode must return OK.
  dec_check(aacDecoder_SetParam(d.handle,AAC_CONCEAL_METHOD,0),"decoder concealment method");
  Decoded result;
  std::vector<INT_PCM> frame(2048*2);
  std::size_t pos=0;
  while (pos<bytes.size()) {
    if (bytes.size()-pos<7 || bytes[pos]!=0xff || (bytes[pos+1]&0xf6)!=0xf0)
      throw std::runtime_error("Invalid/truncated ADTS header");
    unsigned size=((bytes[pos+3]&3)<<11)|(bytes[pos+4]<<3)|(bytes[pos+5]>>5);
    if (size<7 || size>bytes.size()-pos) throw std::runtime_error("Truncated ADTS frame");
    UCHAR *p=bytes.data()+pos; UINT capacity=size, valid=size;
    dec_check(aacDecoder_Fill(d.handle,&p,&capacity,&valid),"fill decoder");
    if (valid) throw std::runtime_error("Decoder did not consume complete ADTS packet");
    dec_check(aacDecoder_DecodeFrame(d.handle,frame.data(),int(frame.size()),0),"decode frame");
    CStreamInfo *info=aacDecoder_GetStreamInfo(d.handle);
    if (info->aot!=AOT_AAC_LC || info->frameSize!=1024 || info->numChannels<1 || info->numChannels>2)
      throw std::runtime_error("Unexpected decoder stream configuration");
    if (result.frames && (result.sample_rate!=info->sampleRate || result.channels!=info->numChannels))
      throw std::runtime_error("Decoder stream configuration changed");
    result.sample_rate=info->sampleRate; result.channels=info->numChannels;
    result.additional_delay=info->outputDelay;
    result.pcm.insert(result.pcm.end(),frame.begin(),frame.begin()+info->frameSize*info->numChannels);
    ++result.frames; pos+=size;
  }
  for (int pending=result.additional_delay; pending>0; pending-=1024) {
    dec_check(aacDecoder_DecodeFrame(d.handle,frame.data(),int(frame.size()),AACDEC_FLUSH),"decoder flush");
    result.pcm.insert(result.pcm.end(),frame.begin(),frame.begin()+1024*result.channels);
    result.flush_samples+=1024;
  }
#ifdef PSY_EXPERIMENT
  FDKpsyExperimentDecoderGet(&result.tns_check);
#endif
  return result;
}
void little(std::ostream &out, std::uint32_t value, int count) {
  for (int i=0; i<count; ++i) out.put(char(value>>(8*i)));
}
void write_wav(const fs::path &path, const Decoded &d) {
  if (d.pcm.size()> (std::numeric_limits<std::uint32_t>::max()-36)/2)
    throw std::runtime_error("Decoded WAV exceeds RIFF size limit");
  std::uint32_t size=std::uint32_t(d.pcm.size()*2);
  std::ofstream f(path,std::ios::binary);
  f.write("RIFF",4); little(f,size+36,4); f.write("WAVEfmt ",8); little(f,16,4);
  little(f,1,2); little(f,d.channels,2); little(f,d.sample_rate,4);
  little(f,d.sample_rate*d.channels*2,4); little(f,d.channels*2,2); little(f,16,2);
  f.write("data",4); little(f,size,4);
  for (INT_PCM v:d.pcm) little(f,std::uint16_t(v),2);
  f.close(); if (!f) throw std::runtime_error("Cannot write decoded WAV");
}
}

std::string integers(const int *p,int n) {
 std::ostringstream s;for(int i=0;i<n;++i){if(i)s<<';';s<<p[i];}return s.str();
}
int main(int argc,char **argv) {
 Options o;
 try {
  static_assert(sizeof(INT_PCM)==2,"PCM16 required");o=parse(argc,argv);fs::create_directories(o.output);
  {std::ofstream f(o.output/"run_metadata.json");f<<"{\"complete\":false}\n";}
  TraceWav wav=read_trace_wav(o.input);
  if(wav.bits!=16 || wav.format!=1)throw std::runtime_error("Controlled experiment requires integer PCM16 WAV");
  Encoded reference=encode(wav,o.mode,true,o.pns); // trace warm-up, never included in timed results
  std::vector<double> times;
  for(int i=0;i<o.runs;++i){Encoded r=encode(wav,o.mode,false,o.pns);if(r.bytes!=reference.bytes)throw std::runtime_error("Timed bitstream differs from warm-up");times.push_back(r.milliseconds);}
  std::ofstream pf(o.output/"native_profile.csv");pf<<"run_index,profile_encode_time_ms,psy_model_time_ms,tonality_time_ms,tns_analysis_time_ms,tns_filtering_time_ms,psy_calls,tonality_calls,tns_analysis_calls,tns_filtering_calls\n";
  for(int i=0;i<(controls_compiled ? o.profiles : 0);++i){Encoded r=encode(wav,o.mode,false,o.pns,1);if(r.bytes!=reference.bytes)throw std::runtime_error("Profile bitstream differs from reference");
   pf<<std::setprecision(17)<<i<<','<<r.milliseconds;for(int k=0;k<4;++k)pf<<','<<r.profile.nanoseconds[k]/1e6;for(int k=0;k<4;++k)pf<<','<<r.profile.calls[k];pf<<'\n';}
  pf.close();if(!pf)throw std::runtime_error("Cannot write profile");
  std::ofstream aac(o.output/"encoded.aac",std::ios::binary);aac.write(reinterpret_cast<const char*>(reference.bytes.data()),reference.bytes.size());aac.close();if(!aac)throw std::runtime_error("Cannot write AAC");
  Decoded decoded=decode(reference.bytes);
  if(decoded.sample_rate!=wav.sample_rate || decoded.channels!=wav.channels || unsigned(decoded.frames)!=reference.packets)throw std::runtime_error("Decode configuration mismatch");
  write_wav(o.output/"decoded.wav",decoded);
  std::ofstream trace(o.output/"psy_trace.csv");trace<<"frame_index,channel_index,tonality_enabled,tonality_applied,tns_enabled,tns_applied,pns_enabled,pns_used,window_sequence,window_shape,tonality_value,tonality_values_q15,tns_filter_order,tns_filter_count,tns_start_band,tns_stop_band,tns_syntax_start_band,tns_syntax_stop_band,mdct_hash\n";
  int filters=0,usedFrames=0,toneFrames=0;bool pns_seen=false;int effective_pns=-1;
  for(const auto &e:reference.trace){double tone=0;for(int j=0;j<e.tonality_count;++j)tone+=e.tonality_q15[j]/32768.;
   trace<<e.frame_index<<','<<e.channel<<','<<e.tonality_enabled<<','<<e.tonality_applied<<','<<e.tns_enabled<<','<<e.tns_applied<<','<<e.pns_enabled<<','<<e.pns_used<<','<<sequences[e.sequence]<<','<<e.shape<<',';
   if(e.tonality_applied)trace<<std::setprecision(17)<<tone/e.tonality_count;
   trace<<','<<integers(e.tonality_q15,e.tonality_count)<<','<<integers(e.orders,e.filter_count)<<','<<e.filter_count<<','<<integers(e.start_bands,e.filter_count)<<','<<integers(e.stop_bands,e.filter_count)<<','<<integers(e.syntax_start_bands,e.filter_count)<<','<<integers(e.syntax_stop_bands,e.filter_count)<<','<<e.mdct_hash<<'\n';
   filters+=e.filter_count;usedFrames+=e.filter_count>0;toneFrames+=e.tonality_applied;
   if(pns_seen && effective_pns!=e.pns_enabled)throw std::runtime_error("PNS configuration changes inside encode");effective_pns=e.pns_enabled;pns_seen=true;
  }
  trace.close();if(!trace)throw std::runtime_error("Cannot write trace");
#ifdef PSY_EXPERIMENT
  if(reference.trace.size()!=reference.packets*wav.channels)throw std::runtime_error("Trace/packet count mismatch");
  if(filters!=decoded.tns_check.signaled_filters || usedFrames!=decoded.tns_check.present_flags)throw std::runtime_error("Encoder TNS metadata differs from decoded syntax");
  if(o.mode==1 || o.mode==3)if(filters || decoded.tns_check.present_flags)throw std::runtime_error("TNS OFF still signals filters");
#endif
  std::ofstream f(o.output/"run_metadata.json");f<<std::setprecision(17)<<"{\n\"complete\":true,\"mode\":\""<<(o.mode<0?"BASELINE":modes[o.mode])<<"\",\"sample_rate\":"<<wav.sample_rate<<",\"channels\":"<<wav.channels
   <<",\"source_samples_per_channel\":"<<wav.sample_frames<<",\"target_bitrate_bps\":64000,\"aot\":2,\"frame_length\":1024,\"afterburner\":1,\"bitrate_mode\":0"
   <<",\"encoder_delay_samples\":"<<reference.info.nDelay<<",\"decoder_additional_delay_samples\":"<<decoded.additional_delay<<",\"decoded_samples_per_channel\":"<<decoded.pcm.size()/decoded.channels
   <<",\"adts_frames\":"<<decoded.frames<<",\"aac_size_bytes\":"<<reference.bytes.size()<<",\"effective_pns_enabled\":"<<observed_count(effective_pns)
   <<",\"tonality_applied_frames\":"<<observed_count(toneFrames)<<",\"encoder_tns_filters\":"<<observed_count(filters)<<",\"decoder_tns_filters\":"<<observed_count(decoded.tns_check.signaled_filters)<<",\"decoder_tns_present_flags\":"<<observed_count(decoded.tns_check.present_flags)
   <<",\"decoder_errors\":0,\"controls_compiled\":"<<(controls_compiled?"true":"false")<<",\"decoder_syntax_observed\":"<<(controls_compiled?"true":"false")
   <<",\"warmup_runs\":1,\"profile_runs\":"<<(controls_compiled?o.profiles:0)<<",\"main_timing_has_trace\":false,\"main_timing_has_stage_clocks\":false,\"bitstreams_stable\":true"
   <<",\"psy_profile_scope\":\"whole FDKaacEnc_psyMain wrapper including block switching, window/MDCT and history; not logical Psy only\""
   <<",\"window_policy\":\"native unchanged\",\"fft_mode\":\"native original\",\"timing_scope\":\"aacEncEncode calls after initialization including flush; no I/O/decode/trace/profile clocks\",\"encoding_time_ms\":[";
  for(std::size_t i=0;i<times.size();++i){if(i)f<<',';f<<times[i];}f<<"]}\n";f.close();if(!f)throw std::runtime_error("Cannot finish metadata");
  std::cout<<(o.mode<0?"BASELINE":modes[o.mode])<<": "<<decoded.frames<<" frames, "<<reference.bytes.size()<<" bytes, "<<times.size()<<" measured runs, tone_frames="<<toneFrames<<", TNS_filters="<<filters<<", PNS="<<effective_pns<<"; FDK decode OK\n";
  return 0;
 }catch(const std::exception &e){std::string message=e.what();
#ifdef PSY_EXPERIMENT
  if(FDKpsyExperimentError()[0])message=FDKpsyExperimentError();
#endif
  std::cerr<<message<<'\n';return message.find("UNSUPPORTED:")==0?2:1;
 }
}
