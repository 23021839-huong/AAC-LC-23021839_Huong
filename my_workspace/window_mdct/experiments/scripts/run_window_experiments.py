"""Run four real native FDK window policies and export measured results."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import uuid
from measure_distortion import inspect_adts, measure_files

ROOT = Path(__file__).resolve().parents[4]
EXPERIMENTS = [("EXP01", "SINE_ONLY", "sine_only", [0, 0, 0, 0]),
               ("EXP02", "KBD_ONLY", "kbd_only", [1, 1, 1, 1]),
               ("EXP03", "SINE_LONG_KBD_SHORT", "sine_long_kbd_short", [0, 0, 1, 0]),
               ("EXP04", "KBD_LONG_SINE_SHORT", "kbd_long_sine_short", [1, 1, 0, 1])]
REQUIRED_COLUMNS = ["experiment_id", "window_mode", "target_bitrate_kbps", "actual_bitrate_kbps",
                    "encoding_time_mean_ms", "encoding_time_std_ms", "mse", "snr_db", "nrmse_percent", "aac_size_bytes"]
EXTRA_COLUMNS = ["status", "error", "payload_bitrate_kbps", "bitrate_over_source_duration_kbps", "aac_size_kb",
                 "source_duration_seconds", "coded_duration_seconds", "adts_frames", "header_bytes", "payload_bytes",
                 "sample_rate", "channels", "source_samples_per_channel", "decoded_samples_per_channel",
                 "alignment_delay_samples", "alignment_correlation", "compared_samples_per_channel",
                 "trailing_padding_samples", "encoder_delay_samples", "decoder_additional_delay_samples",
                 "runs", "warmup_runs", "bitstream_shape_verified", "window_sequences_equal",
                 "only_long_count", "long_start_count", "eight_short_count", "long_stop_count", "aac_sha256", "run_id"]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def validate_trace(rows, meta, table, packets):
    channels = meta["channels"]
    if len(rows) != len(packets) * channels:
        raise ValueError("Transform trace/ADTS frame count mismatch")
    previous = {}
    allowed = {0: {0, 1}, 1: {2}, 2: {2, 3}, 3: {0, 1}}
    by_frame = {}
    for index, row in enumerate(rows):
        frame, ch = int(row["frame_index"]), int(row["channel"])
        seq, shape, prev = int(row["window_sequence_id"]), int(row["window_shape"]), int(row["previous_window_shape"])
        if (frame, ch) != (index // channels, index % channels):
            raise ValueError("Noncontiguous native frame/channel trace")
        if shape != table[seq] or row["experiment_mode"] != meta["window_mode"]:
            raise ValueError("Native window policy differs from requested mode")
        if prev != previous.get(ch, {"shape": 0})["shape"]:
            raise ValueError("Previous window shape history mismatch")
        if ch in previous and seq not in allowed[previous[ch]["seq"]]:
            raise ValueError("Invalid long/short sequence transition")
        right_len = 128 if seq in (1, 2) else 1024
        expected_left_len = previous[ch]["right_len"] if ch in previous else right_len
        expected_left_shape = prev if ch in previous else shape
        if int(row["right_slope_shape"]) != shape or int(row["left_slope_shape"]) != expected_left_shape:
            raise ValueError("MDCT window slope pointer does not match shape history")
        if int(row["right_slope_length"]) != right_len or int(row["left_slope_length"]) != expected_left_len:
            raise ValueError("Window overlap slope length mismatch")
        previous[ch] = {"shape": shape, "seq": seq, "right_len": right_len}
        by_frame.setdefault(frame, {})[ch] = row
    for packet in packets:
        frame_rows = by_frame[packet["frame_index"]]
        check_channels = range(channels) if packet["common_window"] else (0,)
        for ch in check_channels:
            row = frame_rows[ch]
            if int(row["window_shape"]) != packet["window_shape"] or int(row["window_sequence_id"]) != packet["window_sequence_id"]:
                raise ValueError("Bitstream ICS shape/sequence differs from native MDCT trace")
        if channels == 2 and not packet["common_window"]:
            raise ValueError("Full stereo bitstream validation requires common_window=1; second ICS not parsed")
    return [(int(r["frame_index"]), int(r["channel"]), int(r["window_sequence_id"])) for r in rows]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / 'my_workspace/INPUT/data/abc_votay.wav')
    parser.add_argument("--binary", type=Path, default=ROOT / "build/window_experiments/fdk_window_experiment.exe")
    parser.add_argument("--output-dir", type=Path, default=ROOT / 'my_workspace/window_mdct/experiments')
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)
    if args.runs < 5:
        parser.error("At least five measured runs per configuration are required")
    root, source, binary = args.output_dir.resolve(), args.input.resolve(), args.binary.resolve()
    for name in ("encoded", "decoded", "logs", "results", "runs"):
        (root / name).mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    status_path = root / "results/pipeline_status.json"
    status = {"complete": False, "run_id": run_id, "input": str(source), "binary": str(binary),
              "platform": platform.platform(), "machine": platform.machine(), "processor": platform.processor(),
              "python": sys.version, "measured_runs_per_mode": args.runs,
              "timing_order": "EXP01, EXP02, EXP03, EXP04; per-mode fresh encoder warmup, then repeated fresh encoders",
              "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest() if source.exists() else None,
              "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest() if binary.exists() else None,
              "experiments": {}}
    write_json(status_path, status)
    rows, runs, sequence_reference = [], [], None
    for experiment_id, mode, name, table in EXPERIMENTS:
        native = root / "runs" / run_id / name
        native.mkdir(parents=True, exist_ok=True)
        stem = experiment_id.lower() + "_" + name
        row = {"experiment_id": experiment_id, "window_mode": mode, "target_bitrate_kbps": 64,
               "status": "error", "run_id": run_id}
        try:
            command = [str(binary), "--input", str(source), "--output-dir", str(native), "--mode", mode, "--runs", str(args.runs)]
            process = subprocess.run(command, capture_output=True, text=True)
            (native / "process.log").write_text("COMMAND: " + subprocess.list2cmdline(command) + "\n" + process.stdout + process.stderr, encoding="utf-8")
            if process.returncode:
                raise RuntimeError(f"Native runner exit {process.returncode}: {process.stderr.strip()}")
            meta = json.loads((native / "run_metadata.json").read_text())
            if not meta.get("complete") or len(meta["encoding_time_ms"]) != args.runs:
                raise ValueError("Incomplete native measurement run")
            bitstream = inspect_adts((native / "encoded.aac").read_bytes(), inspect_ics=True)
            if (bitstream["sample_rate"], bitstream["channels"], bitstream["adts_frames"]) != (meta["sample_rate"], meta["channels"], meta["adts_frames"]):
                raise ValueError("Native metadata differs from actual ADTS headers")
            with (native / "frame_trace.csv").open() as f:
                trace = list(csv.DictReader(f))
            sequences = validate_trace(trace, meta, table, bitstream["frames"])
            if sequence_reference is None:
                sequence_reference = sequences
            elif sequence_reference != sequences:
                raise ValueError("Window sequence selection differs between experiment policies")
            measured, _ = measure_files(source, native / "decoded.wav",
                                        meta["encoder_delay_samples"] + meta["decoder_additional_delay_samples"])
            if measured["metric_status"] != "ok":
                raise ValueError("Undefined distortion metric: " + measured["metric_status"])
            if measured["compared_samples_per_channel"] != meta["source_samples_per_channel"]:
                raise ValueError("Metrics did not cover every original PCM sample")
            times = meta["encoding_time_ms"]
            counts = Counter(int(r["window_sequence_id"]) for r in trace if int(r["channel"]) == 0)
            row.update({k: v for k, v in bitstream.items() if k != "frames"})
            row.update({k: v for k, v in measured.items() if k in EXTRA_COLUMNS or k in REQUIRED_COLUMNS})
            row.update(error="", encoding_time_mean_ms=statistics.mean(times),
                       encoding_time_std_ms=statistics.stdev(times), aac_size_kb=bitstream["aac_size_bytes"] / 1000,
                       bitrate_over_source_duration_kbps=bitstream["aac_size_bytes"] * 8 / measured["source_duration_seconds"] / 1000,
                       source_samples_per_channel=meta["source_samples_per_channel"],
                       decoded_samples_per_channel=meta["decoded_samples_per_channel"],
                       encoder_delay_samples=meta["encoder_delay_samples"], decoder_additional_delay_samples=meta["decoder_additional_delay_samples"],
                       runs=args.runs, warmup_runs=1, bitstream_shape_verified=True, window_sequences_equal=True,
                       only_long_count=counts[0], long_start_count=counts[1], eight_short_count=counts[2], long_stop_count=counts[3],
                       aac_sha256=hashlib.sha256((native / "encoded.aac").read_bytes()).hexdigest())
            write_json(native / "distortion_alignment.json", measured)
            write_csv(native / "bitstream_ics_trace.csv", bitstream["frames"], list(bitstream["frames"][0]))
            shutil.copy2(native / "encoded.aac", root / "encoded" / (stem + ".aac"))
            shutil.copy2(native / "decoded.wav", root / "decoded" / (experiment_id.lower() + "_decoded.wav"))
            for file, suffix in [("frame_trace.csv", "_window_trace.csv"), ("bitstream_ics_trace.csv", "_bitstream_ics_trace.csv"),
                                 ("run_metadata.json", "_run_metadata.json"), ("distortion_alignment.json", "_distortion_alignment.json"),
                                 ("process.log", "_process.log")]:
                shutil.copy2(native / file, root / "logs" / (experiment_id.lower() + suffix))
            row["status"] = "ok"  # Success includes publication of every required artifact.
            for index, value in enumerate(times, 1):
                runs.append({"experiment_id": experiment_id, "window_mode": mode, "run_index": index,
                             "encoding_time_ms": value, "aac_size_bytes": row["aac_size_bytes"],
                             "aac_sha256": row["aac_sha256"], "status": "ok", "run_id": run_id})
            status["experiments"][experiment_id] = {"status": "ok", "native_directory": str(native), "metrics": row}
            print(f"{experiment_id} {mode}: {row['actual_bitrate_kbps']:.3f} kb/s; "
                  f"{row['encoding_time_mean_ms']:.3f} +/- {row['encoding_time_std_ms']:.3f} ms; "
                  f"SNR={row['snr_db']:.3f} dB; {row['aac_size_bytes']} bytes", flush=True)
        except Exception as error:
            row["status"] = "error"
            row["error"] = str(error)
            write_json(native / "error.json", {"status": "error", "reason": str(error)})
            status["experiments"][experiment_id] = {"status": "error", "error": str(error), "native_directory": str(native)}
            print(f"{experiment_id}: ERROR: {error}", file=sys.stderr, flush=True)
        rows.append(row)
        write_csv(root / "results/window_comparison.csv", rows, REQUIRED_COLUMNS + EXTRA_COLUMNS)
        write_csv(root / "results/window_runs.csv", runs, ["experiment_id", "window_mode", "run_index", "encoding_time_ms", "aac_size_bytes", "aac_sha256", "status", "run_id"])
        write_json(status_path, status)
    if all(row["status"] == "ok" for row in rows):
        if not args.no_plots:
            from plot_results import plot_results
            plot_results(root / "results/window_comparison.csv", root / "results")
        status["complete"] = True
        status["window_sequences_equal"] = True
        write_json(status_path, status)
        print("Measured results:", root / "results/window_comparison.csv")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
