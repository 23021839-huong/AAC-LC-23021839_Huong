#!/usr/bin/env python3
"""Summarize QC Step 0 frame, workload, DMA, and overhead measurements."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable


def nearest_rank(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def distribution(values: Iterable[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered:
        return {"samples": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "samples": len(ordered),
        "p50": nearest_rank(ordered, 0.50),
        "p95": nearest_rank(ordered, 0.95),
        "p99": nearest_rank(ordered, 0.99),
        "max": ordered[-1],
    }


def read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def run_metadata(csv_path: Path) -> dict[str, str]:
    return read_key_values(csv_path.parent / "manifest.txt")


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def summarize_provenance(root: Path) -> dict[str, object]:
    snapshot = root / "snapshot"
    manifest = read_key_values(snapshot / "campaign_manifest.txt")
    required_nonempty = [
        "campaign_manifest.txt",
        "git_revision.txt",
        "working_tree_diff.sha256",
        "relevant_source.sha256",
        "gcc_version.txt",
        "gxx_version.txt",
        "cmake_version.txt",
        "compiler_macros.txt",
        "arm_feature_macros.txt",
        "cpuinfo.txt",
        "cpu_frequency.txt",
        "rom_checksums.sha256",
        "input_checksums.sha256",
        "build_plain/CMakeCache.txt",
        "build_plain/compile_commands.json",
        "build_profile/CMakeCache.txt",
        "build_profile/compile_commands.json",
    ]
    missing = [
        name
        for name in required_nonempty
        if not (snapshot / name).is_file() or (snapshot / name).stat().st_size == 0
    ]
    diff_exists = (snapshot / "working_tree.diff").is_file()
    status_exists = (snapshot / "git_status.txt").is_file()
    frequency_text = (
        (snapshot / "cpu_frequency.txt").read_text(encoding="utf-8", errors="replace")
        if (snapshot / "cpu_frequency.txt").is_file()
        else ""
    )
    machine = manifest.get("machine", "")
    return {
        "machine": machine,
        "armv7_target": machine.startswith("armv7"),
        "metadata_complete": not missing and diff_exists and status_exists,
        "cpu_governor_and_frequency_present": (
            "governor=" in frequency_text and "freq=" in frequency_text
        ),
        "missing_files": missing,
        "working_tree_diff_present": diff_exists,
        "git_status_present": status_exists,
    }


def summarize_frames(root: Path, output: Path) -> tuple[dict[str, object], set[str]]:
    timer_values: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: {"wall_us": [], "cpu_us": [], "calls": []}
    )
    counter_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    profile_cases: set[str] = set()

    for path in root.rglob("profile_frames.csv"):
        metadata = run_metadata(path)
        case = metadata.get("case", path.parent.parent.parent.name)
        profile_cases.add(case)
        with path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                key = (case, row["name"])
                if row["kind"] == "timer":
                    timer_values[key]["wall_us"].append(int(row["wall_ns"]) / 1000.0)
                    timer_values[key]["cpu_us"].append(int(row["cpu_ns"]) / 1000.0)
                    timer_values[key]["calls"].append(float(row["calls"]))
                elif row["kind"] == "counter":
                    counter_values[key].append(float(row["value"]))

    timer_rows: list[dict[str, object]] = []
    for (case, block), values in sorted(timer_values.items()):
        wall = distribution(values["wall_us"])
        cpu = distribution(values["cpu_us"])
        calls = distribution(values["calls"])
        timer_rows.append(
            {
                "case": case,
                "block": block,
                "frames": wall["samples"],
                "wall_p50_us": f"{wall['p50']:.3f}",
                "wall_p95_us": f"{wall['p95']:.3f}",
                "wall_p99_us": f"{wall['p99']:.3f}",
                "wall_max_us": f"{wall['max']:.3f}",
                "cpu_p50_us": f"{cpu['p50']:.3f}",
                "cpu_p95_us": f"{cpu['p95']:.3f}",
                "cpu_p99_us": f"{cpu['p99']:.3f}",
                "cpu_max_us": f"{cpu['max']:.3f}",
                "calls_p50": f"{calls['p50']:.3f}",
                "calls_p95": f"{calls['p95']:.3f}",
                "calls_p99": f"{calls['p99']:.3f}",
                "calls_max": f"{calls['max']:.3f}",
            }
        )
    write_csv(
        output / "frame_timer_summary.csv",
        timer_rows,
        [
            "case",
            "block",
            "frames",
            "wall_p50_us",
            "wall_p95_us",
            "wall_p99_us",
            "wall_max_us",
            "cpu_p50_us",
            "cpu_p95_us",
            "cpu_p99_us",
            "cpu_max_us",
            "calls_p50",
            "calls_p95",
            "calls_p99",
            "calls_max",
        ],
    )

    counter_rows: list[dict[str, object]] = []
    for (case, counter), values in sorted(counter_values.items()):
        stats = distribution(values)
        counter_rows.append(
            {
                "case": case,
                "counter": counter,
                "frames": stats["samples"],
                "p50": f"{stats['p50']:.3f}",
                "p95": f"{stats['p95']:.3f}",
                "p99": f"{stats['p99']:.3f}",
                "max": f"{stats['max']:.3f}",
            }
        )
    write_csv(
        output / "frame_counter_summary.csv",
        counter_rows,
        ["case", "counter", "frames", "p50", "p95", "p99", "max"],
    )

    report = {
        "timer_groups": len(timer_rows),
        "counter_groups": len(counter_rows),
        "has_frame_total": any(block == "frame_total" for _, block in timer_values),
        "has_r_distribution": any(counter == "qmax_scans" for _, counter in counter_values),
    }
    return report, profile_cases


def summarize_band_trials(root: Path, output: Path) -> dict[str, object]:
    grouped: dict[tuple[str, int, int], dict[str, list[float]]] = defaultdict(
        lambda: {"trials": [], "lines": []}
    )
    for path in root.rglob("profile_band_trials.csv"):
        metadata = run_metadata(path)
        case = metadata.get("case", path.parent.parent.parent.name)
        with path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                key = (case, int(row["channel"]), int(row["sfb"]))
                grouped[key]["trials"].append(float(row["trials"]))
                grouped[key]["lines"].append(float(row["total_line_evaluations"]))

    rows: list[dict[str, object]] = []
    all_trials: list[float] = []
    for (case, channel, sfb), values in sorted(grouped.items()):
        trial_stats = distribution(values["trials"])
        line_stats = distribution(values["lines"])
        all_trials.extend(values["trials"])
        rows.append(
            {
                "case": case,
                "channel": channel,
                "sfb": sfb,
                "active_frames": trial_stats["samples"],
                "kb_p50": f"{trial_stats['p50']:.3f}",
                "kb_p95": f"{trial_stats['p95']:.3f}",
                "kb_p99": f"{trial_stats['p99']:.3f}",
                "kb_max": f"{trial_stats['max']:.3f}",
                "line_trials_p50": f"{line_stats['p50']:.3f}",
                "line_trials_p95": f"{line_stats['p95']:.3f}",
                "line_trials_p99": f"{line_stats['p99']:.3f}",
                "line_trials_max": f"{line_stats['max']:.3f}",
            }
        )
    write_csv(
        output / "kb_distribution.csv",
        rows,
        [
            "case",
            "channel",
            "sfb",
            "active_frames",
            "kb_p50",
            "kb_p95",
            "kb_p99",
            "kb_max",
            "line_trials_p50",
            "line_trials_p95",
            "line_trials_p99",
            "line_trials_max",
        ],
    )
    return {"band_groups": len(rows), "overall_kb": distribution(all_trials)}


def summarize_process_overhead(
    root: Path, output: Path, primary: dict[str, object]
) -> dict[str, object]:
    values: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: {"elapsed": [], "cpu": []}
    )
    hashes: dict[str, set[str]] = defaultdict(set)
    repeats: dict[tuple[str, str], set[str]] = defaultdict(set)
    scope_mismatches: list[str] = []
    expected_manifest = {
        "aot": primary["audio_object_type"],
        "frame_length_samples": primary["frame_length_samples"],
        "sample_rate_hz": primary["sample_rate_hz"],
        "channels": primary["channels"],
        "channel_mode": primary["channel_mode"],
        "transport": primary["transport"],
        "rate_control": primary["rate_control"],
        "bitrate_bps": primary["bitrate_bps"],
        "afterburner": primary["afterburner"],
    }

    for path in root.rglob("process_time.csv"):
        metadata = run_metadata(path)
        case = metadata.get("case", "unknown")
        variant = metadata.get("build_variant", "unknown")
        repeat = metadata.get("repeat", path.parent.name)
        repeats[(case, variant)].add(repeat)
        for key, expected in expected_manifest.items():
            actual = metadata.get(key)
            if actual != str(expected):
                scope_mismatches.append(
                    f"{path.parent}: {key}={actual!r}, expected {str(expected)!r}"
                )
        output_hash = metadata.get("output_sha256")
        if output_hash:
            hashes[case].add(output_hash)
        with path.open(newline="", encoding="utf-8") as stream:
            row = next(csv.DictReader(stream))
        values[(case, variant)]["elapsed"].append(float(row["elapsed_s"]))
        values[(case, variant)]["cpu"].append(
            float(row["user_s"]) + float(row["system_s"])
        )

    rows: list[dict[str, object]] = []
    all_cases = sorted({key[0] for key in values})
    paired_cases: list[str] = []
    for case in all_cases:
        plain = values.get((case, "plain"))
        profile = values.get((case, "profile"))
        if plain is None or profile is None:
            continue
        paired_cases.append(case)
        plain_elapsed = distribution(plain["elapsed"])
        profile_elapsed = distribution(profile["elapsed"])
        plain_cpu = distribution(plain["cpu"])
        profile_cpu = distribution(profile["cpu"])
        wall_overhead = (
            100.0 * (profile_elapsed["p50"] / plain_elapsed["p50"] - 1.0)
            if plain_elapsed["p50"]
            else 0.0
        )
        cpu_overhead = (
            100.0 * (profile_cpu["p50"] / plain_cpu["p50"] - 1.0)
            if plain_cpu["p50"]
            else 0.0
        )
        rows.append(
            {
                "case": case,
                "plain_runs": plain_elapsed["samples"],
                "profile_runs": profile_elapsed["samples"],
                "plain_elapsed_p50_s": f"{plain_elapsed['p50']:.6f}",
                "plain_elapsed_p95_s": f"{plain_elapsed['p95']:.6f}",
                "plain_elapsed_p99_s": f"{plain_elapsed['p99']:.6f}",
                "plain_elapsed_max_s": f"{plain_elapsed['max']:.6f}",
                "profile_elapsed_p50_s": f"{profile_elapsed['p50']:.6f}",
                "profile_elapsed_p95_s": f"{profile_elapsed['p95']:.6f}",
                "profile_elapsed_p99_s": f"{profile_elapsed['p99']:.6f}",
                "profile_elapsed_max_s": f"{profile_elapsed['max']:.6f}",
                "wall_overhead_percent": f"{wall_overhead:.3f}",
                "plain_cpu_p50_s": f"{plain_cpu['p50']:.6f}",
                "plain_cpu_p95_s": f"{plain_cpu['p95']:.6f}",
                "plain_cpu_p99_s": f"{plain_cpu['p99']:.6f}",
                "plain_cpu_max_s": f"{plain_cpu['max']:.6f}",
                "profile_cpu_p50_s": f"{profile_cpu['p50']:.6f}",
                "profile_cpu_p95_s": f"{profile_cpu['p95']:.6f}",
                "profile_cpu_p99_s": f"{profile_cpu['p99']:.6f}",
                "profile_cpu_max_s": f"{profile_cpu['max']:.6f}",
                "cpu_overhead_percent": f"{cpu_overhead:.3f}",
            }
        )
    write_csv(
        output / "instrumentation_overhead.csv",
        rows,
        [
            "case",
            "plain_runs",
            "profile_runs",
            "plain_elapsed_p50_s",
            "plain_elapsed_p95_s",
            "plain_elapsed_p99_s",
            "plain_elapsed_max_s",
            "profile_elapsed_p50_s",
            "profile_elapsed_p95_s",
            "profile_elapsed_p99_s",
            "profile_elapsed_max_s",
            "wall_overhead_percent",
            "plain_cpu_p50_s",
            "plain_cpu_p95_s",
            "plain_cpu_p99_s",
            "plain_cpu_max_s",
            "profile_cpu_p50_s",
            "profile_cpu_p95_s",
            "profile_cpu_p99_s",
            "profile_cpu_max_s",
            "cpu_overhead_percent",
        ],
    )
    minimum_repeats = min((len(item) for item in repeats.values()), default=0)
    output_hashes_present = bool(all_cases) and all(case in hashes for case in all_cases)
    output_hash_conflict = any(len(items) > 1 for items in hashes.values())
    return {
        "paired_cases": paired_cases,
        "all_cases_paired": bool(all_cases) and paired_cases == all_cases,
        "minimum_repeats": minimum_repeats,
        "output_hashes_present": output_hashes_present,
        "output_hash_conflict": output_hash_conflict,
        "output_hash_consistent": output_hashes_present and not output_hash_conflict,
        "configuration_locked": bool(repeats) and not scope_mismatches,
        "scope_mismatches": scope_mismatches,
    }


def summarize_dma(root: Path, output: Path, scope: dict[str, object]) -> dict[str, object]:
    grouped: dict[tuple[str, str, str, int], dict[str, list[float]]] = defaultdict(
        lambda: {"wall_us": [], "cpu_us": [], "bytes": [], "transactions": []}
    )
    for path in root.rglob("dma_results.csv"):
        with path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                key = (
                    row["direction"],
                    row["wait_mode"],
                    row["cache_mode"],
                    int(row["size_bytes"]),
                )
                grouped[key]["wall_us"].append(int(row["wall_ns"]) / 1000.0)
                grouped[key]["cpu_us"].append(int(row["cpu_ns"]) / 1000.0)
                grouped[key]["bytes"].append(float(row["logical_bus_bytes"]))
                grouped[key]["transactions"].append(float(row["dma_submissions"]))

    rows: list[dict[str, object]] = []
    for (direction, wait_mode, cache_mode, size), values in sorted(grouped.items()):
        wall = distribution(values["wall_us"])
        cpu = distribution(values["cpu_us"])
        rows.append(
            {
                "direction": direction,
                "wait_mode": wait_mode,
                "cache_mode": cache_mode,
                "size_bytes": size,
                "samples": wall["samples"],
                "wall_p50_us": f"{wall['p50']:.3f}",
                "wall_p95_us": f"{wall['p95']:.3f}",
                "wall_p99_us": f"{wall['p99']:.3f}",
                "wall_max_us": f"{wall['max']:.3f}",
                "cpu_p50_us": f"{cpu['p50']:.3f}",
                "cpu_p95_us": f"{cpu['p95']:.3f}",
                "cpu_p99_us": f"{cpu['p99']:.3f}",
                "cpu_max_us": f"{cpu['max']:.3f}",
                "logical_bus_bytes": int(values["bytes"][0]),
                "dma_submissions": int(values["transactions"][0]),
            }
        )
    write_csv(
        output / "dma_summary.csv",
        rows,
        [
            "direction",
            "wait_mode",
            "cache_mode",
            "size_bytes",
            "samples",
            "wall_p50_us",
            "wall_p95_us",
            "wall_p99_us",
            "wall_max_us",
            "cpu_p50_us",
            "cpu_p95_us",
            "cpu_p99_us",
            "cpu_max_us",
            "logical_bus_bytes",
            "dma_submissions",
        ],
    )

    matrix = scope["dma_matrix"]
    required = {
        (direction, wait_mode, cache_mode, int(size))
        for direction in matrix["directions"]
        for wait_mode in matrix["wait_modes"]
        for cache_mode in matrix["cache_modes"]
        for size in matrix["sizes_bytes"]
    }
    return {
        "measured_combinations": len(grouped),
        "required_combinations": len(required),
        "matrix_complete": required.issubset(grouped),
        "missing_combinations": [list(item) for item in sorted(required - set(grouped))],
    }


def summarize_bus_counters(
    root: Path, output: Path, scope: dict[str, object]
) -> dict[str, object]:
    """Summarize physical AXI counters exported by an APM/ILA measurement.

    Expected input filename: axi_bus_counters.csv.  Each row must carry the
    same matrix coordinates as dma_results.csv plus byte and transaction counts.
    """
    metrics = (
        "read_bytes",
        "write_bytes",
        "read_transactions",
        "write_transactions",
    )
    grouped: dict[tuple[str, str, str, int], dict[str, list[float]]] = defaultdict(
        lambda: {metric: [] for metric in metrics}
    )
    invalid_files: list[str] = []
    for path in root.rglob("axi_bus_counters.csv"):
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            required_fields = {
                "direction",
                "wait_mode",
                "cache_mode",
                "size_bytes",
                *metrics,
            }
            if reader.fieldnames is None or not required_fields.issubset(reader.fieldnames):
                invalid_files.append(str(path))
                continue
            for row in reader:
                key = (
                    row["direction"],
                    row["wait_mode"],
                    row["cache_mode"],
                    int(row["size_bytes"]),
                )
                for metric in metrics:
                    grouped[key][metric].append(float(row[metric]))

    rows: list[dict[str, object]] = []
    for (direction, wait_mode, cache_mode, size), values in sorted(grouped.items()):
        row: dict[str, object] = {
            "direction": direction,
            "wait_mode": wait_mode,
            "cache_mode": cache_mode,
            "size_bytes": size,
            "samples": len(values["read_bytes"]),
        }
        for metric in metrics:
            stats = distribution(values[metric])
            row[f"{metric}_p50"] = f"{stats['p50']:.3f}"
            row[f"{metric}_p95"] = f"{stats['p95']:.3f}"
            row[f"{metric}_p99"] = f"{stats['p99']:.3f}"
            row[f"{metric}_max"] = f"{stats['max']:.3f}"
        rows.append(row)
    fields = ["direction", "wait_mode", "cache_mode", "size_bytes", "samples"]
    fields.extend(
        f"{metric}_{stat}"
        for metric in metrics
        for stat in ("p50", "p95", "p99", "max")
    )
    write_csv(output / "axi_bus_summary.csv", rows, fields)

    matrix = scope["dma_matrix"]
    required = {
        (direction, wait_mode, cache_mode, int(size))
        for direction in matrix["directions"]
        for wait_mode in matrix["wait_modes"]
        for cache_mode in matrix["cache_modes"]
        for size in matrix["sizes_bytes"]
    }
    return {
        "measured_combinations": len(grouped),
        "required_combinations": len(required),
        "matrix_complete": required.issubset(grouped),
        "missing_combinations": [list(item) for item in sorted(required - set(grouped))],
        "invalid_files": invalid_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--scope",
        type=Path,
        default=Path(__file__).with_name("scope_v1.json"),
    )
    args = parser.parse_args()

    output = args.output or args.artifact_root / "summary"
    output.mkdir(parents=True, exist_ok=True)
    scope = json.loads(args.scope.read_text(encoding="utf-8"))

    provenance_report = summarize_provenance(args.artifact_root)
    frame_report, profile_cases = summarize_frames(args.artifact_root, output)
    band_report = summarize_band_trials(args.artifact_root, output)
    overhead_report = summarize_process_overhead(
        args.artifact_root, output, scope["primary_configuration"]
    )
    dma_report = summarize_dma(args.artifact_root, output, scope)
    bus_report = summarize_bus_counters(args.artifact_root, output, scope)

    resource_reports = list(args.artifact_root.rglob("overlay_resource_budget.json"))
    resource_gate = False
    resource_payload = None
    if resource_reports:
        resource_payload = json.loads(resource_reports[-1].read_text(encoding="utf-8"))
        resource_gate = resource_payload.get("status") == "PASS"

    minimum_repeats = int(scope["minimum_repeats_per_case_and_build"])
    normalized_cases = " ".join(case.lower() for case in profile_cases)
    synthetic_classes = [str(item).lower() for item in scope["primary_corpus_classes"]]
    synthetic_present = all(name in normalized_cases for name in synthetic_classes)
    real_audio_present = (
        "speech" in normalized_cases
        and "stable_music" in normalized_cases
        and ("transient_music" in normalized_cases or "applause" in normalized_cases)
    )

    checks = {
        "armv7_target": bool(provenance_report["armv7_target"]),
        "provenance_metadata": bool(provenance_report["metadata_complete"]),
        "cpu_governor_and_frequency": bool(
            provenance_report["cpu_governor_and_frequency_present"]
        ),
        "per_frame_wall_and_cpu": bool(frame_report["has_frame_total"]),
        "r_distribution": bool(frame_report["has_r_distribution"]),
        "kb_distribution": int(band_report["band_groups"]) > 0,
        "plain_profile_overhead_pair": bool(overhead_report["all_cases_paired"]),
        "primary_configuration_locked": bool(overhead_report["configuration_locked"]),
        "minimum_three_repeats": int(overhead_report["minimum_repeats"]) >= minimum_repeats,
        "bitstream_hash_consistent": bool(overhead_report["output_hash_consistent"]),
        "synthetic_corpus": synthetic_present,
        "real_audio_corpus": real_audio_present,
        "dma_matrix": bool(dma_report["matrix_complete"]),
        "physical_bus_bytes_and_transactions": bool(bus_report["matrix_complete"]),
        "overlay_resource_budget": resource_gate,
    }
    hard_failures: list[str] = []
    if provenance_report["machine"] and not provenance_report["armv7_target"]:
        hard_failures.append("campaign was not measured on the ARMv7 target")
    if overhead_report["output_hash_conflict"]:
        hard_failures.append("instrumented/plain output hashes differ")
    if overhead_report["scope_mismatches"]:
        hard_failures.append("one or more runs do not match the locked primary configuration")
    if resource_payload is not None and resource_payload.get("status") == "FAIL":
        hard_failures.append("QC target does not fit the measured overlay resource budget")
    status = "FAIL" if hard_failures else ("PASS" if all(checks.values()) else "PENDING")
    report = {
        "schema_version": 1,
        "scope_id": scope["scope_id"],
        "status": status,
        "hard_failures": hard_failures,
        "checks": checks,
        "provenance": provenance_report,
        "frames": frame_report,
        "band_trials": band_report,
        "instrumentation_overhead": overhead_report,
        "dma": dma_report,
        "physical_axi_bus": bus_report,
        "resource_budget": resource_payload,
    }
    report_path = output / "step0_gate.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
