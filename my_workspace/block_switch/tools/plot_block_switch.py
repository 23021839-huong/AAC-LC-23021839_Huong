#!/usr/bin/env python3
"""Plot PCM16 mono WAV and the real probe_block_switch CSV on a shared clock.

Uses a headless backend; runs on Linux servers without a display.
See ../docs/ve_do_thi_block_switch_linux.md for commands and interpretation.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import sys
import wave

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import mlab
from matplotlib.colors import ListedColormap, BoundaryNorm
import numpy as np

FRAME = 1024
SHORT = 128
Q31 = 2147483648.0
SEQUENCES = ["LONG", "START", "SHORT", "STOP"]
COLORS = ["#2563eb", "#d97706", "#dc2626", "#15803d"]
plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.facecolor": "white",
                     "axes.facecolor": "#fafafa", "savefig.facecolor": "white"})


def read_wav(path):
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
            raise ValueError("WAV must be uncompressed mono PCM16, as required by the probe.")
        rate, count = wav.getframerate(), wav.getnframes()
        raw = wav.readframes(count)
    if not count or len(raw) != count * 2:
        raise ValueError("WAV is empty or truncated.")
    return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0, rate


def read_trace(path, sample_count):
    fields = ["frame", "validSamples", "phase", "attack", "attackIndex",
              "lastWindowSequence", "windowShape", "noOfGroups", "accWindowNrg",
              "nBlockSwitchWindows", "allowShortFrames"]
    fields += [f"groupLen{i}" for i in range(4)]
    fields += [f"windowNrgF_current{i}" for i in range(8)]
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = set(fields) - set(reader.fieldnames or [])
        if missing:
            raise ValueError("CSV must come from probe_block_switch --csv; missing: " +
                             ", ".join(sorted(missing)))
        rows = [{key: int(row[key]) for key in fields if key != "phase"}
                for row in reader if row["phase"] == "after_sync"]
    rows.sort(key=lambda row: row["frame"])
    if not rows or [row["frame"] for row in rows] != list(range(len(rows))):
        raise ValueError("after_sync rows must contain consecutive, unique frames starting at 0.")
    if len(rows) > math.ceil(sample_count / FRAME):
        raise ValueError("CSV has more frames than this WAV. Select the matching WAV/CSV pair.")
    for row in rows:
        expected = min(FRAME, sample_count - row["frame"] * FRAME)
        if row["validSamples"] != expected:
            raise ValueError(f"Frame {row['frame']}: validSamples does not match WAV length.")
        if row["nBlockSwitchWindows"] != 8 or row["allowShortFrames"] != 1:
            raise ValueError("This plotter supports the AAC-LC probe only.")
        if row["lastWindowSequence"] not in range(4) or row["windowShape"] not in (0, 1):
            raise ValueError("Invalid AAC-LC sequence or shape in CSV.")
        if row["attack"] not in (0, 1) or row["attackIndex"] not in range(8):
            raise ValueError("Invalid attack flag or index in CSV.")
        groups = [row[f"groupLen{i}"] for i in range(4)]
        n = row["noOfGroups"]
        total = 8 if row["lastWindowSequence"] == 2 else 1
        if not 1 <= n <= 4 or any(v <= 0 for v in groups[:n]) or any(groups[n:]) or sum(groups) != total:
            raise ValueError(f"Frame {row['frame']}: invalid after_sync grouping.")
        if row["accWindowNrg"] < 0 or any(row[f"windowNrgF_current{i}"] < 0 for i in range(8)):
            raise ValueError("Energy columns must be nonnegative raw Q31 values.")
    return rows


def draw_waveform(ax, pcm, rate, start, end):
    first, last = max(0, int(start * rate)), min(len(pcm), math.ceil(end * rate))
    values = pcm[first:last]
    if not len(values):
        return
    stride = max(1, math.ceil(len(values) / 7000))
    if stride == 1:
        ax.plot(np.arange(first, last) / rate, values, color="#1d4ed8", lw=0.55)
    else:
        # Min/max bins preserve narrow clap peaks that ordinary decimation can miss.
        starts = np.arange(0, len(values), stride)
        low, high = np.minimum.reduceat(values, starts), np.maximum.reduceat(values, starts)
        times = (first + starts + stride / 2) / rate
        ax.fill_between(times, low, high, color="#2563eb", alpha=0.85, linewidth=0)
    ax.set_ylim(-1.05, 1.05)
    ax.set_ylabel("PCM amplitude\n(normalized)")
    ax.set_title("1. INPUT | waveform: clap peaks, decay and quiet intervals", loc="left", fontsize=11)


def draw_spectrogram(ax, pcm, rate, start, end):
    first, last = max(0, int(start * rate)), min(len(pcm), math.ceil(end * rate))
    values = pcm[first:last]
    if len(values) < 512:
        values = np.pad(values, (0, 512 - len(values)))
    power, frequencies, centers = mlab.specgram(values, NFFT=512, Fs=rate, noverlap=384)
    # Keep STFT bin centers on the WAV clock rather than stretching to the view.
    artist = ax.pcolormesh(first / rate + centers, frequencies,
                           10 * np.log10(np.maximum(power, 1e-18)),
                           shading="nearest", cmap="magma", vmin=-110, vmax=-35,
                           rasterized=True)
    ax.set_ylim(0, min(12000, rate / 2))
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title("2. INPUT | spectrogram: vertical bands reveal broadband transients", loc="left", fontsize=11)
    return artist


def save_figure(fig, directory, name):
    for extension in ("png", "pdf"):
        target = directory / f"{name}.{extension}"
        fig.savefig(target, dpi=170)
        print(target)
    plt.close(fig)


def plot_input(pcm, rate, out, stem):
    duration = len(pcm) / rate
    fig, axes = plt.subplots(3, 1, figsize=(15, 8), sharex=True, layout="constrained")
    fig.suptitle(f"{stem} | measured WAV input only | {rate} Hz, {duration:.3f} s\n"
                 "Block-switching output requires the matching server CSV.", fontsize=14)
    draw_waveform(axes[0], pcm, rate, 0, duration)
    padded = np.pad(pcm, (0, (-len(pcm)) % SHORT)).reshape(-1, SHORT)
    rms = np.sqrt(np.mean(padded ** 2, axis=1))
    axes[1].plot((np.arange(len(rms)) + 0.5) * SHORT / rate,
                 20 * np.log10(np.maximum(rms, 1e-6)), color="#0f766e", lw=0.9)
    axes[1].set_ylabel("Input RMS (dBFS)")
    axes[1].set_ylim(-120, 2)
    axes[1].set_title("Input level in 128-sample analysis intervals; display floor = -120 dBFS", loc="left", fontsize=11)
    spectrogram = draw_spectrogram(axes[2], pcm, rate, 0, duration)
    fig.colorbar(spectrogram, ax=axes, pad=0.015, shrink=0.4, label="PSD (dB / Hz)")
    axes[-1].set_xlabel("WAV sample time (s)")
    axes[-1].set_xlim(0, duration)
    for ax in axes:
        ax.grid(axis="x", alpha=0.18)
    save_figure(fig, out, f"{stem}_input")


def plot_io(pcm, rate, rows, start, end, out, name, title):
    count = len(rows)
    edges = np.arange(count + 1) * FRAME / rate
    centers = (edges[:-1] + edges[1:]) / 2
    sequences = np.array([r["lastWindowSequence"] for r in rows])
    shapes = np.array([r["windowShape"] for r in rows])
    attacks = np.array([r["attack"] for r in rows], dtype=bool)
    indices = np.array([r["attackIndex"] for r in rows])
    attack_time = (np.arange(count) * FRAME + (indices + 0.5) * SHORT) / rate
    energies = np.array([[r[f"windowNrgF_current{i}"] for i in range(8)] for r in rows], dtype=float)
    energy_time = (np.arange(count * 8) + 0.5) * SHORT / rate
    acc = np.array([r["accWindowNrg"] for r in rows], dtype=float)
    fig, axes = plt.subplots(7, 1, figsize=(16, 15), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1.8, 1.8, 1, 1.2, 0.7, 1.2]},
                             layout="constrained")
    fig.suptitle(title + "\nFDK output: after_sync; all lanes aligned to analyzed WAV frames", fontsize=14)
    draw_waveform(axes[0], pcm, rate, start, end)
    spectrogram = draw_spectrogram(axes[1], pcm, rate, start, end)
    fig.colorbar(spectrogram, ax=axes, pad=0.015, shrink=0.25, label="PSD (dB / Hz)")
    axes[2].plot(energy_time, 10 * np.log10(np.maximum(energies.ravel() / Q31, 1e-12)),
                 color="#0f766e", lw=0.8, label="HP energy / sub-window")
    axes[2].plot(edges[1:], 10 * np.log10(np.maximum(acc / Q31, 1e-12)),
                 color="#9333ea", ls=":", lw=1, marker=".", ms=2,
                 label="accWindowNrg: end-of-frame snapshots")
    axes[2].set_ylabel("Energy\n(dB re Q31 unit)")
    axes[2].set_ylim(-120, 3)
    axes[2].legend(loc="upper right", ncol=2, fontsize=9)
    axes[2].set_title("3. ANALYSIS | high-pass energy and accumulated background; display floor = -120 dB", loc="left", fontsize=11)
    # accWindowNrg is an end-of-frame state, not the threshold at each sub-window.
    axes[3].scatter(attack_time[attacks], indices[attacks], marker="v", s=28,
                    color="#dc2626", zorder=4)
    axes[3].set_ylim(-0.6, 7.6)
    axes[3].set_yticks([0, 2, 4, 6, 7])
    axes[3].set_ylabel("attackIndex\n(attack = 1 only)")
    axes[3].set_title("4. OUTPUT | attack flag/index; markers at sub-window centers, not exact onset samples", loc="left", fontsize=11)
    axes[4].stairs(sequences, edges, color="#334155", linewidth=1)
    axes[4].scatter(centers, sequences, c=[COLORS[v] for v in sequences], s=8, zorder=3)
    axes[4].set_ylim(-0.4, 3.4)
    axes[4].set_yticks(range(4), SEQUENCES)
    axes[4].set_ylabel("Sequence")
    axes[4].set_title("5. OUTPUT | window transitions: LONG / START / SHORT / STOP", loc="left", fontsize=11)
    axes[5].stairs(shapes, edges, color="#9333ea", linewidth=1.2)
    axes[5].set_ylim(-0.3, 1.3)
    axes[5].set_yticks([0, 1], ["SINE", "KBD"])
    axes[5].set_ylabel("Shape")
    axes[5].set_title("6. OUTPUT | window shape", loc="left", fontsize=11)
    groups = np.full((8, count), np.nan)
    for frame, row in enumerate(rows):
        if row["lastWindowSequence"] == 2:
            offset = 0
            for group in range(row["noOfGroups"]):
                length = row[f"groupLen{group}"]
                groups[offset:offset + length, frame] = group + 1
                offset += length
    cmap = ListedColormap(["#2563eb", "#d97706", "#16a34a", "#9333ea"])
    cmap.set_bad("#e5e7eb")
    axes[6].pcolormesh(edges, np.arange(9) - 0.5, np.ma.masked_invalid(groups),
                       cmap=cmap, norm=BoundaryNorm(np.arange(0.5, 5.5), 4), shading="flat",
                       rasterized=True)
    axes[6].set_yticks(range(8))
    axes[6].set_ylabel("Short-window\nindex (0..7)")
    axes[6].set_title("7. OUTPUT | grouping: blue=G0, orange=G1, green=G2, purple=G3; gray=non-SHORT", loc="left", fontsize=11)
    axes[6].invert_yaxis()
    for ax in axes:
        ax.set_xlim(start, end)
        ax.grid(axis="x", color="#64748b", alpha=0.18)
    # Same pale red bands connect SHORT decisions to the input and attack lanes.
    boundaries = np.r_[0, np.flatnonzero(np.diff(sequences)) + 1, count]
    for first, last in zip(boundaries[:-1], boundaries[1:]):
        if sequences[first] == 2:
            for ax in (axes[0], axes[2], axes[3]):
                ax.axvspan(edges[first], edges[last], color=COLORS[2], alpha=0.07)
    axes[-1].set_xlabel("Analyzed WAV frame time (s); control timestamps are not MDCT output timestamps")
    save_figure(fig, out, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", type=Path, required=True)
    parser.add_argument("--csv", type=Path, help="CSV generated by probe_block_switch --csv")
    parser.add_argument("--input-only", action="store_true", help="Plot WAV without claiming FDK output")
    parser.add_argument("--out", type=Path, default=Path("my_workspace/block_switch/out/plots"))
    parser.add_argument("--zoom", nargs=2, type=float, metavar=("START_S", "END_S"))
    args = parser.parse_args()
    if not args.csv and not args.input_only:
        parser.error("Supply --csv for real FDK output, or --input-only for a WAV-only preview.")
    if args.csv and args.input_only:
        parser.error("Select --csv or --input-only.")
    pcm, rate = read_wav(args.wav)
    rows = read_trace(args.csv, len(pcm)) if args.csv else None
    duration = len(pcm) / rate
    covered = min(duration, len(rows) * FRAME / rate) if rows else duration
    if args.zoom and not 0 <= args.zoom[0] < args.zoom[1] <= covered:
        parser.error(f"--zoom must lie within 0..{covered:.6f} seconds.")
    args.out.mkdir(parents=True, exist_ok=True)
    if rows is None:
        plot_input(pcm, rate, args.out, args.wav.stem)
        return
    plot_io(pcm, rate, rows, 0, covered, args.out, f"{args.wav.stem}_overview",
            f"{args.wav.name} | input and block switching | {len(rows)} frames, {covered:.3f} s")
    if args.zoom:
        start, end = args.zoom
    else:
        # Skip startup when possible; focus on the first later attack.
        events = [r["frame"] * FRAME / rate for r in rows if r["attack"]]
        center = next((t for t in events if t >= 0.25), events[0] if events else covered / 2)
        start, end = max(0, center - 0.12), min(covered, center + 0.30)
    plot_io(pcm, rate, rows, start, end, args.out, f"{args.wav.stem}_zoom",
            f"{args.wav.name} | transient detail | {start:.3f}..{end:.3f} s")
    summary = {"wav": str(args.wav), "csv": str(args.csv), "phase": "after_sync",
               "sample_rate": rate, "wav_samples": len(pcm), "wav_duration_s": duration,
               "frames": len(rows), "covered_duration_s": covered,
               "attack_frames": sum(r["attack"] for r in rows),
               "window_frames": {label: sum(r["lastWindowSequence"] == i for r in rows)
                                 for i, label in enumerate(SEQUENCES)},
               "zoom_s": [start, end],
               "note": "CSV length validated against WAV; sample identity is not verifiable without an input hash."}
    target = args.out / f"{args.wav.stem}_summary.json"
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, wave.Error, KeyError) as exc:
        sys.exit(f"ERROR: {exc}")
