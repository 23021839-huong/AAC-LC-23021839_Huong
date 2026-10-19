#!/usr/bin/env python3
"""Generate a deterministic mono PCM16 corpus for QC Step 0 profiling."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import random
import sys
import wave
from array import array
from pathlib import Path
from typing import Callable


SampleFunction = Callable[[int, float], float]


def clamp_pcm16(value: float) -> int:
    return max(-32768, min(32767, int(round(value * 32767.0))))


def write_wav(path: Path, sample_rate: int, samples: list[int]) -> None:
    payload = array("h", samples)
    if sys.byteorder != "little":
        payload.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(payload.tobytes())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_cases(seed: int) -> list[tuple[str, SampleFunction]]:
    noise_rng = random.Random(seed)
    transient_rng = random.Random(seed + 1)

    def silence(_index: int, _time_s: float) -> float:
        return 0.0

    def dc(_index: int, _time_s: float) -> float:
        return 0.25

    def impulse(index: int, _time_s: float) -> float:
        return 0.95 if index % 8192 == 0 else 0.0

    def sine(_index: int, time_s: float) -> float:
        return 0.75 * math.sin(2.0 * math.pi * 1000.0 * time_s)

    def sweep(_index: int, time_s: float) -> float:
        start_hz = 40.0
        end_hz = 20000.0
        sweep_seconds = 8.0
        ratio = end_hz / start_hz
        phase = (
            2.0
            * math.pi
            * start_hz
            * sweep_seconds
            / math.log(ratio)
            * (ratio ** ((time_s % sweep_seconds) / sweep_seconds) - 1.0)
        )
        return 0.7 * math.sin(phase)

    def deterministic_noise(_index: int, _time_s: float) -> float:
        return 0.55 * (2.0 * noise_rng.random() - 1.0)

    def near_clip(_index: int, time_s: float) -> float:
        signal = math.sin(2.0 * math.pi * 997.0 * time_s)
        return 0.995 if signal >= 0.0 else -0.995

    def transient(index: int, time_s: float) -> float:
        position = index % 12000
        if position >= 1800:
            return 0.03 * math.sin(2.0 * math.pi * 220.0 * time_s)
        envelope = math.exp(-position / 260.0)
        return 0.92 * envelope * (2.0 * transient_rng.random() - 1.0)

    return [
        ("silence", silence),
        ("dc", dc),
        ("impulse", impulse),
        ("sine_1k", sine),
        ("sweep", sweep),
        ("deterministic_noise", deterministic_noise),
        ("near_clip", near_clip),
        ("transient", transient),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--seed", type=int, default=20260921)
    args = parser.parse_args()

    if args.sample_rate <= 0 or args.duration <= 0.0:
        parser.error("sample rate and duration must be positive")

    args.output.mkdir(parents=True, exist_ok=True)
    sample_count = int(round(args.sample_rate * args.duration))
    rows: list[dict[str, object]] = []
    for name, function in build_cases(args.seed):
        samples = [
            clamp_pcm16(function(index, index / args.sample_rate))
            for index in range(sample_count)
        ]
        path = args.output / f"{name}_mono_{args.sample_rate}_pcm16.wav"
        write_wav(path, args.sample_rate, samples)
        rows.append(
            {
                "case": name,
                "path": path.name,
                "sample_rate_hz": args.sample_rate,
                "channels": 1,
                "sample_format": "PCM16",
                "samples_per_channel": sample_count,
                "duration_s": f"{sample_count / args.sample_rate:.6f}",
                "seed": args.seed,
                "sha256": sha256(path),
            }
        )

    manifest = args.output / "corpus_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Generated {len(rows)} deterministic WAV files in {args.output}")


if __name__ == "__main__":
    main()
