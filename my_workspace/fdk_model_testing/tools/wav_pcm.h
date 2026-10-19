#ifndef FDK_TRACE_WAV_PCM_H
#define FDK_TRACE_WAV_PCM_H
#include <cstdint>
#include <filesystem>
#include <vector>
struct TraceWav {
  int sample_rate = 0, channels = 0, bits = 0, format = 0;
  std::uint64_t sample_frames = 0, clipped_samples = 0;
  std::vector<std::int16_t> pcm;
};
TraceWav read_trace_wav(const std::filesystem::path &path);
#endif
