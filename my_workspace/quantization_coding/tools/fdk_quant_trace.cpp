/* Native AAC-LC QC survey. No replacement DSP or quantizer. */
#include "aacenc_lib.h"
#include "aacdecoder_lib.h"
#include "wav_pcm.h"
#ifdef QUANT_DEBUG
#include "quant_debug_api.h"
#endif
#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs=std::filesystem;
namespace {
struct Options {
  fs::path input="my_workspace/INPUT/data/abc_votay.wav",output="my_workspace/quantization_coding/output/quant";
  int first=0,end=1,channel=0,bitrate=0,rate=0,afterburner=1,bandwidth=0;
  unsigned stages=255;bool noTrace=false,iterations=true,lines=false,overwrite=false,decodeCheck=false;
};
int integer(const std::string &s) {
  std::size_t n;long long value=std::stoll(s,&n);
  if(n!=s.size() || value<0 || value>std::numeric_limits<int>::max())throw std::runtime_error("Invalid nonnegative integer: "+s);
  return (int)value;
}
Options parse(int argc,char **argv) {
  Options o;bool selection=false;
  for(int i=1;i<argc;i++) {
    std::string a=argv[i];
    if(a=="--help" || a=="-h") {
      std::cout<<"fdk_quant_trace --wav WAV --output-dir DIR [--frame N | --frames START:END]\n"
        " [--channel 0|1|all] [--bitrate bps] [--sample-rate Hz] [--afterburner 0|1]\n"
        " [--stages all|form_factor,pe,bit_allocation,threshold,scalefactor,global_gain,quantization,iterations]\n"
        " [--no-iteration-log] [--line-trace] [--no-trace] [--overwrite]\n"
        "Range end is exclusive. Frame index includes native priming/flush.\n";std::exit(0);
    }
    if(a=="--no-trace"){o.noTrace=true;continue;}
    if(a=="--no-iteration-log"){o.iterations=false;continue;}
    if(a=="--line-trace"){o.lines=true;continue;}
    if(a=="--overwrite"){o.overwrite=true;continue;}
    if(a=="--decode-check"){o.decodeCheck=true;continue;}
    if(i+1>=argc)throw std::runtime_error("Missing value for "+a);
    std::string v=argv[++i];
    if(a=="--wav")o.input=v;
    else if(a=="--output-dir")o.output=v;
    else if(a=="--bitrate")o.bitrate=integer(v);
    else if(a=="--sample-rate")o.rate=integer(v);
    else if(a=="--bandwidth")o.bandwidth=integer(v);
    else if(a=="--afterburner"){o.afterburner=integer(v);if(o.afterburner>1)throw std::runtime_error("Afterburner must be 0 or 1");}
    else if(a=="--channel")o.channel=v=="all"?-1:integer(v);
    else if(a=="--frame" || a=="--frames") {
      if(selection)throw std::runtime_error("Choose frame or frames once");selection=true;
      if(a=="--frame"){o.first=integer(v);if(o.first==std::numeric_limits<int>::max())throw std::runtime_error("Frame too large");o.end=o.first+1;}
      else{auto colon=v.find(':');if(colon==std::string::npos)throw std::runtime_error("Expected START:END");o.first=integer(v.substr(0,colon));o.end=integer(v.substr(colon+1));}
      if(o.end<=o.first)throw std::runtime_error("Empty/reversed frame range");
    } else if(a=="--stages") {
      o.stages=0;std::istringstream parts(v);std::string name;
      const char *names[]={"form_factor","pe","bit_allocation","threshold","scalefactor","global_gain","quantization","iterations"};
      while(std::getline(parts,name,',')){
        if(name=="all"){o.stages=255;continue;}bool found=false;
        for(int k=0;k<8;k++)if(name==names[k]){o.stages|=1u<<k;found=true;}
        if(!found)throw std::runtime_error("Unknown stage: "+name);
      }
      if(!o.stages)throw std::runtime_error("Empty stage selection");
    } else throw std::runtime_error("Unknown option: "+a);
  }
  return o;
}
void check(AACENC_ERROR e,const char *operation){if(e!=AACENC_OK){std::ostringstream s;s<<operation<<" failed (FDK 0x"<<std::hex<<(int)e<<')';throw std::runtime_error(s.str());}}
struct Encoder{HANDLE_AACENCODER handle=nullptr;~Encoder(){if(handle)aacEncClose(&handle);}};
#ifdef QUANT_DEBUG
constexpr bool debug=true;
#else
constexpr bool debug=false;
#endif
std::string quote(const std::string &s){std::string r="\"";for(unsigned char c:s){if(c=='"'||c=='\\')r+='\\';if(c<32)throw std::runtime_error("Control character in path");r+=c;}return r+'"';}
int decode_check(const fs::path &path) {
  std::ifstream stream(path,std::ios::binary);
  std::vector<unsigned char> bytes((std::istreambuf_iterator<char>(stream)),std::istreambuf_iterator<char>());
  if(!stream || bytes.empty())throw std::runtime_error("Cannot read AAC for decoder validation");
  struct Decoder { HANDLE_AACDECODER handle; ~Decoder(){if(handle)aacDecoder_Close(handle);} } d{aacDecoder_Open(TT_MP4_ADTS,1)};
  if(!d.handle)throw std::runtime_error("Cannot open native FDK decoder");
  std::vector<INT_PCM> pcm(8192);std::size_t pos=0;int frames=0;
  while(pos<bytes.size()) {
    if(bytes.size()-pos<7 || bytes[pos]!=0xFF || (bytes[pos+1]&0xF6)!=0xF0)throw std::runtime_error("Invalid native ADTS header");
    UINT size=((bytes[pos+3]&3)<<11)|(bytes[pos+4]<<3)|(bytes[pos+5]>>5);
    if(size<7 || size>bytes.size()-pos)throw std::runtime_error("Invalid ADTS frame length");
    UCHAR *buffer=bytes.data()+pos;UINT valid=size;
    if(aacDecoder_Fill(d.handle,&buffer,&size,&valid)!=AAC_DEC_OK || valid)throw std::runtime_error("Native decoder did not accept full ADTS packet");
    AAC_DECODER_ERROR error=aacDecoder_DecodeFrame(d.handle,pcm.data(),(INT)pcm.size(),0);
    if(error!=AAC_DEC_OK){std::ostringstream message;message<<"FDK decoder error 0x"<<std::hex<<(int)error;throw std::runtime_error(message.str());}
    const CStreamInfo *info=aacDecoder_GetStreamInfo(d.handle);
    if(!info || info->frameSize!=1024 || info->numChannels<1 || info->numChannels>2)throw std::runtime_error("Decoded AAC-LC dimensions invalid");
    pos+=size;++frames;
  }
  return frames;
}
void status(const fs::path &directory,bool complete,bool trace,int packets,int decoded=-1){
  std::ofstream f(directory/"run_status.json");
  f<<"{\"complete\":"<<(complete?"true":"false")<<",\"quant_debug\":"<<(debug?"true":"false")<<",\"trace_enabled\":"<<(trace?"true":"false")<<",\"packets\":"<<packets<<",\"decoded_packets\":"<<decoded<<"}\n";
  f.close();if(!f)throw std::runtime_error("Cannot write run status");
}
}
int main(int argc,char **argv) {
  try {
    static_assert(sizeof(INT_PCM)==2,"Runner requires native PCM16 input");
    Options o=parse(argc,argv);TraceWav w=read_trace_wav(o.input);
    if(o.rate && o.rate!=w.sample_rate)throw std::runtime_error("Sample rate must match WAV; no resampling");
    if(o.channel>=w.channels || o.channel>1)throw std::runtime_error("Channel outside WAV mono/stereo range");
    if(fs::exists(o.output) && !fs::is_empty(o.output) && !o.overwrite)throw std::runtime_error("Output directory is not empty; choose a new campaign or --overwrite");
    fs::create_directories(o.output);
    for(const char *name:{"native_trace.jsonl","survey_manifest.json","validation.json"})if(o.overwrite)fs::remove(o.output/name);
    bool trace=debug && !o.noTrace;status(o.output,false,trace,0);
    Encoder e;int bitrate=o.bitrate?o.bitrate:64000*w.channels;
    check(aacEncOpen(&e.handle,0,w.channels),"aacEncOpen");
    check(aacEncoder_SetParam(e.handle,AACENC_AOT,2),"AOT");
    check(aacEncoder_SetParam(e.handle,AACENC_SAMPLERATE,w.sample_rate),"sample rate");
    check(aacEncoder_SetParam(e.handle,AACENC_CHANNELMODE,w.channels==1?MODE_1:MODE_2),"channel mode");
    check(aacEncoder_SetParam(e.handle,AACENC_CHANNELORDER,1),"channel order");
    check(aacEncoder_SetParam(e.handle,AACENC_GRANULE_LENGTH,1024),"granule");
    check(aacEncoder_SetParam(e.handle,AACENC_BITRATE,bitrate),"bitrate");
    check(aacEncoder_SetParam(e.handle,AACENC_TRANSMUX,2),"ADTS");
    check(aacEncoder_SetParam(e.handle,AACENC_AFTERBURNER,o.afterburner),"Afterburner");
    if(o.bandwidth)check(aacEncoder_SetParam(e.handle,AACENC_BANDWIDTH,o.bandwidth),"bandwidth");
    check(aacEncEncode(e.handle,nullptr,nullptr,nullptr,nullptr),"initialize");
    AACENC_InfoStruct info{};check(aacEncInfo(e.handle,&info),"info");
    if(info.frameLength!=1024)throw std::runtime_error("AAC-LC frame length is not 1024");
    std::ofstream metadata(o.output/"input_info.json");
    metadata<<"{\"source\":"<<quote(fs::absolute(o.input).generic_string())<<",\"sample_rate\":"<<w.sample_rate<<",\"channels\":"<<w.channels
      <<",\"sample_frames\":"<<w.sample_frames<<",\"bits_per_sample\":"<<w.bits<<",\"format_tag\":"<<w.format<<",\"converted_bits\":16,\"clipped_samples\":"<<w.clipped_samples
      <<",\"bitrate\":"<<bitrate<<",\"aot\":2,\"frame_length\":1024,\"afterburner\":"<<o.afterburner<<",\"encoder_delay_samples\":"<<info.nDelay<<"}\n";
    metadata.close();if(!metadata)throw std::runtime_error("Cannot write input metadata");
#ifdef QUANT_DEBUG
    if(trace && FDKquantDebugConfigure((o.output/"native_trace.jsonl").generic_string().c_str(),o.first,o.end,o.channel,w.sample_rate,bitrate,o.stages,o.iterations,o.lines))throw std::runtime_error(FDKquantDebugError());
#endif
    std::ofstream aac(o.output/"encoded.aac",std::ios::binary);if(!aac)throw std::runtime_error("Cannot open AAC output");
    std::vector<unsigned char> output(std::max<unsigned>(info.maxOutBufBytes,8192));
    std::size_t pos=0;int flushCalls=0,packets=0;
    for(;;) {
      bool flush=pos==w.pcm.size();int count=flush?0:(int)std::min<std::size_t>(w.pcm.size()-pos,1024*w.channels);
      void *ip=flush?nullptr:(void*)(w.pcm.data()+pos),*op=output.data();
      int iid=IN_AUDIO_DATA,isize=count*sizeof(INT_PCM),iesize=sizeof(INT_PCM),oid=OUT_BITSTREAM_DATA,osize=output.size(),oesize=1;
      AACENC_BufDesc in{},out{};in.numBufs=1;in.bufs=&ip;in.bufferIdentifiers=&iid;in.bufSizes=&isize;in.bufElSizes=&iesize;
      out.numBufs=1;out.bufs=&op;out.bufferIdentifiers=&oid;out.bufSizes=&osize;out.bufElSizes=&oesize;
      AACENC_InArgs ia{};AACENC_OutArgs oa{};ia.numInSamples=flush?-1:count;
      AACENC_ERROR result=aacEncEncode(e.handle,&in,&out,&ia,&oa);if(result==AACENC_ENCODE_EOF)break;check(result,"encode");
      if(oa.numOutBytes<0 || oa.numOutBytes>osize || oa.numInSamples<0 || oa.numInSamples>count)throw std::runtime_error("Invalid FDK buffer accounting");
      if(oa.numOutBytes){aac.write((char*)output.data(),oa.numOutBytes);++packets;}pos+=oa.numInSamples;
      if(!flush && !oa.numInSamples && !oa.numOutBytes)throw std::runtime_error("Encoder made no progress");
      if(flush && ++flushCalls>64)throw std::runtime_error("Flush did not terminate");
    }
    aac.close();if(!aac)throw std::runtime_error("Cannot finish AAC output");
#ifdef QUANT_DEBUG
    if(trace && FDKquantDebugFinish())throw std::runtime_error(FDKquantDebugError());
#endif
    int decoded=o.decodeCheck?decode_check(o.output/"encoded.aac"):-1;
    if(o.decodeCheck && decoded!=packets)throw std::runtime_error("Encoded/decoded packet count mismatch");
    status(o.output,true,trace,packets,decoded);std::cout<<"Encoded "<<packets<<" native ADTS packets; delay="<<info.nDelay<<" samples; decoded="<<decoded<<"\n";return 0;
  } catch(const std::exception &e){std::cerr<<"Error: "<<e.what()<<'\n';return 1;}
}
