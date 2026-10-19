"""Hand-calculated fixtures pin bitrate, alignment and distortion semantics."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[4]


class MeasurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'my_workspace/window_mdct/experiments/scripts/measure_distortion.py'
        if not path.exists():
            cls.module = None
        else:
            spec = importlib.util.spec_from_file_location("measure_distortion", path)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)

    def module_ready(self):
        self.assertIsNotNone(self.module, "Full-file measurement module not implemented yet")
        return self.module

    def test_metrics_use_float_before_square(self):
        m = self.module_ready()
        result = m.distortion_metrics(np.array([-32768, 32767], dtype=np.int16),
                                      np.array([0, 0], dtype=np.int16))
        self.assertAlmostEqual(result["mse"], 0.9999694828875363, places=13)
        self.assertAlmostEqual(result["snr_db"], 0.0)
        self.assertAlmostEqual(result["nrmse_percent"], 100.0)

    def test_known_error_matches_manual_metrics(self):
        m = self.module_ready()
        result = m.distortion_metrics(np.array([0.5, -0.5]), np.array([0.25, -0.25]))
        self.assertAlmostEqual(result["mse"], 0.0625)
        self.assertAlmostEqual(result["snr_db"], 6.020599913279624)
        self.assertAlmostEqual(result["nrmse_percent"], 50.0)

    def test_alignment_recovers_delay_without_changing_gain(self):
        m = self.module_ready()
        rng = np.random.default_rng(321)
        original = rng.uniform(-0.8, 0.8, (12000, 2))
        decoded = np.vstack([np.zeros((137, 2)), original * 0.8, np.zeros((60, 2))])
        aligned, info = m.align_pcm(original, decoded, expected_delay=130, search_radius=32)
        self.assertEqual(info["alignment_delay_samples"], 137)
        self.assertEqual(info["compared_samples_per_channel"], 12000)
        self.assertEqual(info["trailing_padding_samples"], 60)
        self.assertAlmostEqual(m.distortion_metrics(original, aligned)["nrmse_percent"], 20.0)

    def test_zero_energy_is_explicitly_undefined(self):
        m = self.module_ready()
        result = m.distortion_metrics(np.zeros(128), np.ones(128) * 0.1)
        self.assertIsNone(result["snr_db"])
        self.assertIsNone(result["nrmse_percent"])
        self.assertEqual(result["metric_status"], "zero_reference_energy")
        with self.assertRaisesRegex(ValueError, "energy"):
            m.align_pcm(np.zeros((128, 1)), np.zeros((256, 1)), 0, 32)

    def test_unrelated_audio_rejected_as_unreliable(self):
        m = self.module_ready()
        rng = np.random.default_rng(42)
        with self.assertRaisesRegex(ValueError, "reliable"):
            m.align_pcm(rng.normal(size=(8192, 1)), rng.normal(size=(9000, 1)), 50, 100)

    def test_insufficient_tail_cannot_silently_drop_original_samples(self):
        m = self.module_ready()
        rng = np.random.default_rng(2)
        original = rng.normal(size=(8192, 1))
        decoded = np.vstack([np.zeros((100, 1)), original[:-20]])
        with self.assertRaisesRegex(ValueError, "cover"):
            m.align_pcm(original, decoded, 100, 8)

    def test_adts_duration_and_header_overhead(self):
        m = self.module_ready()
        # Two AAC-LC mono 48k ADTS packets, sizes 100 and 120 bytes.
        def packet(size):
            return bytes([0xff, 0xf1, 0x4c, 0x40 | (size >> 11), (size >> 3) & 255,
                          ((size & 7) << 5) | 31, 0xfc]) + bytes(size - 7)
        result = m.inspect_adts(packet(100) + packet(120))
        self.assertEqual(result["adts_frames"], 2)
        self.assertEqual(result["header_bytes"], 14)
        self.assertEqual(result["payload_bytes"], 206)
        self.assertAlmostEqual(result["coded_duration_seconds"], 2048 / 48000)
        self.assertAlmostEqual(result["actual_bitrate_kbps"], 41.25)
        self.assertAlmostEqual(result["payload_bitrate_kbps"], 38.625)
        with self.assertRaisesRegex(ValueError, "truncated"):
            m.inspect_adts(packet(100)[:-1])


if __name__ == "__main__":
    unittest.main()
