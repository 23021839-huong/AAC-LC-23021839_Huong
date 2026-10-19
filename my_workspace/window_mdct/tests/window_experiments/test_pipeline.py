import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_native_window import fixture

ROOT = Path(__file__).resolve().parents[4]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.wav = self.path / "attacks.wav"
        fixture(self.wav)

    def tearDown(self):
        self.tmp.cleanup()

    def run_pipeline(self, binary):
        return subprocess.run([sys.executable, str(ROOT / 'my_workspace/window_mdct/experiments/scripts/run_window_experiments.py'),
                               "--binary", str(binary), "--input", str(self.wav),
                               "--output-dir", str(self.path / "experiment"), "--runs", "5", "--no-plots"],
                              capture_output=True, text=True)

    def test_real_four_mode_csv_covers_all_input_samples(self):
        p = self.run_pipeline(BINARY)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        results = self.path / "experiment/results"
        status = json.loads((results / "pipeline_status.json").read_text())
        self.assertTrue(status["complete"])
        with (results / "window_comparison.csv").open() as f:
            rows = list(csv.DictReader(f))
        with (results / "window_runs.csv").open() as f:
            runs = list(csv.DictReader(f))
        self.assertEqual(len(rows), 4)
        self.assertEqual(len(runs), 20)
        for row in rows:
            self.assertEqual(row["status"], "ok")
            self.assertEqual(int(row["compared_samples_per_channel"]), 48000)
            self.assertEqual(int(row["alignment_delay_samples"]), 2048)
            self.assertEqual(row["window_sequences_equal"], "True")
            self.assertGreater(float(row["snr_db"]), 0)
            self.assertGreater(int(row["aac_size_bytes"]), 0)
            self.assertEqual(row["bitstream_shape_verified"], "True")

    def test_failed_encoder_produces_error_rows_without_fake_measurements(self):
        p = self.run_pipeline(self.path / "missing.exe")
        self.assertNotEqual(p.returncode, 0)
        results = self.path / "experiment/results"
        self.assertTrue((results / "window_comparison.csv").exists(), p.stderr)
        with (results / "window_comparison.csv").open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(row["status"], "error")
            self.assertEqual(row["mse"], "")
            self.assertEqual(row["encoding_time_mean_ms"], "")
            self.assertTrue(row["error"])
        self.assertFalse(json.loads((results / "pipeline_status.json").read_text())["complete"])

    def test_artifact_copy_failure_after_measurement_cannot_report_success(self):
        # Real filesystem failure, after valid encoding/metrics, without mocks.
        conflict = self.path / "experiment/encoded/exp01_sine_only.aac/encoded.aac"
        conflict.mkdir(parents=True)
        p = self.run_pipeline(BINARY)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        results = self.path / "experiment/results"
        with (results / "window_comparison.csv").open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["status"], "error")
        self.assertTrue(rows[0]["error"])
        status = json.loads((results / "pipeline_status.json").read_text())
        self.assertFalse(status["complete"])
        self.assertEqual(status["experiments"]["EXP01"]["status"], "error")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    args, rest = parser.parse_known_args()
    BINARY = Path(args.binary).resolve()
    unittest.main(argv=[__file__] + rest)
