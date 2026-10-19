"""Scientific checks for pitch conversion and periodic-signal sample alignment."""
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'my_workspace/psychoacoustic_model/experiments/psy/scripts'))
from measure_distortion import align_pcm


class InputSignalTests(unittest.TestCase):
    def preparer(self):
        path = ROOT / 'my_workspace/psychoacoustic_model/experiments/psy/scripts/prepare_psy_inputs.py'
        self.assertTrue(path.exists(), 'Input-preparation feature is missing')
        spec = importlib.util.spec_from_file_location('input_preparer', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_pitch_rate_conversion_moves_220_hz_to_330_hz(self):
        module = self.preparer()
        fs = 48000
        x = np.sin(2 * np.pi * 220 * np.arange(fs) / fs)
        y = module.raise_pitch_by_rate(x, 3, 2)
        f = np.fft.rfftfreq(len(y), 1 / fs)
        peak = f[np.argmax(np.abs(np.fft.rfft(y * np.hanning(len(y)))))]
        self.assertAlmostEqual(peak, 330, delta=2)
        self.assertEqual(len(y), fs * 2 // 3)

    def test_stable_bass_can_align_all_samples_with_unique_marker(self):
        module = self.preparer()
        x = module.make_low_stable(48000, 6 * 48000, 20261013)
        delay = 2048
        decoded = np.concatenate((np.zeros(delay), x, np.zeros(512)))
        aligned, metadata = align_pcm(x, decoded, delay)
        self.assertEqual(metadata['alignment_delay_samples'], delay)
        self.assertEqual(metadata['compared_samples_per_channel'], len(x))
        np.testing.assert_allclose(aligned[:, 0], x)


if __name__ == '__main__':
    unittest.main()
