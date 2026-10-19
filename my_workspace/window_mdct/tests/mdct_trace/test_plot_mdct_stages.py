import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

SCRIPT = Path(__file__).resolve().parents[4] / 'my_workspace/window_mdct/tools/plot_mdct_stages.py'


class PlotTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), 'The dump reader/plotting script does not exist yet')
        spec = importlib.util.spec_from_file_location('plot_mdct_stages', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def valid_old_dump(self, directory):
        d = Path(directory)
        meta = {'schema_version': 1, 'pcm_samples': 2048, 'data_fraction_bits': 31,
                'subtransforms': [{'L': 1024, 'M': 512, 'scalar_offset': 0,
                                  'exponents': {'postprocessing': {'effective': 12}}}]}
        (d / 'stage_metadata.json').write_text(json.dumps(meta))
        for name, count, width, value in [
            ('00_pcm_input.txt', 2048, 1, 0), ('01_window_fold.txt', 1024, 1, 0),
            ('02_preprocessing.txt', 512, 2, 0), ('03_fft.txt', 512, 2, 0),
            ('04_postprocessing.txt', 1024, 1, 0), ('05_mdct_output.txt', 1024, 1, 0),
            ('05_mdct_exponents.txt', 1024, 1, 12)]:
            (d / name).write_text(''.join(f'{i} ' + ' '.join([str(value)] * width) + '\n'
                                        for i in range(count)))

    def test_statistics_do_not_overflow_signed_fixed_point(self):
        s = self.module.statistics(np.array([-2147483648, 2147483647], dtype=np.int64))
        self.assertEqual(s['count'], 2)
        self.assertEqual(s['min'], -2147483648)
        self.assertEqual(s['max'], 2147483647)
        self.assertEqual(s['mean'], -0.5)
        self.assertAlmostEqual(s['rms'], 2147483647.5, places=5)

    def test_reconstruction_uses_exponent_per_coefficient(self):
        got = self.module.reconstruct(np.array([1073741824, -1073741824]), 31, np.array([2, 3]))
        np.testing.assert_array_equal(got, [2.0, -4.0])

    def test_noncontiguous_indices_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'bad.txt'
            f.write_text('0 12\n2 14\n')
            with self.assertRaisesRegex(ValueError, 'contiguous'):
                self.module.read_dump(f, 2, 2)

    def test_wrong_column_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'bad.txt'
            f.write_text('0 12\n1 14\n')
            with self.assertRaisesRegex(ValueError, 'columns'):
                self.module.read_dump(f, 3, 2)

    def test_partial_run_is_rejected_before_reading_old_dumps(self):
        with tempfile.TemporaryDirectory() as d:
            self.valid_old_dump(d)
            (Path(d) / 'run_status.json').write_text(json.dumps({'complete': False, 'mdct_debug': True}))
            with self.assertRaisesRegex(ValueError, 'complete'):
                self.module.load_trace(d)

    def test_latest_debug_off_run_is_not_presented_as_current_trace(self):
        with tempfile.TemporaryDirectory() as d:
            self.valid_old_dump(d)
            (Path(d) / 'run_status.json').write_text(json.dumps({'complete': True, 'mdct_debug': False}))
            with self.assertRaisesRegex(ValueError, 'MDCT_DEBUG=OFF'):
                self.module.load_trace(d)


if __name__ == '__main__':
    unittest.main()
