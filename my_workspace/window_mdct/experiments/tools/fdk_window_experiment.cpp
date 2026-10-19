// Real native FDK AAC-LC encode/decode. Timers wrap only aacEncEncode calls.
#include "aacenc_lib.h"
#include "aacdecoder_lib.h"
#include "window_experiment.h"
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
const char *modes[] = {"SINE_ONLY", "KBD_ONLY", "SINE_LONG_KBD_SHORT", "KBD_LONG_SINE_SHORT"};
const char *sequences[] = {"ONLY_LONG_SEQUENCE", "LONG_START_SEQUENCE", "EIGHT_SHORT_SEQUENCE", "LONG_STOP_SEQUENCE"};
struct Options { fs::path input = "my_workspace/INPUT/data/abc_votay.wav", output = "my_workspace/window_mdct/experiments/native"; int mode = 3, runs = 5; };
Options parse(int argc, char **argv) {
  Options o;
  for (int i=1; i<argc; ++i) {
    std::string a = argv[i];
    if (a == "--help") {
      std::cout << "fdk_window_experiment --input WAV --output-dir DIR --mode "
                   "SINE_ONLY|KBD_ONLY|SINE_LONG_KBD_SHORT|KBD_LONG_SINE_SHORT|DEFAULT --runs N\n";
      std::exit(0);
    }
    if (++i >= argc) throw std::runtime_error("Missing value for " + a);
    std::string v = argv[i];
    if (a == "--input") o.input=v;
    else if (a == "--output-dir") o.output=v;
    else if (a == "--mode") {
      o.mode=-2;
      if (v == "DEFAULT") o.mode=-1;
      for (int j=0; j<4; ++j) if (v == modes[j]) o.mode=j;
      if (o.mode == -2) throw std::runtime_error("Invalid window mode: " + v);
    } else if (a == "--runs") {
      std::size_t end=0; o.runs=std::stoi(v,&end);
      if (end != v.size() || o.runs<1 || o.runs>100) throw std::runtime_error("runs must be 1..100");
    } else throw std::runtime_error("Unknown option: " + a);
  }
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
  std::vector<FDK_WINDOW_EVENT> trace;
  AACENC_InfoStruct info{};
  double milliseconds=0;
  unsigned packets=0;
};
void observe(const FDK_WINDOW_EVENT *event, void *context) {
  static_cast<std::vector<FDK_WINDOW_EVENT>*>(context)->push_back(*event);
}
Encoded encode(TraceWav &wav, int mode, bool collect_trace) {
  Encoded result;
  result.bytes.reserve((wav.sample_frames/1024+10)*8192);
  result.trace.reserve((wav.sample_frames/1024+10)*wav.channels);
  if (FDKwindowExperimentConfigure(mode, collect_trace ? observe : nullptr, &result.trace))
    throw std::runtime_error("Cannot configure window policy");
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
  FDKwindowExperimentConfigure(-1,nullptr,nullptr);
  return result;
}
struct Decoded {
  std::vector<INT_PCM> pcm;
  int sample_rate=0, channels=0, frames=0, additional_delay=0, flush_samples=0;
};
Decoded decode(std::vector<unsigned char> &bytes) {
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
int main(int argc, char **argv) {
  try {
    static_assert(sizeof(INT_PCM)==2,"PCM16 build required");
    Options o=parse(argc,argv);
    fs::create_directories(o.output);
    { std::ofstream f(o.output/"run_metadata.json"); f << "{\"complete\":false}\n";
      if (!f) throw std::runtime_error("Cannot create run metadata"); }
    TraceWav wav=read_trace_wav(o.input);
    Encoded reference=encode(wav,o.mode,true); // warm-up + trace, excluded from measurements
    std::vector<double> times;
    for (int i=0; i<o.runs; ++i) {
      Encoded run=encode(wav,o.mode,false);
      if (run.bytes!=reference.bytes) throw std::runtime_error("Repeated encode differs from warm-up bitstream");
      times.push_back(run.milliseconds);
    }
    std::ofstream aac(o.output/"encoded.aac",std::ios::binary);
    aac.write(reinterpret_cast<const char*>(reference.bytes.data()),reference.bytes.size());
    aac.close(); if (!aac) throw std::runtime_error("Cannot write AAC");
    Decoded decoded=decode(reference.bytes);
    if (decoded.sample_rate!=wav.sample_rate || decoded.channels!=wav.channels || unsigned(decoded.frames)!=reference.packets)
      throw std::runtime_error("Encode/decode frame configuration mismatch");
    write_wav(o.output/"decoded.wav",decoded);
    std::ofstream trace(o.output/"frame_trace.csv");
    trace << "frame_index,channel,window_sequence,window_sequence_id,window_shape,previous_window_shape,experiment_mode,left_slope_shape,right_slope_shape,left_slope_length,right_slope_length,bootstrap\n";
    for (const auto &r:reference.trace) {
      if (r.sequence<0 || r.sequence>3 || r.left_shape<0) throw std::runtime_error("Unrecognized native window state");
      trace << r.frame_index << ',' << r.channel << ',' << sequences[r.sequence] << ',' << r.sequence << ','
            << r.shape << ',' << r.previous_shape << ',' << (o.mode<0 ? "DEFAULT" : modes[o.mode]) << ','
            << r.left_shape << ',' << r.right_shape << ',' << r.left_length << ',' << r.right_length << ',' << r.bootstrap << '\n';
    }
    trace.close(); if (!trace) throw std::runtime_error("Cannot write frame trace");
    if (reference.trace.size()!=reference.packets*wav.channels) throw std::runtime_error("Native transform/ADTS count mismatch");
    std::ofstream f(o.output/"run_metadata.json");
    f << std::setprecision(17) << "{\n\"complete\":true,\"window_mode\":\"" << (o.mode<0 ? "DEFAULT" : modes[o.mode])
      << "\",\"sample_rate\":" << wav.sample_rate << ",\"channels\":" << wav.channels
      << ",\"input_bits\":" << wav.bits << ",\"input_format_tag\":" << wav.format
      << ",\"source_samples_per_channel\":" << wav.sample_frames << ",\"clipped_input_samples\":" << wav.clipped_samples
      << ",\"target_bitrate_bps\":64000,\"aot\":2,\"frame_length\":1024,\"bitrate_mode\":0,\"afterburner\":1"
      << ",\"encoder_delay_samples\":" << reference.info.nDelay << ",\"encoder_delay_core_samples\":" << reference.info.nDelayCore
      << ",\"decoder_additional_delay_samples\":" << decoded.additional_delay << ",\"decoder_flush_samples\":" << decoded.flush_samples
      << ",\"decoded_samples_per_channel\":" << decoded.pcm.size()/decoded.channels
      << ",\"adts_frames\":" << decoded.frames << ",\"aac_size_bytes\":" << reference.bytes.size()
      << ",\"decoder_errors\":0,\"decoder_limiter\":0,\"decoder_conceal_method\":0"
      << ",\"warmup_runs\":1,\"trace_enabled_during_timed_runs\":false,\"measured_bitstreams_equal_warmup\":true"
      << ",\"timing_scope\":\"sum of aacEncEncode calls after initialization, including flush; no I/O/trace/decode\""
      << ",\"tns_pns_configuration\":\"native AAC-LC defaults, identical for all modes\""
      << ",\"encoding_time_ms\":[";
    for (std::size_t i=0; i<times.size(); ++i) { if(i) f << ','; f << times[i]; }
    f << "]}\n"; f.close(); if (!f) throw std::runtime_error("Cannot finish metadata");
    std::cout << (o.mode<0 ? "DEFAULT" : modes[o.mode]) << ": " << decoded.frames << " AAC-LC frames, "
              << reference.bytes.size() << " bytes, " << times.size() << " measured runs; native decode OK\n";
    return 0;
  } catch (const std::exception &e) { std::cerr << "Error: " << e.what() << '\n'; return 1; }
}
