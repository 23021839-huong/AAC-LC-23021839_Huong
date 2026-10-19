"""Real kernel and AAC round-trip contracts, no mocked FFT."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[4]


def fixture(path):
    values = []
    state = 321
    for n in range(48000):
        state = (1664525 * state + 1013904223) & 0xffffffff
        values.append(((state >> 16) - 32768) // 2 if n > 4000 and n % 12000 < 2500 else 0)
    with wave.open(str(path), "wb") as f:
        f.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        f.writeframes(struct.pack("<" + "h" * len(values), *values))


class FFTTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_actual_kernel_vectors_and_preprocessing_pass_independent_dft(self):
        folder = self.root / "validation"
        p = subprocess.run([str(ARGS.validator), "--output-dir", str(folder),
                            "--pre-long", str(ARGS.pre_long), "--pre-short", str(ARGS.pre_short)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        summary = json.loads((folder / "fft_validation.json").read_text())
        self.assertTrue(summary["complete"])
        self.assertTrue(summary["passed"])
        self.assertEqual(summary["supported_lengths"], [64, 512])
        self.assertGreaterEqual(len(summary["cases"]), 20)
        names = {r["case"] for r in summary["cases"]}
        self.assertTrue({"zero", "impulse", "complex_tone", "random_0", "full_scale", "pre_long", "pre_short_0"} <= names)
        for case in summary["cases"]:
            length = case["length"]
            self.assertEqual(case["exponent_difference"], 0)
            self.assertEqual(case["radix2_butterflies"], length // 2 * (6 if length == 64 else 9))
            self.assertEqual(case["radix4_butterflies"], 0)
            self.assertEqual(case["saturation_count"], 0)
            self.assertLessEqual(case["max_abs_error"], 64)
            self.assertLessEqual(case["direct_dft_max_error"], case["direct_dft_error_bound"])
        with (folder / "fft_comparison.csv").open() as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            if row["case"] == "zero":
                self.assertEqual(int(row["radix2_real"]), 0)
                self.assertEqual(int(row["radix2_imag"]), 0)
            if row["case"] == "impulse":
                self.assertEqual(int(row["radix2_real"]), 4194304 if int(row["length"]) == 64 else 524288)
                self.assertEqual(int(row["radix2_imag"]), 0)
        self.assertTrue((folder / "fft_original.txt").exists())
        self.assertTrue((folder / "fft_radix2.txt").exists())

    def test_incomplete_pre_input_rejected_before_validation_success(self):
        short = self.root / "bad_pre.txt"
        short.write_text("0 123 456\n")
        folder = self.root / "validation"
        p = subprocess.run([str(ARGS.validator), "--output-dir", str(folder),
                            "--pre-long", str(short), "--pre-short", str(ARGS.pre_short)], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        if (folder / "fft_validation.json").exists():
            self.assertFalse(json.loads((folder / "fft_validation.json").read_text()).get("passed", False))

    def test_real_codec_modes_fix_windows_and_separate_profiling(self):
        wav = self.root / "attack.wav"
        fixture(wav)
        bytes_by_mode = {}
        traces = []
        for mode in ("ORIGINAL_FFT", "RADIX2_ONLY"):
            folder = self.root / mode
            p = subprocess.run([str(ARGS.runner), "--input", str(wav), "--output-dir", str(folder),
                                "--mode", mode, "--runs", "2", "--profile-runs", "2", "--bitrate", "64000"],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
            meta = json.loads((folder / "run_metadata.json").read_text())
            self.assertTrue(meta["complete"])
            self.assertEqual(meta["window_mode"], "SINE_ONLY")
            self.assertEqual(meta["target_bitrate_bps"], 64000)
            self.assertEqual(len(meta["encoding_time_ms"]), 2)
            self.assertEqual(len(meta["profile_runs"]), 2)
            self.assertFalse(meta["profiling_in_main_benchmark"])
            self.assertTrue(meta["profile_bitstream_equals_unprofiled"])
            with (folder / "frame_trace.csv").open() as f:
                rows = list(csv.DictReader(f))
            self.assertTrue(all(int(r["window_shape"]) == 0 for r in rows))
            count512 = sum(r["window_sequence_id"] != "2" for r in rows)
            count64 = 8 * sum(r["window_sequence_id"] == "2" for r in rows)
            self.assertGreater(count64, 0)
            for profile in meta["profile_runs"]:
                self.assertEqual(profile["calls_64"], count64)
                self.assertEqual(profile["calls_512"], count512)
                self.assertEqual(profile["unexpected_lengths"], 0)
                self.assertEqual(profile["saturations"], 0)
                self.assertEqual(profile["extra_prescale_calls"], 0)
                self.assertGreater(profile["fft_time_ms"], 0)
                self.assertEqual(profile["radix4_butterflies"] == 0, mode == "RADIX2_ONLY")
            traces.append([r["window_sequence_id"] for r in rows])
            bytes_by_mode[mode] = (folder / "encoded.aac").read_bytes()
            with wave.open(str(folder / "decoded.wav")) as f:
                self.assertEqual(f.getframerate(), 48000)
                self.assertGreaterEqual(f.getnframes(), 50048)
        self.assertEqual(traces[0], traces[1])
        # This design deliberately retains the original truncation schedule.
        self.assertEqual(bytes_by_mode["ORIGINAL_FFT"], bytes_by_mode["RADIX2_ONLY"])

    def test_invalid_fft_mode_is_not_silently_original(self):
        folder = self.root / "bad"
        p = subprocess.run([str(ARGS.runner), "--output-dir", str(folder), "--mode", "RADIX4_ONLY"],
                           capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse((folder / "run_metadata.json").exists())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--pre-long", type=Path, default=ROOT / 'my_workspace/window_mdct/output/02_preprocessing.txt')
    parser.add_argument("--pre-short", type=Path, default=ROOT / 'my_workspace/window_mdct/output/mdct_short_example/02_preprocessing.txt')
    ARGS, rest = parser.parse_known_args()
    ARGS.validator = ARGS.validator.resolve()
    ARGS.runner = ARGS.runner.resolve()
    unittest.main(argv=[__file__] + rest)
