import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_native_fft import fixture
ROOT=Path(__file__).resolve().parents[4]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.wav=self.root/'attack.wav';fixture(self.wav)

    def tearDown(self):
        self.tmp.cleanup()

    def run_pipeline(self, pre_long=None):
        return subprocess.run([sys.executable,str(ROOT/'my_workspace/window_mdct/experiments/fft/scripts/run_fft_experiments.py'),
            '--input',str(self.wav),'--output-dir',str(self.root/'results'),
            '--binary',str(ARGS.runner),'--validator',str(ARGS.validator),'--skip-build','--no-plots',
            '--pre-long',str(pre_long or ROOT/'my_workspace/window_mdct/output/02_preprocessing.txt'),
            '--pre-short',str(ROOT/'my_workspace/window_mdct/output/mdct_short_example/02_preprocessing.txt'),
            '--bitrate','64000','--runs','10'],capture_output=True,text=True)

    def test_measured_csv_and_profile_reconcile_with_native_counts(self):
        p=self.run_pipeline();self.assertEqual(p.returncode,0,p.stderr+p.stdout)
        root=self.root/'results'
        status=json.loads((root/'results/pipeline_status.json').read_text())
        self.assertTrue(status['complete']);self.assertTrue(status['fft_validation_passed'])
        with (root/'results/fft_window_comparison.csv').open() as f:rows=list(csv.DictReader(f))
        with (root/'results/fft_runs.csv').open() as f:runs=list(csv.DictReader(f))
        with (root/'results/fft_profile.csv').open() as f:profiles=list(csv.DictReader(f))
        self.assertEqual(len(rows),2);self.assertEqual(len(runs),20);self.assertEqual(len(profiles),40)
        for row in rows:
            self.assertEqual(row['status'],'ok');self.assertEqual(row['compared_samples_per_channel'],'48000')
            self.assertGreater(float(row['fft_time_mean_ms']),0);self.assertEqual(row['window_mode'],'SINE_ONLY')
            self.assertEqual(row['bitstream_shape_verified'],'True');self.assertEqual(row['window_sequences_equal'],'True')
        self.assertEqual(rows[0]['aac_sha256'],rows[1]['aac_sha256'])
        self.assertEqual((root/'encoded/original.aac').read_bytes(),(root/'encoded/radix2.aac').read_bytes())

    def test_validation_failure_prevents_encoding_and_clears_success(self):
        bad=self.root/'bad_pre.txt';bad.write_text('0 1 2\n')
        result=self.root/'results/results';result.mkdir(parents=True)
        (result/'pipeline_status.json').write_text('{"complete":true,"fft_validation_passed":true}')
        p=self.run_pipeline(bad);self.assertNotEqual(p.returncode,0)
        status=json.loads((result/'pipeline_status.json').read_text())
        self.assertFalse(status['complete']);self.assertFalse(status['fft_validation_passed'])
        self.assertFalse((self.root/'results/encoded/radix2.aac').exists())
        with (result/'fft_window_comparison.csv').open() as f:rows=list(csv.DictReader(f))
        self.assertTrue(all(r['status']=='error' and r['mse']=='' for r in rows))

    def test_publication_failure_after_measurement_is_not_success(self):
        (self.root/'results/encoded/original.aac/encoded.aac').mkdir(parents=True)
        p=self.run_pipeline();self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertTrue((self.root/'results/results/pipeline_status.json').exists(),p.stderr)
        status=json.loads((self.root/'results/results/pipeline_status.json').read_text())
        self.assertFalse(status['complete'])
        with (self.root/'results/results/fft_window_comparison.csv').open() as f:rows=list(csv.DictReader(f))
        self.assertEqual(rows[0]['status'],'error')

    def test_exact_output_filename_cannot_be_an_existing_directory(self):
        # copy2 would silently copy inside this directory instead of publishing the promised file.
        (self.root/'results/encoded/original.aac').mkdir(parents=True)
        p=self.run_pipeline();self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
        status=json.loads((self.root/'results/results/pipeline_status.json').read_text())
        self.assertFalse(status['complete'])
        with (self.root/'results/results/fft_window_comparison.csv').open() as f:rows=list(csv.DictReader(f))
        self.assertEqual(rows[0]['status'],'error')
        self.assertIn('directory',rows[0]['error'].lower())
        self.assertFalse((self.root/'results/encoded/original.aac/encoded.aac').exists())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runner',type=Path,required=True);parser.add_argument('--validator',type=Path,required=True)
    ARGS,rest=parser.parse_known_args();ARGS.runner=ARGS.runner.resolve();ARGS.validator=ARGS.validator.resolve()
    unittest.main(argv=[__file__]+rest)
