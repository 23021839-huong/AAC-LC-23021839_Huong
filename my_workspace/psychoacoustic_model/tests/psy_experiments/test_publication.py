"""Failed campaigns must not expose old or partially committed measurements."""
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'my_workspace/psychoacoustic_model/experiments/psy/scripts'))
import run_psy_experiments as pipeline


class PublicationTests(unittest.TestCase):
    def arguments(self, folder):
        return ['--input', str(ROOT / 'my_workspace/INPUT/data/abc_votay.wav'), '--output-dir', str(folder),
                '--skip-build', '--no-plots', '--runs', '10', '--profile-runs', '1']

    def test_preflight_failure_invalidates_owned_publications(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            old = [folder / 'encoded/exp01_both_on.aac', folder / 'decoded/exp01_decoded.wav',
                   folder / 'logs/exp01_psy_trace.csv', folder / 'logs/exp01_distortion_alignment.json',
                   folder / 'plots/psy_overview.png', folder / 'results/analysis.md']
            for path in old:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('old successful campaign')
            (folder / 'results/psy_comparison.csv').write_text('status\nPASS\n')
            (folder / 'results/psy_profile.csv').write_text('status\nPASS\n')
            sentinel = folder / 'encoded/unrelated.aac'
            sentinel.write_text('keep')
            code = pipeline.main(self.arguments(folder) + ['--build-dir', str(folder / 'missing'),
                                                          '--baseline-build-dir', str(folder / 'missing2')])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads((folder / 'results/pipeline_status.json').read_text())['complete'])
            self.assertTrue(all(not path.exists() for path in old))
            self.assertTrue(sentinel.exists())
            with (folder / 'results/psy_comparison.csv').open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(r['status'] == 'NOT_RUN' and not r['aac_size_bytes'] for r in rows))
            with (folder / 'results/psy_profile.csv').open() as f:
                self.assertEqual(list(csv.DictReader(f)), [])

    def test_copy_failure_has_no_partial_files_or_pass_measurements(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            real_copy = shutil.copy2

            def fail_decoded(source, destination, *args, **kwargs):
                if Path(source).name == 'decoded.wav':
                    raise OSError('simulated publication failure')
                return real_copy(source, destination, *args, **kwargs)

            with patch.object(pipeline.shutil, 'copy2', side_effect=fail_decoded):
                self.assertEqual(pipeline.main(self.arguments(folder)), 1)
            with (folder / 'results/psy_comparison.csv').open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(r['status'] == 'ERROR' for r in rows))
            for r in rows:
                for field in ('aac_size_bytes', 'encoding_time_mean_ms', 'mse', 'distortion_rate_percent'):
                    self.assertEqual(r[field], '')
            for filename in ('psy_runs.csv', 'psy_profile.csv'):
                with (folder / 'results' / filename).open() as f:
                    self.assertEqual(list(csv.DictReader(f)), [])
            self.assertEqual(list((folder / 'encoded').glob('*.aac')), [])
            self.assertEqual(list((folder / 'decoded').glob('*.wav')), [])


if __name__ == '__main__':
    unittest.main()
