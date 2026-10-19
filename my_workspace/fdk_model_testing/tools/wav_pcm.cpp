// WAV front end only. All filterbank/MDCT/FFT arithmetic remains inside FDK.
#include "wav_pcm.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <string>

namespace {
std::uint64_t le(const std::vector<unsigned char> &b, std::size_t p, int n) {
  if (p > b.size() || (std::size_t)n > b.size()-p) throw std::runtime_error("Truncated WAV field");
  std::uint64_t v = 0;
  for (int i = 0; i < n; ++i) v |= (std::uint64_t)b[p+i] << (8*i);
  return v;
}
bool tag(const std::vector<unsigned char> &b, std::size_t p, const char *s) {
  return p <= b.size() && b.size()-p >= 4 && std::memcmp(b.data()+p, s, 4) == 0;
}
}
TraceWav read_trace_wav(const std::filesystem::path &path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("Cannot open WAV: " + path.string());
  std::vector<unsigned char> b((std::istreambuf_iterator<char>(input)), {});
  if (input.bad()) throw std::runtime_error("Cannot read WAV");
  if (b.size() < 12 || !tag(b, 0, "RIFF") || !tag(b, 8, "WAVE"))
    throw std::runtime_error("Expected a RIFF/WAVE file (RF64/RIFX are not supported)");
  std::uint64_t end64 = le(b,4,4)+8;
  if (end64 > b.size()) throw std::runtime_error("Truncated WAV RIFF payload");
  std::size_t end = (std::size_t)end64, data = 0, data_size = 0;
  int align = 0;
  bool got_fmt = false, got_data = false;
  TraceWav w;
  for (std::size_t p = 12; p < end;) {
    if (end-p < 8) throw std::runtime_error("Truncated WAV chunk header");
    std::uint64_t n = le(b,p+4,4);
    std::size_t body = p+8;
    if (n > end-body) throw std::runtime_error("Truncated WAV chunk payload");
    if (tag(b,p,"fmt ") && !got_fmt) {
      if (n < 16) throw std::runtime_error("Invalid WAV fmt chunk");
      w.format = (int)le(b,body,2); w.channels = (int)le(b,body+2,2);
      w.sample_rate = (int)le(b,body+4,4);
      align = (int)le(b,body+12,2); w.bits = (int)le(b,body+14,2);
      if (w.format == 0xfffe) {
        static const unsigned char suffix[14] = {0,0,0,0,0x10,0,0x80,0,0,0xaa,0,0x38,0x9b,0x71};
        if (n < 40 || le(b,body+16,2) < 22 ||
            std::memcmp(b.data()+body+26,suffix,14) != 0)
          throw std::runtime_error("Unsupported WAV extensible GUID");
        w.format = (int)le(b,body+24,2);
        int valid = (int)le(b,body+18,2);
        if (valid && valid > w.bits) throw std::runtime_error("Invalid WAV valid bits");
      }
      got_fmt = true;
    } else if (tag(b,p,"data") && !got_data) {
      data = body; data_size = (std::size_t)n; got_data = true;
    }
    p = body+(std::size_t)n+(n&1);
    if (p > end) throw std::runtime_error("Truncated WAV chunk padding");
  }
  if (!got_fmt || !got_data) throw std::runtime_error("Missing WAV fmt or data chunk");
  if (w.channels < 1 || w.channels > 2) throw std::runtime_error("Runner supports mono/stereo WAV only");
  if (w.sample_rate <= 0) throw std::runtime_error("Invalid WAV sample rate");
  if (!((w.format == 1 && (w.bits == 8 || w.bits == 16 || w.bits == 24 || w.bits == 32)) ||
        (w.format == 3 && (w.bits == 32 || w.bits == 64))))
    throw std::runtime_error("WAV must be PCM8/16/24/32 or IEEE float32/64");
  const int bytes = w.bits/8;
  if (align != bytes*w.channels || data_size % align != 0)
    throw std::runtime_error("Invalid WAV block alignment");
  w.sample_frames = data_size/align;
  if (!w.sample_frames) throw std::runtime_error("WAV contains no samples");
  w.pcm.reserve(data_size/bytes);
  for (std::size_t p = data; p < data+data_size; p += bytes) {
    std::int64_t converted = 0;
    if (w.format == 1) {
      std::uint64_t u = le(b,p,bytes);
      if (w.bits == 8) converted = ((int)u-128)*256;
      else {
        std::int64_t s = (std::int64_t)u;
        if (u & (std::uint64_t(1) << (w.bits-1))) s -= std::int64_t(1) << w.bits;
        const std::int64_t divisor = std::int64_t(1) << (w.bits-16);
        converted = s >= 0 ? s/divisor : -((-s+divisor-1)/divisor);
      }
    } else {
      double value;
      if (w.bits == 32) {
        std::uint32_t u = (std::uint32_t)le(b,p,4); float v;
        std::memcpy(&v,&u,4); value = v;
      } else {
        std::uint64_t u = le(b,p,8); std::memcpy(&value,&u,8);
      }
      if (!std::isfinite(value)) throw std::runtime_error("WAV contains non-finite float samples");
      if (value < -1 || value > 32767.0/32768) ++w.clipped_samples;
      value = std::max(-1.0, std::min(32767.0/32768, value));
      converted = (std::int64_t)std::floor(value*32768);
    }
    w.pcm.push_back((std::int16_t)converted);
  }
  return w;
}
