/* Observation-only research hooks for the existing FDK transform.
 * Fixed-size storage, no exceptions and no replacement DSP implementation. */
#include "mdct_debug.h"
#include "FDK_tools_rom.h"
#include <cmath>
#include <cstdio>
#include <cstring>

namespace {
struct Scale { int variable, effective; };
struct Sub {
  int L, offset, input_start, fl, fr, nl, nr, flags;
  const char *left_rom, *right_rom;
  Scale fold, pre, fft, post;
};
struct Frame {
  bool valid;
  int frame, channel, block, shape, subs;
  double pcm_rms;
  const INT_PCM *base;
  INT_PCM pcm[2048];
  FIXP_DBL fold[1024], pre[1024], fft[1024], post[1024], mdct[1024];
  int exponents[1024];
  Sub sub[8];
};
struct State {
  bool configured, active;
  int frame, channels, target_frame, channel, active_sub;
  char directory[4096], error[256];
  FILE *catalog;
  Frame current, best;
};
State g;

void fail(const char *message) {
  if (!g.error[0]) std::snprintf(g.error, sizeof(g.error), "%s", message);
}
const char *block_name(int block) {
  static const char *names[] = {"LONG", "START", "SHORT", "STOP"};
  return block >= 0 && block < 4 ? names[block] : "UNKNOWN";
}
const char *window_name(const FIXP_WTP *window) {
  if (window == SineWindow1024) return "SineWindow1024";
  if (window == SineWindow128) return "SineWindow128";
  if (window == KBDWindow1024) return "KBDWindow1024";
  if (window == KBDWindow128) return "KBDWindow128";
  return "unknown";
}
FILE *open_file(const char *name) {
  char path[4096];
  int n = std::snprintf(path, sizeof(path), "%s/%s", g.directory, name);
  if (n < 0 || n >= (int)sizeof(path)) { fail("Output path too long"); return NULL; }
  FILE *f = std::fopen(path, "w");
  if (!f) fail("Cannot open an MDCT trace output file");
  return f;
}
void close_file(FILE *f) {
  if (!f) return;
  bool bad = std::ferror(f) != 0;
  if (std::fclose(f) != 0 || bad) fail("Cannot finish writing MDCT trace data");
}
template<class T> void scalar_file(const char *name, const T *data, int count) {
  FILE *f = open_file(name);
  if (!f) return;
  for (int i = 0; i < count; ++i) std::fprintf(f, "%d %ld\n", i, (long)data[i]);
  close_file(f);
}
void complex_file(const char *name, const FIXP_DBL *data) {
  FILE *f = open_file(name);
  if (!f) return;
  for (int i = 0; i < 512; ++i)
    std::fprintf(f, "%d %ld %ld\n", i, (long)data[2*i], (long)data[2*i+1]);
  close_file(f);
}
template<class T> void print_stats(const char *name, const T *data, int count) {
  long minimum = (long)data[0], maximum = minimum;
  long double sum = 0, square = 0;
  for (int i = 0; i < count; ++i) {
    long value = (long)data[i];
    if (value < minimum) minimum = value;
    if (value > maximum) maximum = value;
    sum += value; square += (long double)value * value;
  }
  std::printf("%-18s count=%d min=%ld max=%ld mean=%.9g RMS=%.9g\n", name,
               count, minimum, maximum, (double)(sum/count),
               std::sqrt((double)(square/count)));
}
void scale_json(FILE *f, const char *name, Scale s, bool comma) {
  std::fprintf(f, "\"%s\":{\"variable\":%d,\"effective\":%d}%s", name,
                s.variable, s.effective, comma ? "," : "");
}
void metadata() {
  const Frame &b = g.best;
  FILE *f = open_file("stage_metadata.json");
  if (!f) return;
  std::fprintf(f,
    "{\n\"schema_version\":1,\"selected_frame\":%d,\"channel\":%d,"
    "\"selection\":\"%s\",\"block_type\":\"%s\",\"window_shape\":\"%s\","
    "\"pcm_rms\":%.17g,\"pcm_samples\":2048,\"coefficient_count\":1024,"
    "\"complex_count\":512,\"pcm_fraction_bits\":%d,\"data_fraction_bits\":%d,"
    "\"window_coefficient_bits\":%d,\"sine_coefficient_bits\":%d,"
    "\"transform_frames_seen\":%d,\n"
    "\"frame_index_meaning\":\"zero-based native encoder transform frame, including priming/flush\","
    "\"buffer_aliases\":\"psyInputBuffer -> mdctData=pDat; FFT pInput=x=pDat\","
    "\"raw_layout\":\"short subtransforms concatenated, no spectral grouping yet\","
    "\"subtransforms\":[\n",
    b.frame, b.channel, g.target_frame < 0 ? "maximum_pcm_rms" : "explicit",
    block_name(b.block), b.shape == 0 ? "SINE" : "KBD", b.pcm_rms,
    SAMPLE_BITS-1, DFRACT_BITS-1, (int)sizeof(FIXP_WTB)*8,
    (int)sizeof(FIXP_STB)*8, g.frame+1);
  for (int n = 0; n < b.subs; ++n) {
    const Sub &s = b.sub[n];
    std::fprintf(f,
      "{\"index\":%d,\"L\":%d,\"M\":%d,\"scalar_offset\":%d,"
      "\"input_start\":%d,\"input_length\":%d,\"fl\":%d,\"fr\":%d,"
      "\"nl\":%d,\"nr\":%d,\"left_window\":\"%s\",\"right_window\":\"%s\","
      "\"pre_rom\":\"SineWindow%d\",\"fft_rom\":\"SineTable512\","
      "\"post_rom\":\"SineTable1024\",\"sin_step\":%d,\"exponents\":{",
      n, s.L, s.L/2, s.offset, s.input_start, 2*s.L, s.fl, s.fr, s.nl, s.nr,
      s.left_rom, s.right_rom, s.L, s.L == 1024 ? 2 : 16);
    scale_json(f, "window_fold", s.fold, true);
    scale_json(f, "preprocessing", s.pre, true);
    scale_json(f, "fft", s.fft, true);
    scale_json(f, "postprocessing", s.post, false);
    std::fprintf(f, "}}%s\n", n+1 < b.subs ? "," : "");
  }
  std::fprintf(f, "]}\n");
  close_file(f);
}
Sub *active_sub(int length) {
  if (!g.active) return NULL;
  if (g.active_sub < 0 || g.active_sub >= g.current.subs) {
    fail("DCT stage observed without a Window/Fold boundary"); return NULL;
  }
  Sub *s = &g.current.sub[g.active_sub];
  if (s->L != length) { fail("Inconsistent transform length"); return NULL; }
  return s;
}
} // namespace

extern "C" int FDKmdctDebugConfigure(const char *directory, int channels,
                                     int frame, int channel) {
  if (g.catalog) close_file(g.catalog);
  std::memset(&g, 0, sizeof(g));
  g.frame = -1; g.active_sub = -1;
  if (!directory || std::strlen(directory) >= sizeof(g.directory) ||
      channels < 1 || channels > 2 || frame < -1 || channel < 0 || channel >= channels) {
    fail("Trace requires mono/stereo, a valid channel and frame >= 0 or auto");
    return 1;
  }
  std::snprintf(g.directory, sizeof(g.directory), "%s", directory);
  g.channels = channels; g.target_frame = frame; g.channel = channel;
  g.catalog = open_file("frame_index.csv");
  if (!g.catalog) return 1;
  std::fprintf(g.catalog, "frame,channel,block_type,window_shape,pcm_rms\n");
  g.configured = true;
  return 0;
}
extern "C" const char *FDKmdctDebugError(void) { return g.error; }

extern "C" void FDKmdctDebugBegin(const INT_PCM *pcm, int length, int channel,
                                  int block_type, int window_shape) {
  if (!g.configured) return;
  g.active = false;
  if (channel == 0) ++g.frame;
  if (length != 1024 || channel < 0 || channel >= g.channels) {
    fail("Trace supports AAC-LC frame length 1024 only"); return;
  }
  long double square = 0;
  for (int i = 0; i < 2048; ++i) square += (long double)pcm[i] * pcm[i];
  double rms = std::sqrt((double)(square/2048));
  std::fprintf(g.catalog, "%d,%d,%s,%s,%.17g\n", g.frame, channel,
               block_name(block_type), window_shape == 0 ? "SINE" : "KBD", rms);
  if (channel != g.channel) return;
  if (g.target_frame >= 0 && g.target_frame != g.frame) return;
  if (g.target_frame < 0 && g.best.valid && rms <= g.best.pcm_rms) return;
  std::memset(&g.current, 0, sizeof(g.current));
  g.current.frame = g.frame; g.current.channel = channel;
  g.current.block = block_type; g.current.shape = window_shape;
  g.current.pcm_rms = rms; g.current.base = pcm;
  std::memcpy(g.current.pcm, pcm, sizeof(g.current.pcm));
  g.active_sub = -1; g.active = true;
}
extern "C" void FDKmdctDebugFold(const FIXP_DBL *data, int length, int exponent,
                                 int sub, int fl, int fr, int nl, int nr,
                                 const FIXP_WTP *left, const FIXP_WTP *right,
                                 const INT_PCM *sub_pcm) {
  if (!g.active) return;
  if ((length != 128 && length != 1024) || sub < 0 || sub >= 8 ||
      sub*length+length > 1024 || sub != g.current.subs) {
    fail("Invalid or out-of-order Window/Fold event"); return;
  }
  Sub &s = g.current.sub[sub];
  s.L = length; s.offset = sub*length;
  s.input_start = (int)(sub_pcm-g.current.base);
  s.fl = fl; s.fr = fr; s.nl = nl; s.nr = nr;
  s.left_rom = window_name(left); s.right_rom = window_name(right);
  s.fold.variable = s.fold.effective = exponent; s.flags = 1;
  std::memcpy(g.current.fold+s.offset, data, length*sizeof(FIXP_DBL));
  ++g.current.subs; g.active_sub = sub;
}
extern "C" void FDKmdctDebugPre(const FIXP_DBL *data, int length, int exponent) {
  Sub *s = active_sub(length); if (!s) return;
  if (s->flags != 1) fail("Pre-processing event out of order");
  s->pre.variable = exponent; s->pre.effective = exponent+2; s->flags |= 2;
  std::memcpy(g.current.pre+s->offset, data, length*sizeof(FIXP_DBL));
}
extern "C" void FDKmdctDebugFft(const FIXP_DBL *data, int length, int exponent) {
  Sub *s = active_sub(length); if (!s) return;
  if (s->flags != 3) fail("FFT event out of order");
  s->fft.variable = exponent; s->fft.effective = exponent+2; s->flags |= 4;
  std::memcpy(g.current.fft+s->offset, data, length*sizeof(FIXP_DBL));
}
extern "C" void FDKmdctDebugPost(const FIXP_DBL *data, int length, int exponent) {
  Sub *s = active_sub(length); if (!s) return;
  if (s->flags != 7) fail("Post-processing event out of order");
  s->post.variable = s->post.effective = exponent; s->flags |= 8;
  std::memcpy(g.current.post+s->offset, data, length*sizeof(FIXP_DBL));
}
extern "C" void FDKmdctDebugEnd(const FIXP_DBL *data, int length, int exponent) {
  if (!g.active) return;
  g.active = false;
  if (length != 1024 || g.current.subs != (g.current.block == 2 ? 8 : 1)) {
    fail("Incomplete native MDCT frame"); return;
  }
  for (int n = 0; n < g.current.subs; ++n) {
    const Sub &s = g.current.sub[n];
    if (s.flags != 15 || s.post.effective != exponent) {
      fail("Missing stage hook or inconsistent final MDCT exponent"); return;
    }
    for (int i = 0; i < s.L; ++i) g.current.exponents[s.offset+i] = exponent;
  }
  if (std::memcmp(data, g.current.post, 1024*sizeof(FIXP_DBL)) != 0) {
    fail("Post boundary differs from final native MDCT buffer"); return;
  }
  std::memcpy(g.current.mdct, data, sizeof(g.current.mdct));
  g.current.valid = true;
  std::memcpy(&g.best, &g.current, sizeof(g.best));
  g.best.base = NULL;
}
extern "C" int FDKmdctDebugWrite(void) {
  close_file(g.catalog); g.catalog = NULL; g.configured = false;
  if (!g.best.valid) fail("Requested transform frame/channel was not observed");
  if (g.error[0]) return 1;
  scalar_file("00_pcm_input.txt", g.best.pcm, 2048);
  scalar_file("01_window_fold.txt", g.best.fold, 1024);
  complex_file("02_preprocessing.txt", g.best.pre);
  complex_file("03_fft.txt", g.best.fft);
  scalar_file("04_postprocessing.txt", g.best.post, 1024);
  scalar_file("05_mdct_output.txt", g.best.mdct, 1024);
  scalar_file("05_mdct_exponents.txt", g.best.exponents, 1024);
  metadata();
  std::printf("Selected native transform frame %d, channel %d, %s, %d transform(s)\n",
               g.best.frame, g.best.channel, block_name(g.best.block), g.best.subs);
  print_stats("PCM16", g.best.pcm, 2048);
  print_stats("Window/Fold Q31", g.best.fold, 1024);
  print_stats("Pre Re/Im Q31", g.best.pre, 1024);
  print_stats("FFT Re/Im Q31", g.best.fft, 1024);
  print_stats("Post Q31", g.best.post, 1024);
  print_stats("MDCT Q31", g.best.mdct, 1024);
  for (int i = 0; i < g.best.subs; ++i) {
    const Sub &s = g.best.sub[i];
    std::printf("Sub %d: L=%d M=%d; effective e=%d/%d/%d/%d; variable e=%d/%d/%d/%d\n",
      i, s.L, s.L/2, s.fold.effective, s.pre.effective, s.fft.effective,
      s.post.effective, s.fold.variable, s.pre.variable, s.fft.variable,
      s.post.variable);
  }
  return g.error[0] ? 1 : 0;
}
