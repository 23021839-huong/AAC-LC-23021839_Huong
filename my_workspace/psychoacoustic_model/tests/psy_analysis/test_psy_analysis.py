import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location('psy_trace_data', ROOT / 'my_workspace/psychoacoustic_model/tools/psy_trace_data.py')
DATA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DATA)


class TraceTests(unittest.TestCase):
    def record(self, **changes):
        r = dict(frame=10, channel=0, window=0, block_type=0, window_shape=0,
                 sample_rate=48000, frame_length=1024, window_length=1024,
                 stage='energy', name='scaled.energy', count=2, index=0,
                 fraction_bits=31, exponent=8, unit='pcm_squared', raw=[0, 1073741824])
        r.update(changes)
        return r

    def test_fixed_point_reconstruction(self):
        self.assertEqual(DATA.reconstruct(self.record()).tolist(), [0, 128])

    def test_log_sentinel_is_not_positive_energy(self):
        r = self.record(unit='ld64', exponent=4, raw=[-2147483648, 0])
        self.assertEqual(DATA.reconstruct(r).tolist(), [0, 16])

    def test_count_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'count'):
            DATA.validate_record(self.record(count=3))

    def test_missing_exponent_rejected(self):
        r = self.record()
        del r['exponent']
        with self.assertRaises(ValueError):
            DATA.validate_record(r)

    def test_int32_bounds_rejected(self):
        with self.assertRaises(ValueError):
            DATA.validate_record(self.record(raw=[0, 2147483648]))

    def test_nonmonotonic_offsets_rejected(self):
        with self.assertRaisesRegex(ValueError, 'offset'):
            DATA.validate_record(self.record(stage='sfb', name='offsets', unit='integer',
                                            fraction_bits=0, exponent=0, count=3, raw=[0, 4, 3]))

    def test_truncated_json_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'trace.jsonl'
            p.write_text(json.dumps(self.record()) + '\n{', encoding='utf-8')
            with self.assertRaises(ValueError):
                DATA.load_trace(p)

    def test_short_output_padding_is_opaque(self):
        r = self.record(block_type=2, window_length=128, stage='output', name='offsets',
                        unit='integer', fraction_bits=0, exponent=0,
                        count=5, raw=[0, 4, 0, 0, 1024], valid_indices=[0, 1, 4])
        DATA.validate_record(r)
        self.assertTrue(__import__('math').isnan(DATA.reconstruct(r)[2]))

    def test_invalid_native_mask_rejected(self):
        with self.assertRaisesRegex(ValueError, 'valid_indices'):
            DATA.validate_record(self.record(valid_indices=[0, 9]))


if __name__ == '__main__':
    unittest.main()
