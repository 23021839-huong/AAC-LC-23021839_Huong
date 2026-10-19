// AAC-LC encoder runner. No local MDCT, FFT, windowing or block-switching code.
#include "aacenc_lib.h"
#ifdef MDCT_DEBUG
#include "mdct_debug.h"
#endif
#include "wav_pcm.h"
#include <algorithm>
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
struct Options {
  fs::path input = "my_workspace/INPUT/data/abc_votay.wav", output = "my_workspace/window_mdct/output";
  int frame = -1, channel = 0, bitrate = 0;
};
int integer(const std::string &s) {
  std::size_t n = 0; long long v = std::stoll(s,&n);
  if (n != s.size() || v < 0 || v > std::numeric_limits<int>::max())
    throw std::runtime_error("Expected a nonnegative integer: " + s);
  return (int)v;
}
Options options(int argc, char **argv) {
  Options o;
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    if (a == "--help" || a == "-h") {
      std::cout << "Usage: fdk_mdct_trace [--input my_workspace/INPUT/data/abc_votay.wav] [--output-dir output]\n"
                   "       [--frame auto|N] [--channel N] [--bitrate bits_per_second]\n"
                   "N is a zero-based native encoder transform frame, including priming/flush.\n"
                   "auto chooses the earliest maximum-RMS native PCM snapshot.\n";
      std::exit(0);
    }
    if (i+1 >= argc) throw std::runtime_error("Missing value for " + a);
    std::string v = argv[++i];
    if (a == "--input") o.input = v;
    else if (a == "--output-dir") o.output = v;
    else if (a == "--frame") o.frame = v == "auto" ? -1 : integer(v);
    else if (a == "--channel") o.channel = integer(v);
    else if (a == "--bitrate") o.bitrate = integer(v);
    else throw std::runtime_error("Unknown option: " + a);
  }
  return o;
}
std::string quote(const std::string &s) {
  std::ostringstream out; out << '"';
  for (unsigned char c : s) {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << (int)c;
    else out << c;
  }
  out << '"'; return out.str();
}
void check(AACENC_ERROR e, const char *operation) {
  if (e != AACENC_OK) {
    std::ostringstream s; s << operation << " failed (FDK error 0x" << std::hex << (int)e << ')';
    throw std::runtime_error(s.str());
  }
}
struct Encoder {
  HANDLE_AACENCODER handle = nullptr;
  ~Encoder() { if (handle) aacEncClose(&handle); }
};
#ifdef MDCT_DEBUG
constexpr bool trace_enabled = true;
#else
constexpr bool trace_enabled = false;
#endif
void write_run_status(const fs::path &directory, bool complete) {
  std::ofstream f(directory/"run_status.json");
  f << "{\"complete\":" << (complete ? "true" : "false")
    << ",\"mdct_debug\":" << (trace_enabled ? "true" : "false") << "}\n";
  f.close();
  if (!f) throw std::runtime_error("Cannot write run_status.json");
}
}
int main(int argc, char **argv) {
  try {
    static_assert(sizeof(INT_PCM) == 2, "Runner converts to FDK PCM16");
    Options o = options(argc,argv);
    TraceWav w = read_trace_wav(o.input);
    if (o.channel >= w.channels) throw std::runtime_error("Channel index outside WAV channels");
    std::cout << "WAV: " << w.sample_rate << " Hz, " << w.channels << " channel(s), "
              << w.bits << " bits, format " << w.format << '\n'
              << "Sample frames: " << w.sample_frames << ", scalar samples: " << w.pcm.size()
              << ", duration: " << (double)w.sample_frames/w.sample_rate << " s\n"
              << "FDK input: PCM16, no resampling/peak normalization; clipped samples: "
              << w.clipped_samples << '\n';
    Encoder e;
    check(aacEncOpen(&e.handle,0,w.channels),"aacEncOpen");
    check(aacEncoder_SetParam(e.handle,AACENC_AOT,2),"AAC-LC AOT");
    check(aacEncoder_SetParam(e.handle,AACENC_SAMPLERATE,w.sample_rate),"sample rate");
    check(aacEncoder_SetParam(e.handle,AACENC_CHANNELMODE,w.channels == 1 ? MODE_1 : MODE_2),"channel mode");
    check(aacEncoder_SetParam(e.handle,AACENC_CHANNELORDER,1),"WAV channel order");
    check(aacEncoder_SetParam(e.handle,AACENC_GRANULE_LENGTH,1024),"frame length");
    check(aacEncoder_SetParam(e.handle,AACENC_BITRATE,o.bitrate ? o.bitrate : 64000*w.channels),"bitrate");
    check(aacEncoder_SetParam(e.handle,AACENC_TRANSMUX,2),"ADTS");
    check(aacEncoder_SetParam(e.handle,AACENC_AFTERBURNER,1),"afterburner");
    check(aacEncEncode(e.handle,nullptr,nullptr,nullptr,nullptr),"encoder initialization");
    AACENC_InfoStruct info{}; check(aacEncInfo(e.handle,&info),"aacEncInfo");
    if (info.frameLength != 1024) throw std::runtime_error("Expected AAC-LC frame length 1024");
    fs::create_directories(o.output);
    write_run_status(o.output,false);
    std::ofstream input_info(o.output/"input_info.json");
    input_info << "{\n\"source\":" << quote(fs::absolute(o.input).generic_string())
       << ",\"sample_rate\":" << w.sample_rate << ",\"channels\":" << w.channels
       << ",\"bits_per_sample\":" << w.bits << ",\"format_tag\":" << w.format
       << ",\"sample_frames\":" << w.sample_frames << ",\"scalar_samples\":" << w.pcm.size()
       << ",\"converted_bits\":16,\"clipped_samples\":" << w.clipped_samples
       << ",\"encoder_frame_length\":1024,\"encoder_delay_samples\":" << info.nDelay
       << ",\"conversion\":\"PCM: signed top 16 bits; float: floor(x*32768), clip at PCM16 range; no peak normalization/resampling\"\n}\n";
    input_info.close();
    if (!input_info) throw std::runtime_error("Cannot write input_info.json");
#ifdef MDCT_DEBUG
    if (FDKmdctDebugConfigure(o.output.generic_string().c_str(),w.channels,o.frame,o.channel))
      throw std::runtime_error(FDKmdctDebugError());
#else
    std::cout << "MDCT_DEBUG=OFF: normal encoder only, no stage dumps.\n";
#endif
    std::ofstream aac(o.output/"encoded.aac",std::ios::binary);
    if (!aac) throw std::runtime_error("Cannot write encoded.aac");
    std::vector<unsigned char> output(std::max<unsigned>(info.maxOutBufBytes,8192));
    std::size_t pos = 0; int flush_calls = 0, packets = 0;
    for (;;) {
      const bool flush = pos == w.pcm.size();
      int count = flush ? 0 : (int)std::min<std::size_t>(w.pcm.size()-pos,1024*w.channels);
      void *ip = flush ? nullptr : static_cast<void*>(w.pcm.data()+pos);
      void *op = output.data();
      int iid = IN_AUDIO_DATA, isize = count*(int)sizeof(INT_PCM), iesize = sizeof(INT_PCM);
      int oid = OUT_BITSTREAM_DATA, osize = (int)output.size(), oesize = 1;
      AACENC_BufDesc in{}, out{};
      in.numBufs=1; in.bufs=&ip; in.bufferIdentifiers=&iid; in.bufSizes=&isize; in.bufElSizes=&iesize;
      out.numBufs=1; out.bufs=&op; out.bufferIdentifiers=&oid; out.bufSizes=&osize; out.bufElSizes=&oesize;
      AACENC_InArgs ia{}; AACENC_OutArgs oa{}; ia.numInSamples=flush ? -1 : count;
      AACENC_ERROR result = aacEncEncode(e.handle,&in,&out,&ia,&oa);
      if (result == AACENC_ENCODE_EOF) break;
      check(result,"aacEncEncode");
      if (oa.numOutBytes < 0 || oa.numOutBytes > osize || oa.numInSamples < 0 || oa.numInSamples > count)
        throw std::runtime_error("Invalid encoder buffer accounting");
      if (oa.numOutBytes) { aac.write((char*)output.data(),oa.numOutBytes); ++packets; }
      pos += oa.numInSamples;
      if (!flush && !oa.numInSamples && !oa.numOutBytes) throw std::runtime_error("Encoder made no progress");
      if (flush && ++flush_calls > 64) throw std::runtime_error("Encoder flush did not terminate");
    }
    aac.close();
    if (!aac) throw std::runtime_error("Cannot finish encoded.aac");
    std::cout << "Encoded " << packets << " ADTS packets, FDK delay=" << info.nDelay << " samples\n";
#ifdef MDCT_DEBUG
    if (FDKmdctDebugWrite()) throw std::runtime_error(FDKmdctDebugError());
#endif
    write_run_status(o.output,true);
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "Error: " << e.what() << '\n'; return 1;
  }
}
