#!/usr/bin/env bash

# Reproducible Step-0 workload campaign for FDK-AAC on PYNQ-Z2.
set -euo pipefail

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/../../../.." && pwd)
profiling_dir="$repo_root/my_workspace/quantization_coding/profiling"

corpus_dir=${1:-"$profiling_dir/corpus/primary_mono_48k"}
artifact_root=${2:-"$repo_root/my_workspace/pynq_z2/artifacts/qc_step0"}
repeats=${REPEATS:-3}
cpu_affinity=${CPU_AFFINITY:-1}
build_jobs=${BUILD_JOBS:-2}
build_root=${BUILD_ROOT:-"$repo_root/build-pynq-qc-step0"}
bitrate=64000

case "$repeats" in
  '' | *[!0-9]*) die "REPEATS must be an integer" ;;
esac
[ "$repeats" -ge 3 ] || die "Step-0 gate requires REPEATS >= 3"

for command_name in cmake gcc g++ git python3 sha256sum taskset /usr/bin/time; do
  command -v "$command_name" >/dev/null 2>&1 || die "Missing command: $command_name"
done

machine=$(uname -m)
case "$machine" in
  armv7l | armv7*) ;;
  *)
    [ "${ALLOW_NON_ARM:-0}" = 1 ] ||
      die "Expected ARMv7/PYNQ-Z2, got '$machine' (set ALLOW_NON_ARM=1 only for runner testing)"
    ;;
esac

first_wav=$(find "$corpus_dir" -maxdepth 1 -type f -iname '*.wav' -print -quit 2>/dev/null || true)
if [ -z "$first_wav" ]; then
  mkdir -p "$corpus_dir"
  python3 "$profiling_dir/generate_corpus.py" --output "$corpus_dir"
fi

run_id=$(date -u +%Y%m%dT%H%M%SZ)
run_dir="$artifact_root/$run_id"
snapshot_dir="$run_dir/snapshot"
results_dir="$run_dir/results"
summary_dir="$run_dir/summary"
mkdir -p "$snapshot_dir" "$results_dir" "$summary_dir"

# Repository and source provenance.  The tracked diff and the source hash list
# together cover modified tracked files as well as relevant untracked files.
git -C "$repo_root" rev-parse HEAD >"$snapshot_dir/git_revision.txt"
git -C "$repo_root" status --porcelain=v1 -uall >"$snapshot_dir/git_status.txt"
git -C "$repo_root" diff --binary --no-ext-diff HEAD >"$snapshot_dir/working_tree.diff"
sha256sum "$snapshot_dir/working_tree.diff" >"$snapshot_dir/working_tree_diff.sha256"
(
  cd "$repo_root"
  find libAACenc libSYS CMakeLists.txt \
    my_workspace/quantization_coding/profiling \
    my_workspace/pynq_z2/sw/scripts \
    -type f -print0 | sort -z | xargs -0 sha256sum
) >"$snapshot_dir/relevant_source.sha256"

{
  printf 'run_id=%s\n' "$run_id"
  printf 'utc_started=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'machine=%s\n' "$machine"
  printf 'kernel=%s\n' "$(uname -srvmo)"
  printf 'scope_id=aac_lc_qc_step0_v1\n'
  printf 'aot=2\nframe_length_samples=1024\nsample_rate_hz=48000\n'
  printf 'channels=1\nchannel_mode=MODE_1\ntransport=ADTS\n'
  printf 'rate_control=CBR\nbitrate_bps=%s\nafterburner=1\n' "$bitrate"
  printf 'repeats=%s\ncpu_affinity=%s\n' "$repeats" "$cpu_affinity"
} >"$snapshot_dir/campaign_manifest.txt"

gcc --version >"$snapshot_dir/gcc_version.txt"
g++ --version >"$snapshot_dir/gxx_version.txt"
cmake --version >"$snapshot_dir/cmake_version.txt"
gcc -dM -E - </dev/null >"$snapshot_dir/compiler_macros.txt"
grep -E '__ARM|__arm|__VFP|__NEON|__thumb|__GNUC|__BYTE_ORDER' \
  "$snapshot_dir/compiler_macros.txt" >"$snapshot_dir/arm_feature_macros.txt" || true
cp /proc/cpuinfo "$snapshot_dir/cpuinfo.txt"
{
  for cpu_dir in /sys/devices/system/cpu/cpu[0-9]*; do
    cpu_name=${cpu_dir##*/}
    for item in scaling_governor scaling_cur_freq scaling_min_freq scaling_max_freq \
      cpuinfo_cur_freq cpuinfo_min_freq cpuinfo_max_freq; do
      path="$cpu_dir/cpufreq/$item"
      [ -r "$path" ] && printf '%s.%s=%s\n' "$cpu_name" "$item" "$(cat "$path")"
    done
  done
} >"$snapshot_dir/cpu_frequency.txt"

rom_files=(
  "$repo_root/libAACenc/src/common/aacEnc_rom.cpp"
  "$repo_root/libAACenc/src/aacEnc_rom.h"
  "$repo_root/my_workspace/quantization_coding/quantization_reference/python_ref/fdk_tables.py"
  "$repo_root/my_workspace/quantization_coding/quantization_reference/cpp_ref/fdk_quant_tables.inc"
)
for rom_file in "${rom_files[@]}"; do
  [ -f "$rom_file" ] || die "Required ROM/table file missing: $rom_file"
done
sha256sum "${rom_files[@]}" >"$snapshot_dir/rom_checksums.sha256"

build_variant() {
  local variant=$1
  local profiling=$2
  local build_dir="$build_root/$variant"
  mkdir -p "$build_dir"
  cmake -S "$repo_root" -B "$build_dir" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DBUILD_PROGRAMS=ON \
    -DBUILD_SHARED_LIBS=OFF \
    -DFDK_ENABLE_ENCODER_PROFILING="$profiling"
  cmake --build "$build_dir" -- -j"$build_jobs"
  [ -x "$build_dir/aac-enc" ] || die "Encoder was not built: $build_dir/aac-enc"
  mkdir -p "$snapshot_dir/build_$variant"
  cp "$build_dir/CMakeCache.txt" "$snapshot_dir/build_$variant/"
  cp "$build_dir/compile_commands.json" "$snapshot_dir/build_$variant/"
}

build_variant plain OFF
build_variant profile ON

mapfile -d '' wav_files < <(
  {
    find "$corpus_dir" -maxdepth 1 -type f -iname '*.wav' -print0
    [ -f "$repo_root/my_workspace/INPUT/data/abc_votay.wav" ] && \
      printf '%s\0' "$repo_root/my_workspace/INPUT/data/abc_votay.wav"
  } | sort -zu
)
[ "${#wav_files[@]}" -gt 0 ] || die "No WAV files in $corpus_dir"

python3 - "${wav_files[@]}" <<'PY'
import sys
import wave

bad = []
for name in sys.argv[1:]:
    try:
        with wave.open(name, "rb") as stream:
            values = (stream.getnchannels(), stream.getframerate(), stream.getsampwidth())
        if values != (1, 48000, 2):
            bad.append(f"{name}: channels/rate/sample_bytes={values}, expected (1, 48000, 2)")
    except (wave.Error, EOFError) as exc:
        bad.append(f"{name}: {exc}")
if bad:
    raise SystemExit("Primary corpus validation failed:\n" + "\n".join(bad))
PY

sha256sum "${wav_files[@]}" >"$snapshot_dir/input_checksums.sha256"

for input_wav in "${wav_files[@]}"; do
  base_name=$(basename "$input_wav" .wav)
  case_name=$(printf '%s' "$base_name" | tr -cs 'A-Za-z0-9._-' '_')
  if [ "$case_name" = abc_votay ]; then
    case_name=applause_abc_votay
  fi
  for variant in plain profile trace; do
    if [ "$variant" = plain ]; then
      encoder="$build_root/plain/aac-enc"
    else
      encoder="$build_root/profile/aac-enc"
    fi
    for ((repeat = 1; repeat <= repeats; repeat++)); do
      one_run="$results_dir/$case_name/$variant/repeat_$repeat"
      mkdir -p "$one_run"
      output_aac="$one_run/output.aac"
      timing_raw="$one_run/process_time.raw"
      timing_csv="$one_run/process_time.csv"
      aggregate_csv="$one_run/encoder_profile.csv"
      frames_csv="$one_run/profile_frames.csv"
      bands_csv="$one_run/profile_band_trials.csv"

      printf 'case=%s variant=%s repeat=%s/%s\n' \
        "$case_name" "$variant" "$repeat" "$repeats"
      if [ "$variant" = trace ]; then
        /usr/bin/time -f '%e,%U,%S,%M,%F,%R,%c,%w' -o "$timing_raw" \
          env FDK_PROFILE_CSV="$aggregate_csv" \
              FDK_PROFILE_FRAMES_CSV="$frames_csv" \
              FDK_PROFILE_BANDS_CSV="$bands_csv" \
          taskset -c "$cpu_affinity" "$encoder" \
            -t 2 -r "$bitrate" -a 1 "$input_wav" "$output_aac"
        [ -s "$aggregate_csv" ] || die "Missing aggregate profile: $aggregate_csv"
        [ -s "$frames_csv" ] || die "Missing per-frame profile: $frames_csv"
        [ -s "$bands_csv" ] || die "Missing per-band trials: $bands_csv"
      elif [ "$variant" = profile ]; then
        /usr/bin/time -f '%e,%U,%S,%M,%F,%R,%c,%w' -o "$timing_raw" \
          env FDK_PROFILE_CSV="$aggregate_csv" \
          taskset -c "$cpu_affinity" "$encoder" \
            -t 2 -r "$bitrate" -a 1 "$input_wav" "$output_aac"
        [ -s "$aggregate_csv" ] || die "Missing aggregate profile: $aggregate_csv"
      else
        /usr/bin/time -f '%e,%U,%S,%M,%F,%R,%c,%w' -o "$timing_raw" \
          taskset -c "$cpu_affinity" "$encoder" \
            -t 2 -r "$bitrate" -a 1 "$input_wav" "$output_aac"
      fi
      [ -s "$output_aac" ] || die "Encoder produced an empty output: $output_aac"
      printf 'elapsed_s,user_s,system_s,max_rss_kib,major_faults,minor_faults,involuntary_ctx,voluntary_ctx\n' \
        >"$timing_csv"
      tr -d '\r' <"$timing_raw" >>"$timing_csv"

      input_hash=$(sha256sum "$input_wav" | awk '{print $1}')
      output_hash=$(sha256sum "$output_aac" | awk '{print $1}')
      {
        printf 'case=%s\n' "$case_name"
        printf 'build_variant=%s\n' "$variant"
        printf 'repeat=%s\n' "$repeat"
        printf 'input=%s\ninput_sha256=%s\n' "$input_wav" "$input_hash"
        printf 'output=%s\noutput_sha256=%s\n' "$output_aac" "$output_hash"
        printf 'aot=2\nframe_length_samples=1024\nsample_rate_hz=48000\n'
        printf 'channels=1\nchannel_mode=MODE_1\ntransport=ADTS\n'
        printf 'rate_control=CBR\nbitrate_bps=%s\nafterburner=1\n' "$bitrate"
        printf 'cpu_affinity=%s\n' "$cpu_affinity"
      } >"$one_run/manifest.txt"
      find "$one_run" -maxdepth 1 -type f ! -name SHA256SUMS -print0 | \
        sort -z | xargs -0 sha256sum >"$one_run/SHA256SUMS"
    done
  done
done

python3 "$profiling_dir/analyze_step0.py" "$run_dir" --output "$summary_dir"
printf '\nStep-0 software campaign completed: %s\n' "$run_dir"
printf 'Gate report: %s\n' "$summary_dir/step0_gate.json"
printf 'PENDING is expected until real corpus, DMA matrix, and Vivado resource report are present.\n'
