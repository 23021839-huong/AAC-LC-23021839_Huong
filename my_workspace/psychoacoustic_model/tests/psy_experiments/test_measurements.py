import importlib.util
import unittest
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('psy_metrics',ROOT/'my_workspace/psychoacoustic_model/experiments/psy/scripts/measure_distortion.py')
metrics=importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)

class MetricsTests(unittest.TestCase):
    def test_nrmse_energy_definition(self):
        r=metrics.distortion_metrics(np.array([1.,-1.]),np.array([.9,-.9]))
        self.assertAlmostEqual(r['nrmse_percent'],10.)
        self.assertAlmostEqual(r['snr_db'],20.)
        self.assertAlmostEqual(r['mse'],.01)
    def test_silence_is_missing_not_zero_distortion(self):
        r=metrics.distortion_metrics(np.zeros(10),np.zeros(10))
        self.assertIsNone(r['nrmse_percent'])
    def test_mismatched_shapes_rejected(self):
        with self.assertRaises(ValueError):metrics.distortion_metrics(np.ones(5),np.ones(6))
    def test_alignment_recovers_broad_unique_low_frequency_peak(self):
        # A three-sample neighbor on a broad peak is not a distinct delay hypothesis.
        rate=48000; count=96000; rng=np.random.default_rng(75)
        bins=np.fft.rfft(rng.standard_normal(count))
        bins[np.fft.rfftfreq(count,1/rate)>150]=0
        x=np.fft.irfft(bins,n=count)
        y=np.concatenate((np.zeros(2048),x,np.zeros(512)))
        try:
            aligned,metadata=metrics.align_pcm(x,y,2048)
        except ValueError as error:
            self.fail('Known unique delay rejected for a broad correlation peak: '+str(error))
        self.assertEqual(metadata['alignment_delay_samples'],2048)
        np.testing.assert_allclose(aligned[:,0],x)
    def test_alignment_still_rejects_distinct_equally_strong_periodic_peaks(self):
        x=.3*np.sin(2*np.pi*200*np.arange(96000)/48000)
        y=np.concatenate((np.zeros(2048),x,np.zeros(512)))
        with self.assertRaises(ValueError):metrics.align_pcm(x,y,2048)

if __name__=='__main__':unittest.main()
