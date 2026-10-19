"""Integration: inputs are generated PCM, all surveyed outputs come from native FDK."""
import argparse
import hashlib
import importlib.util
import json
import math
import random
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'my_workspace/psychoacoustic_model/tools'))
from psy_trace_data import find, group_records, load_trace, validate

ARGS = None


def wav(path, rate, channels, kind):
    rng = random.Random(42)
    samples = []
    for i in range(rate):
        for ch in range(channels):
            if kind == 'silence':
                value = 0
            elif kind == 'transient':
                value = rng.randint(-18000, 18000) if rate//5 <= i < rate//5+rate//20 else 0
            elif kind == 'noise':
                value = rng.randint(-18000, 18000)
            else:
                value = int(12000 * math.sin(2*math.pi*(997+271*ch)*i/rate))
            samples.append(value)
    with wave.open(str(path), 'wb') as w:
        w.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
        w.writeframes(struct.pack('<%dh' % len(samples), *samples))


class NativeTests(unittest.TestCase):
    def test_native_vectors_and_bitstream_invariance(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            summary = []
            for kind, rate, channels, bitrate in (
                ('silence', 48000, 1, 64000), ('sine', 48000, 1, 32000),
                ('noise', 48000, 1, 32000), ('transient', 48000, 1, 48000),
                ('sine', 44100, 2, 96000), ('noise', 48000, 2, 64000)):
                name = f'{kind}_{rate}_{channels}_{bitrate}'
                source = base / (name + '.wav')
                wav(source, rate, channels, kind)
                outputs = []
                for mode, binary in (('debug', ARGS.debug), ('normal', ARGS.normal)):
                    output = base / (name + '_' + mode)
                    result = subprocess.run([str(binary), '--input', str(source), '--output-dir', str(output),
                                             '--frames', '0:18', '--channel', 'all', '--bitrate', str(bitrate)],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    outputs.append(output)
                self.assertEqual((outputs[0]/'encoded.aac').read_bytes(), (outputs[1]/'encoded.aac').read_bytes())
                self.assertFalse((outputs[1]/'native_trace.jsonl').exists())
                records = load_trace(outputs[0]/'native_trace.jsonl')
                report = validate(records)
                self.assertEqual(len(report['frames']), 18*channels)
                for rs in group_records(records).values():
                    spec = find(rs, 'output', 'spectrum')
                    if spec['block_type'] == 2:
                        active = find(rs, 'context', 'sfb_active')['raw'][0]
                        boundary = find(rs, 'context', 'offsets')['raw'][active]
                        if boundary < 128:
                            self.assertIn('valid_indices', spec)
                            invalid = set(range(1024))-set(spec['valid_indices'])
                            self.assertTrue(invalid)
                            self.assertTrue(all(spec['raw'][i] is None for i in invalid))
                    mask = find(rs, 'output', 'ms_mask')
                    if mask:
                        limit = find(rs, 'output', 'max_sfb_per_group')['raw'][0]
                        stride = find(rs, 'output', 'sfb_per_group')['raw'][0]
                        expected = [i for i in range(mask['count']) if i % stride < limit]
                        self.assertEqual(mask.get('valid_indices', list(range(mask['count']))), expected)
                if kind == 'silence':
                    self.assertTrue(all(not any(find(rs, 'output', 'energy')['raw']) for rs in group_records(records).values()))
                if kind == 'transient':
                    self.assertTrue(any(r['block'] == 'SHORT' for r in report['frames']))
                    for rs in group_records(records).values():
                        if find(rs, 'mdct', 'input')['block_type'] == 2:
                            self.assertIsNone(find(rs, 'energy', 'post_tns.energy_ld'))
                if kind == 'noise' and channels == 1:
                    self.assertTrue(any(r['tonality_observed'] for r in report['frames']))
                    self.assertTrue(any(r['pns_bands'] > 0 for r in report['frames']))
                summary.append(dict(case=name, frame_channel_pairs=len(report['frames']),
                                    energy_shift_checks=report['native_energy_shift_checks'],
                                    tns_filters=sum(r['tns_filters'] for r in report['frames']),
                                    pns_bands=sum(r['pns_bands'] for r in report['frames']),
                                    sha256=hashlib.sha256((outputs[0]/'encoded.aac').read_bytes()).hexdigest(),
                                    identical=True))
            ARGS.report.parent.mkdir(parents=True, exist_ok=True)
            ARGS.report.write_text(json.dumps(summary, indent=2), encoding='utf-8')

    def test_out_of_range_selection_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'input.wav'
            wav(source, 48000, 1, 'sine')
            result = subprocess.run([str(ARGS.debug), '--input', str(source), '--output-dir', str(Path(temp)/'out'),
                                     '--frame', '9999'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(json.loads((Path(temp)/'out/run_status.json').read_text())['complete'])

    def test_stage_selection_and_runtime_off(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'input.wav'
            wav(source, 48000, 1, 'noise')
            outputs = []
            for name, extra in (('selected', ['--stages', 'energy']), ('runtime_off', ['--no-trace'])):
                output = Path(temp)/name
                result = subprocess.run([str(ARGS.debug), '--input', str(source), '--output-dir', str(output),
                                         '--frame', '10', '--bitrate', '32000', *extra], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                outputs.append(output)
            records = load_trace(outputs[0]/'native_trace.jsonl')
            self.assertEqual({r['stage'] for r in records}, {'context', 'mdct', 'energy', 'output'})
            self.assertIsNone(validate(records)['frames'][0]['tns_filters'])
            self.assertFalse((outputs[1]/'native_trace.jsonl').exists())
            self.assertEqual((outputs[0]/'encoded.aac').read_bytes(), (outputs[1]/'encoded.aac').read_bytes())

    def test_standalone_mdct_input_rejected(self):
        result = subprocess.run([sys.executable, str(ROOT/'my_workspace/psychoacoustic_model/tools/run_psy_analysis.py'),
                                 '--input', str(ROOT/'my_workspace/window_mdct/output/05_mdct_output.txt')], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('standalone replay is not supported', result.stderr)

    def test_debug_binary_cannot_be_normal_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'input.wav'
            wav(source, 48000, 1, 'sine')
            result = subprocess.run([sys.executable, str(ROOT/'my_workspace/psychoacoustic_model/tools/run_psy_analysis.py'),
                                     '--wav', str(source), '--frame', '10', '--skip-build',
                                     '--binary', str(ARGS.debug), '--normal-binary', str(ARGS.debug),
                                     '--verify-bitstream', '--no-plots', '--output-dir', str(Path(temp)/'out')],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('normal reference', result.stderr.lower())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', type=Path, required=True)
    parser.add_argument('--normal', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=ROOT/'my_workspace/psychoacoustic_model/output/psy_tests/native_regression.json')
    ARGS, unknown = parser.parse_known_args()
    ARGS.debug = ARGS.debug.resolve()
    ARGS.normal = ARGS.normal.resolve()
    unittest.main(argv=[sys.argv[0], *unknown])
