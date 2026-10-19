/* -----------------------------------------------------------------------------
Third-Party Modified Version of the Fraunhofer FDK AAC Codec Library.
Encoder profiling instrumentation added in 2026.
----------------------------------------------------------------------------- */

#include "aacenc_profile.h"

#if defined(FDK_ENABLE_ENCODER_PROFILING)

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

#if defined(__linux__)
#include <time.h>
#endif

namespace {

struct ProfileBlockInfo {
  const char *scope;
  const char *name;
};

struct ProfileStat {
  uint64_t wallNanoseconds;
  uint64_t cpuNanoseconds;
  uint64_t calls;
  uint64_t minimumWallNanoseconds;
  uint64_t maximumWallNanoseconds;
  uint64_t minimumCpuNanoseconds;
  uint64_t maximumCpuNanoseconds;
};

struct BandTrialStat {
  uint64_t trials;
  uint64_t lineEvaluations;
};

static const int kMaximumProfileChannels = 8;
static const int kMaximumProfileBands = 60;

static const ProfileBlockInfo kProfileBlockInfo[FDK_ENC_PROFILE_BLOCK_COUNT] = {
    {"root", "frame_total"},
    {"parent", "psy_total"},
    {"detail", "block_switching"},
    {"detail", "window_mdct"},
    {"detail", "band_energy_scaling"},
    {"detail", "tonality"},
    {"detail", "tns"},
    {"detail", "threshold_spreading"},
    {"detail", "psy_tools"},
    {"parent", "qc_prepare"},
    {"parent", "qc_total"},
    {"detail", "adjust_thresholds"},
    {"detail", "scale_factor_estimation"},
    {"detail", "improve_scf"},
    {"detail", "assimilate_single_scf"},
    {"detail", "assimilate_multiple_scf"},
    {"detail", "assimilate_multiple_scf2"},
    {"detail", "calc_sfb_dist"},
    {"detail", "calc_sfb_quant_energy_dist"},
    {"detail", "rate_control"},
    {"detail", "quantize_and_max_sfb"},
    {"detail", "huffman_bit_count"},
    {"detail", "section_merge"},
    {"detail", "crash_recovery"},
    {"parent", "qc_finalize"},
    {"parent", "bitstream_write"}};

static const char *kProfileCounterNames[FDK_ENC_PROFILE_COUNTER_COUNT] = {
    "qmax_scans",
    "qmax_lines",
    "distortion_trials",
    "distortion_trial_lines",
    "quant_energy_calls",
    "quant_energy_lines",
    "gain_retries",
    "section_merge_searches",
    "section_merge_operations",
    "recovery_calls",
    "output_bytes",
    "window_long",
    "window_start",
    "window_short",
    "window_stop"};

static ProfileStat profileAggregate[FDK_ENC_PROFILE_BLOCK_COUNT];
static ProfileStat profileFrame[FDK_ENC_PROFILE_BLOCK_COUNT];
static uint64_t profileCounters[FDK_ENC_PROFILE_COUNTER_COUNT];
static BandTrialStat profileBandTrials[kMaximumProfileChannels]
                                             [kMaximumProfileBands];
static bool profileBandActive[kMaximumProfileChannels][kMaximumProfileBands];
static int profileEnabled = -1;
static bool profileDumped = false;
static bool profileFrameActive = false;
static uint64_t profileFrameIndex = 0;
static int profileChannel = -1;
static FILE *profileFrameOutput = NULL;
static FILE *profileBandOutput = NULL;

static const char *nonemptyEnvironment(const char *name) {
  const char *value = std::getenv(name);
  return (value != NULL && value[0] != '\0') ? value : NULL;
}

static bool isProfileEnabled(void) {
  if (profileEnabled < 0) {
    profileEnabled =
        (nonemptyEnvironment("FDK_PROFILE_CSV") != NULL ||
         nonemptyEnvironment("FDK_PROFILE_FRAMES_CSV") != NULL ||
         nonemptyEnvironment("FDK_PROFILE_BANDS_CSV") != NULL)
            ? 1
            : 0;
  }
  return profileEnabled != 0;
}

static uint64_t wallNowNanoseconds(void) {
#if defined(__linux__)
  struct timespec currentTime;
#if defined(CLOCK_MONOTONIC_RAW)
  const clockid_t clockId = CLOCK_MONOTONIC_RAW;
#else
  const clockid_t clockId = CLOCK_MONOTONIC;
#endif
  if (clock_gettime(clockId, &currentTime) != 0) return 0;
  return static_cast<uint64_t>(currentTime.tv_sec) * 1000000000ULL +
         static_cast<uint64_t>(currentTime.tv_nsec);
#else
  return static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch())
          .count());
#endif
}

static uint64_t cpuNowNanoseconds(void) {
#if defined(__linux__)
  struct timespec currentTime;
  if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &currentTime) != 0) return 0;
  return static_cast<uint64_t>(currentTime.tv_sec) * 1000000000ULL +
         static_cast<uint64_t>(currentTime.tv_nsec);
#else
  const std::clock_t currentTime = std::clock();
  if (currentTime == static_cast<std::clock_t>(-1)) return 0;
  return static_cast<uint64_t>(currentTime) * 1000000000ULL /
         static_cast<uint64_t>(CLOCKS_PER_SEC);
#endif
}

static void addStat(ProfileStat *stat, uint64_t wallNanoseconds,
                    uint64_t cpuNanoseconds) {
  stat->wallNanoseconds += wallNanoseconds;
  stat->cpuNanoseconds += cpuNanoseconds;
  stat->calls++;
  if (stat->calls == 1 || wallNanoseconds < stat->minimumWallNanoseconds) {
    stat->minimumWallNanoseconds = wallNanoseconds;
  }
  if (wallNanoseconds > stat->maximumWallNanoseconds) {
    stat->maximumWallNanoseconds = wallNanoseconds;
  }
  if (stat->calls == 1 || cpuNanoseconds < stat->minimumCpuNanoseconds) {
    stat->minimumCpuNanoseconds = cpuNanoseconds;
  }
  if (cpuNanoseconds > stat->maximumCpuNanoseconds) {
    stat->maximumCpuNanoseconds = cpuNanoseconds;
  }
}

static FILE *openCsv(const char *environmentName, const char *header) {
  const char *path = nonemptyEnvironment(environmentName);
  if (path == NULL) return NULL;
  FILE *output = std::fopen(path, "w");
  if (output == NULL) {
    std::fprintf(stderr, "FDK profiling: cannot open %s output: %s\n",
                 environmentName, path);
    return NULL;
  }
  std::fputs(header, output);
  std::fflush(output);
  return output;
}

static void writeCurrentFrame(void) {
  if (profileFrameOutput == NULL) {
    profileFrameOutput = openCsv(
        "FDK_PROFILE_FRAMES_CSV",
        "frame,kind,scope,name,calls,wall_ns,cpu_ns,value\n");
  }
  if (profileFrameOutput != NULL) {
    for (int block = 0; block < FDK_ENC_PROFILE_BLOCK_COUNT; ++block) {
      const ProfileStat &stat = profileFrame[block];
      std::fprintf(profileFrameOutput,
                   "%llu,timer,%s,%s,%llu,%llu,%llu,0\n",
                   static_cast<unsigned long long>(profileFrameIndex),
                   kProfileBlockInfo[block].scope,
                   kProfileBlockInfo[block].name,
                   static_cast<unsigned long long>(stat.calls),
                   static_cast<unsigned long long>(stat.wallNanoseconds),
                   static_cast<unsigned long long>(stat.cpuNanoseconds));
    }
    for (int counter = 0; counter < FDK_ENC_PROFILE_COUNTER_COUNT; ++counter) {
      std::fprintf(profileFrameOutput,
                   "%llu,counter,workload,%s,0,0,0,%llu\n",
                   static_cast<unsigned long long>(profileFrameIndex),
                   kProfileCounterNames[counter],
                   static_cast<unsigned long long>(profileCounters[counter]));
    }
    std::fflush(profileFrameOutput);
  }

  if (profileBandOutput == NULL) {
    profileBandOutput = openCsv(
        "FDK_PROFILE_BANDS_CSV",
        "frame,channel,sfb,trials,total_line_evaluations\n");
  }
  if (profileBandOutput != NULL) {
    for (int channel = 0; channel < kMaximumProfileChannels; ++channel) {
      for (int sfb = 0; sfb < kMaximumProfileBands; ++sfb) {
        const BandTrialStat &stat = profileBandTrials[channel][sfb];
        if (!profileBandActive[channel][sfb]) continue;
        std::fprintf(profileBandOutput, "%llu,%d,%d,%llu,%llu\n",
                     static_cast<unsigned long long>(profileFrameIndex), channel,
                     sfb, static_cast<unsigned long long>(stat.trials),
                     static_cast<unsigned long long>(stat.lineEvaluations));
      }
    }
    std::fflush(profileBandOutput);
  }
}

}  // namespace

FDK_ENCODER_PROFILE_STAMP FDKaacEnc_ProfileNow(void) {
  FDK_ENCODER_PROFILE_STAMP stamp = {0, 0};
  if (!isProfileEnabled()) return stamp;
  stamp.wallNanoseconds = wallNowNanoseconds();
  stamp.cpuNanoseconds = cpuNowNanoseconds();
  return stamp;
}

void FDKaacEnc_ProfileAdd(FDK_ENCODER_PROFILE_BLOCK block,
                          FDK_ENCODER_PROFILE_STAMP start) {
  if ((start.wallNanoseconds == 0 && start.cpuNanoseconds == 0) || block < 0 ||
      block >= FDK_ENC_PROFILE_BLOCK_COUNT) {
    return;
  }

  const FDK_ENCODER_PROFILE_STAMP end = FDKaacEnc_ProfileNow();
  const uint64_t wallNanoseconds =
      (end.wallNanoseconds >= start.wallNanoseconds)
          ? end.wallNanoseconds - start.wallNanoseconds
          : 0;
  const uint64_t cpuNanoseconds =
      (end.cpuNanoseconds >= start.cpuNanoseconds)
          ? end.cpuNanoseconds - start.cpuNanoseconds
          : 0;
  addStat(&profileAggregate[block], wallNanoseconds, cpuNanoseconds);
  if (profileFrameActive) {
    addStat(&profileFrame[block], wallNanoseconds, cpuNanoseconds);
  }
}

void FDKaacEnc_ProfileCounterAdd(FDK_ENCODER_PROFILE_COUNTER counter,
                                 uint64_t value) {
  if (!isProfileEnabled() || !profileFrameActive || counter < 0 ||
      counter >= FDK_ENC_PROFILE_COUNTER_COUNT) {
    return;
  }
  profileCounters[counter] += value;
}

void FDKaacEnc_ProfileDistortionTrial(int sfb, int lineCount) {
  if (!isProfileEnabled() || !profileFrameActive) return;
  FDKaacEnc_ProfileCounterAdd(FDK_ENC_PROFILE_COUNTER_DISTORTION_TRIALS, 1);
  if (lineCount > 0) {
    FDKaacEnc_ProfileCounterAdd(FDK_ENC_PROFILE_COUNTER_DISTORTION_TRIAL_LINES,
                                static_cast<uint64_t>(lineCount));
  }
  if (profileChannel < 0 || profileChannel >= kMaximumProfileChannels ||
      sfb < 0 || sfb >= kMaximumProfileBands) {
    return;
  }
  BandTrialStat &stat = profileBandTrials[profileChannel][sfb];
  stat.trials++;
  if (lineCount > 0) stat.lineEvaluations += static_cast<uint64_t>(lineCount);
}

void FDKaacEnc_ProfileNextChannel(int sfbCnt, int maxSfbPerGroup,
                                  int sfbPerGroup) {
  if (!isProfileEnabled() || !profileFrameActive) return;
  ++profileChannel;
  if (profileChannel < 0 || profileChannel >= kMaximumProfileChannels ||
      sfbCnt <= 0 || maxSfbPerGroup <= 0 || sfbPerGroup <= 0) {
    return;
  }
  for (int groupOffset = 0; groupOffset < sfbCnt;
       groupOffset += sfbPerGroup) {
    for (int band = 0; band < maxSfbPerGroup; ++band) {
      const int sfb = groupOffset + band;
      if (sfb >= 0 && sfb < kMaximumProfileBands && sfb < sfbCnt) {
        profileBandActive[profileChannel][sfb] = true;
      }
    }
  }
}

void FDKaacEnc_ProfileFrameBegin(void) {
  if (!isProfileEnabled()) return;
  std::memset(profileFrame, 0, sizeof(profileFrame));
  std::memset(profileCounters, 0, sizeof(profileCounters));
  std::memset(profileBandTrials, 0, sizeof(profileBandTrials));
  std::memset(profileBandActive, 0, sizeof(profileBandActive));
  profileChannel = -1;
  profileFrameActive = true;
}

void FDKaacEnc_ProfileFrameEnd(void) {
  if (!isProfileEnabled() || !profileFrameActive) return;
  writeCurrentFrame();
  profileFrameActive = false;
  ++profileFrameIndex;
}

void FDKaacEnc_ProfileDump(void) {
  if (!isProfileEnabled() || profileDumped) return;

  const char *path = nonemptyEnvironment("FDK_PROFILE_CSV");
  if (path != NULL &&
      profileAggregate[FDK_ENC_PROFILE_FRAME_TOTAL].calls != 0) {
    FILE *output = std::fopen(path, "w");
    if (output == NULL) {
      std::fprintf(stderr, "FDK profiling: cannot open CSV output: %s\n", path);
    } else {
      const double frameCpuNanoseconds = static_cast<double>(
          profileAggregate[FDK_ENC_PROFILE_FRAME_TOTAL].cpuNanoseconds);
      const double frameCount = static_cast<double>(
          profileAggregate[FDK_ENC_PROFILE_FRAME_TOTAL].calls);

      std::fprintf(
          output,
          "clock_source,wall_clock_source,scope,block,total_us,"
          "percent_of_frame,calls,calls_per_frame,average_us,minimum_us,"
          "maximum_us,wall_total_us,wall_average_us,wall_minimum_us,"
          "wall_maximum_us\n");

      for (int block = 0; block < FDK_ENC_PROFILE_BLOCK_COUNT; ++block) {
        const ProfileStat &stat = profileAggregate[block];
        if (stat.calls == 0) continue;
        const double totalCpuMicroseconds = stat.cpuNanoseconds / 1000.0;
        const double totalWallMicroseconds = stat.wallNanoseconds / 1000.0;
        const double percentOfFrame =
            frameCpuNanoseconds > 0.0
                ? 100.0 * stat.cpuNanoseconds / frameCpuNanoseconds
                : 0.0;
        const double callsPerFrame = stat.calls / frameCount;
        std::fprintf(
            output,
            "thread_cpu_time,monotonic_wall_clock,%s,%s,%.3f,%.6f,%llu,"
            "%.6f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f\n",
            kProfileBlockInfo[block].scope, kProfileBlockInfo[block].name,
            totalCpuMicroseconds, percentOfFrame,
            static_cast<unsigned long long>(stat.calls), callsPerFrame,
            totalCpuMicroseconds / static_cast<double>(stat.calls),
            stat.minimumCpuNanoseconds / 1000.0,
            stat.maximumCpuNanoseconds / 1000.0, totalWallMicroseconds,
            totalWallMicroseconds / static_cast<double>(stat.calls),
            stat.minimumWallNanoseconds / 1000.0,
            stat.maximumWallNanoseconds / 1000.0);
      }
      std::fclose(output);
      std::fprintf(stderr, "FDK profiling: wrote %s\n", path);
    }
  }

  if (profileFrameOutput != NULL) {
    std::fclose(profileFrameOutput);
    profileFrameOutput = NULL;
  }
  if (profileBandOutput != NULL) {
    std::fclose(profileBandOutput);
    profileBandOutput = NULL;
  }
  profileDumped = true;
}

#endif /* FDK_ENABLE_ENCODER_PROFILING */
