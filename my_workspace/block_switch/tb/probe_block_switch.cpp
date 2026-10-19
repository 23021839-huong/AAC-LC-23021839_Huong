/* Standalone AAC-LC probe of the real FDK block switching implementation.
 * Build/run instructions: ../docs/khao_sat_fdk_block_switch.md
 */
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <climits>
#include <cerrno>

#include "block_switch.h"
#include "wavreader.h"

static_assert(SAMPLE_BITS == 16, "This probe expects PCM16 input");
static const int FRAME_LEN = 1024;

static const char *sequenceName(int value) {
  static const char *names[] = {"LONG", "START", "SHORT", "STOP", "LOWOV", "WRONG"};
  return value >= 0 && value < 6 ? names[value] : "UNKNOWN";
}

static const char *shapeName(int value) {
  static const char *names[] = {"SINE", "KBD", "LOL"};
  return value >= 0 && value < 3 ? names[value] : "UNKNOWN";
}

/* EDIT HERE to supply your own samples. State is kept across calls/frames.
 * Default: silence, with one impulse at frame 3, sample 512 (sub-window 4).
 */
static void makeInput(INT_PCM *pcm, int frame, const char *signal) {
  for (int n = 0; n < FRAME_LEN; ++n) {
    const double sample = (double)frame * FRAME_LEN + n;
    pcm[n] = !std::strcmp(signal, "sine")
                 ? (INT_PCM)(8000.0 * std::sin(2.0 * 3.141592653589793 *
                                              1000.0 * sample / 48000.0))
                 : 0;
  }
  if (!std::strcmp(signal, "impulse") && frame == 3) pcm[512] = 30000;
}

static void csvHeader(FILE *csv) {
  std::fprintf(csv, "frame,validSamples,phase,attack,attackIndex,lastattack,"
                    "lastAttackIndex,lastWindowSequence,seq,windowShape,shape,"
                    "lastWindowShape,nBlockSwitchWindows,allowShortFrames,"
                    "allowLookAhead,noOfGroups,groupLen0,groupLen1,groupLen2,"
                    "groupLen3,maxWindowNrg,accWindowNrg,iirState0,iirState1");
  for (int filtered = 0; filtered < 2; ++filtered)
    for (int history = 0; history < 2; ++history)
      for (int w = 0; w < BLOCK_SWITCH_WINDOWS; ++w)
        std::fprintf(csv, ",%s_%s%d", filtered ? "windowNrgF" : "windowNrg",
                     history == THIS_WINDOW ? "current" : "previous", w);
  std::fprintf(csv, "\n");
}

static void csvRow(FILE *csv, int frame, int valid, const char *phase,
                   const BLOCK_SWITCHING_CONTROL &s) {
  std::fprintf(csv, "%d,%d,%s,%d,%d,%d,%d,%d,%s,%d,%s,%d,%u,%d,%d,%d",
               frame, valid, phase, s.attack, s.attackIndex, s.lastattack,
               s.lastAttackIndex, s.lastWindowSequence,
               sequenceName(s.lastWindowSequence), s.windowShape,
               shapeName(s.windowShape), s.lastWindowShape,
               s.nBlockSwitchWindows, s.allowShortFrames, s.allowLookAhead,
               s.noOfGroups);
  for (int i = 0; i < MAX_NO_OF_GROUPS; ++i)
    std::fprintf(csv, ",%d", s.groupLen[i]);
  std::fprintf(csv, ",%ld,%ld,%ld,%ld", (long)s.maxWindowNrg,
               (long)s.accWindowNrg, (long)s.iirStates[0], (long)s.iirStates[1]);
  for (int filtered = 0; filtered < 2; ++filtered)
    for (int history = 0; history < 2; ++history)
      for (int w = 0; w < BLOCK_SWITCH_WINDOWS; ++w)
        std::fprintf(csv, ",%ld", (long)(filtered ? s.windowNrgF[history][w]
                                                      : s.windowNrg[history][w]));
  std::fprintf(csv, "\n");
}

int main(int argc, char **argv) {
  const char *wavPath = NULL, *csvPath = NULL, *signal = "impulse";
  bool signalSelected = false;
  int frameLimit = 0;  // 0: whole WAV, or 10 generated frames.
  for (int i = 1; i < argc; ++i) {
    if (!std::strcmp(argv[i], "--wav") && i + 1 < argc) wavPath = argv[++i];
    else if (!std::strcmp(argv[i], "--csv") && i + 1 < argc) csvPath = argv[++i];
    else if (!std::strcmp(argv[i], "--signal") && i + 1 < argc) {
      signal = argv[++i];
      signalSelected = true;
    } else if (!std::strcmp(argv[i], "--frames") && i + 1 < argc) {
      char *end = NULL;
      errno = 0;
      long count = std::strtol(argv[++i], &end, 10);
      if (!*argv[i] || *end || errno == ERANGE || count <= 0 || count > INT_MAX) {
        std::fprintf(stderr, "--frames must be an integer in 1..%d.\n", INT_MAX);
        return 1;
      }
      frameLimit = (int)count;
    } else {
      std::fprintf(stderr, "Usage: %s [--signal impulse|silence|sine | --wav mono.wav] "
                           "[--frames N] [--csv trace.csv]\n", argv[0]);
      return 1;
    }
  }
  if ((wavPath && signalSelected) ||
      (std::strcmp(signal, "impulse") && std::strcmp(signal, "silence") &&
       std::strcmp(signal, "sine"))) {
    std::fprintf(stderr, "Select either a WAV or a supported generated signal.\n");
    return 1;
  }
  if (wavPath && csvPath && !std::strcmp(wavPath, csvPath)) {
    std::fprintf(stderr, "Input and CSV paths must differ.\n");
    return 1;
  }

  void *wav = NULL;
  unsigned int dataBytes = 0;
  int sampleRate = 48000;
  if (wavPath) {
    wav = wav_read_open(wavPath);
    int format = 0, channels = 0, bits = 0;
    if (!wav || !wav_get_header(wav, &format, &channels, &sampleRate, &bits,
                                &dataBytes) ||
        format != 1 || channels != 1 || bits != 16 || sampleRate <= 0 ||
        dataBytes == 0 || (dataBytes & 1)) {
      std::fprintf(stderr, "Input must be a nonempty mono PCM16 WAV.\n");
      if (wav) wav_read_close(wav);
      return 1;
    }
  }
  FILE *csv = csvPath ? std::fopen(csvPath, "w") : NULL;
  if (csvPath && !csv) {
    std::perror(csvPath);
    if (wav) wav_read_close(wav);
    return 1;
  }
  if (csv) csvHeader(csv);

  BLOCK_SWITCHING_CONTROL state;
  FDKaacEnc_InitBlockSwitching(&state, 0);  // Once, AAC-LC.
  int result = 0, processed = 0;
  const unsigned int totalSamples = dataBytes / 2;
  const int available = wav ? (int)((totalSamples + FRAME_LEN - 1) / FRAME_LEN) : 10;
  const int frames = frameLimit ? (wav && frameLimit > available ? available : frameLimit)
                               : available;
  std::printf("Input=%s, sampleRate=%d, AAC-LC, 1024 samples/frame\n",
              wavPath ? wavPath : signal, sampleRate);
  std::printf("Output below is AFTER mono SyncBlockSwitching.\n"
              "frame valid attack index sequence shape groups groupLen\n");
  for (int frame = 0; frame < frames; ++frame) {
    INT_PCM pcm[FRAME_LEN] = {};
    int valid = FRAME_LEN;
    if (wav) {
      unsigned char bytes[FRAME_LEN * 2];
      const unsigned int remaining = totalSamples - (unsigned int)frame * FRAME_LEN;
      valid = remaining < FRAME_LEN ? (int)remaining : FRAME_LEN;
      if (wav_read_data(wav, bytes, (unsigned int)valid * 2) != valid * 2) {
        std::fprintf(stderr, "Truncated WAV at frame %d.\n", frame);
        result = 1;
        break;
      }
      for (int n = 0; n < valid; ++n) {
        const int value = bytes[2 * n] | ((unsigned int)bytes[2 * n + 1] << 8);
        pcm[n] = (INT_PCM)(value >= 32768 ? value - 65536 : value);
      }
    } else makeInput(pcm, frame, signal);

    // The actual DUT call: change pcm[] above to supply your own input.
    if (FDKaacEnc_BlockSwitching(&state, FRAME_LEN, 0, pcm) != 0) {
      result = 1;
      break;
    }
    if (csv) csvRow(csv, frame, valid, "before_sync", state);
    // Match the mono encoder's final grouping step. Right state is unused.
    if (FDKaacEnc_SyncBlockSwitching(&state, NULL, 1, 0) != 0) {
      result = 1;
      break;
    }
    if (csv) csvRow(csv, frame, valid, "after_sync", state);
    std::printf("%5d %5d %6d %5d %-8s %-5s %6d [%d,%d,%d,%d]\n", frame,
                valid, state.attack, state.attackIndex,
                sequenceName(state.lastWindowSequence), shapeName(state.windowShape),
                state.noOfGroups, state.groupLen[0], state.groupLen[1],
                state.groupLen[2], state.groupLen[3]);
    ++processed;
  }
  if (wav) wav_read_close(wav);
  if (csv) {
    const bool writeFailed = std::ferror(csv) != 0;
    if (std::fclose(csv) != 0 || writeFailed) result = 1;
  }
  std::printf("Processed %d frames; status=%s%s\n", processed,
              result ? "ERROR" : "OK", csvPath ? "; CSV includes both phases" : "");
  return result;
}
