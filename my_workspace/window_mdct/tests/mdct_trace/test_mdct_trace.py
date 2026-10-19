#!/usr/bin/env python3
"""Consumer-level tests for the instrumented AAC-LC encoder (no FFT substitute)."""
import argparse
import csv
import json
import math
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path, default=ROOT / 'build/mdct_debug/fdk_mdct_trace')
parser.add_argument('--baseline', type=Path)
parser.add_argument('--test')
ARGS = parser.parse_args()


def rows(path, columns):
    values = [list(map(int, line.split())) for line in path.read_text().splitlines()]
    if any(len(v) != columns for v in values):
        raise AssertionError('wrong number of columns in ' + str(path))
    if [v[0] for v in values] != list(range(len(values))):
        raise AssertionError('indices must be contiguous: ' + str(path))
    return values


def write_pcm(path, channels=1, bits=16):
    rng = random.Random(345)
    samples = []
    for n in range(12288):
        # Quiet history followed by isolated attacks, for real block switching.
        value = rng.randrange(-26000, 26001) if 2048 <= n < 2200 or 6144 <= n < 6450 else 0
        samples.extend([value] if channels == 1 else [value, -value // 2])
    with wave.open(str(path), 'wb') as f:
        f.setparams((channels, bits // 8, 48000, 0, 'NONE', ''))
        f.writeframes(struct.pack('<' + 'h' * len(samples), *samples))
    return samples


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(ARGS.binary.is_file(), 'The instrumented encoder runner is not built yet')
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.wav = self.root / 'attacks.wav'
        self.samples = write_pcm(self.wav)

    def tearDown(self):
        if hasattr(self, 'temp'):
            self.temp.cleanup()

    def run_encoder(self, name='trace', source=None, binary=None, *options):
        out = self.root / name
        result = subprocess.run([str(binary or ARGS.binary), '--input', str(source or self.wav),
                                 '--output-dir', str(out), *options],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return out

    def assert_contract(self, out):
        meta = json.loads((out / 'stage_metadata.json').read_text())
        info = json.loads((out / 'input_info.json').read_text())
        self.assertEqual(info['sample_rate'], 48000)
        self.assertEqual(info['bits_per_sample'], 16)
        self.assertEqual(info['sample_frames'], 12288)
        self.assertEqual(meta['pcm_samples'], 2048)
        self.assertEqual(meta['data_fraction_bits'], 31)
        pcm = rows(out / '00_pcm_input.txt', 2)
        self.assertEqual(len(pcm), 2048)
        for f in ['01_window_fold.txt', '04_postprocessing.txt', '05_mdct_output.txt']:
            self.assertEqual(len(rows(out / f, 2)), 1024)
        for f in ['02_preprocessing.txt', '03_fft.txt']:
            self.assertEqual(len(rows(out / f, 3)), 512)
        self.assertEqual(rows(out / '04_postprocessing.txt', 2), rows(out / '05_mdct_output.txt', 2))
        exponents = rows(out / '05_mdct_exponents.txt', 2)
        self.assertEqual(len(exponents), 1024)
        short = meta['block_type'] == 'SHORT'
        self.assertEqual(len(meta['subtransforms']), 8 if short else 1)
        for s in meta['subtransforms']:
            self.assertEqual(s['L'], 128 if short else 1024)
            self.assertEqual(s['M'], s['L'] // 2)
            e = s['exponents']
            self.assertEqual(e['window_fold'], {'variable': 2, 'effective': 2})
            self.assertEqual(e['preprocessing'], {'variable': 2, 'effective': 4})
            self.assertEqual(e['fft'], {'variable': 7 if short else 10, 'effective': 9 if short else 12})
            self.assertEqual(e['postprocessing'], {'variable': 9 if short else 12, 'effective': 9 if short else 12})
            lo, hi = s['scalar_offset'], s['scalar_offset'] + s['L']
            self.assertEqual([r[1] for r in exponents[lo:hi]], [9 if short else 12] * s['L'])
        return meta

    def test_reports_native_encoder_stages(self):
        out = self.run_encoder()
        meta = self.assert_contract(out)
        catalog = list(csv.DictReader((out / 'frame_index.csv').open()))
        selected = [r for r in catalog if int(r['channel']) == meta['channel']]
        highest = max(float(r['pcm_rms']) for r in selected)
        expected = next(int(r['frame']) for r in selected if float(r['pcm_rms']) == highest)
        self.assertEqual(meta['selected_frame'], expected)
        self.assertAlmostEqual(meta['pcm_rms'], highest, places=7)

    def test_short_frame_preserves_eight_independent_transforms(self):
        out = self.run_encoder('catalog')
        catalog = list(csv.DictReader((out / 'frame_index.csv').open()))
        short_frames = [int(r['frame']) for r in catalog if r['block_type'] == 'SHORT']
        self.assertTrue(short_frames, 'attack fixture should cause real AAC-LC short blocks')
        selected = self.run_encoder('short', None, None, '--frame', str(short_frames[0]))
        meta = self.assert_contract(selected)
        for q, s in enumerate(meta['subtransforms']):
            self.assertEqual(s['input_start'], 448 + 128 * q)
            self.assertEqual(s['input_length'], 256)

    def test_channel_selection_uses_native_channel_buffer(self):
        source = self.root / 'stereo.wav'
        values = write_pcm(source, channels=2)
        out = self.run_encoder('stereo', source, None, '--channel', '1')
        meta = self.assert_contract(out)
        self.assertEqual(meta['channel'], 1)
        allowed = set(values[1::2]) | {0}
        self.assertTrue(all(v in allowed for _, v in rows(out / '00_pcm_input.txt', 2)))

    def test_debug_does_not_change_aac_bitstream(self):
        if not ARGS.baseline:
            self.skipTest('pass --baseline to compare MDCT_DEBUG=OFF encoder')
        self.assertTrue(ARGS.baseline.is_file())
        traced = self.run_encoder('on')
        plain = self.run_encoder('off', None, ARGS.baseline)
        self.assertEqual((traced / 'encoded.aac').read_bytes(), (plain / 'encoded.aac').read_bytes())
        self.assertFalse((plain / '01_window_fold.txt').exists())

    def test_truncated_wav_is_rejected(self):
        bad = self.root / 'truncated.wav'
        bad.write_bytes(self.wav.read_bytes()[:-37])
        r = subprocess.run([str(ARGS.binary), '--input', str(bad), '--output-dir', str(self.root / 'bad')],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('truncat', r.stderr.lower())

    def test_out_of_range_frame_is_rejected(self):
        r = subprocess.run([str(ARGS.binary), '--input', str(self.wav), '--output-dir', str(self.root / 'missing'),
                            '--frame', '99999'], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('frame', r.stderr.lower())

    def test_failed_rerun_marks_previous_dumps_as_stale(self):
        out = self.run_encoder('reuse')
        r = subprocess.run([str(ARGS.binary), '--input', str(self.wav), '--output-dir', str(out),
                            '--frame', '99999'], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        status = out / 'run_status.json'
        self.assertTrue(status.is_file(), 'a failed rerun must not present old dumps as current')
        self.assertFalse(json.loads(status.read_text())['complete'])

    def test_pcm24_conversion_keeps_signed_top_16_bits(self):
        values = [-32768, -1, 0, 1, 32767] * 1000
        source = self.root / 'pcm24.wav'
        payload = b''.join((v * 256 & 0xffffff).to_bytes(3, 'little') for v in values)
        fmt = struct.pack('<HHIIHH', 1, 1, 48000, 144000, 3, 24)
        body = b'WAVEfmt ' + struct.pack('<I', 16) + fmt + b'data' + struct.pack('<I', len(payload)) + payload
        source.write_bytes(b'RIFF' + struct.pack('<I', len(body)) + body)
        out = self.run_encoder('pcm24', source)
        allowed = set(values)
        self.assertTrue(all(v in allowed for _, v in rows(out / '00_pcm_input.txt', 2)))
        info = json.loads((out / 'input_info.json').read_text())
        self.assertEqual(info['bits_per_sample'], 24)
        self.assertEqual(info['converted_bits'], 16)

    def test_nonfinite_float_wav_is_rejected(self):
        source = self.root / 'nan.wav'
        payload = struct.pack('<f', float('nan')) * 2048
        fmt = struct.pack('<HHIIHH', 3, 1, 48000, 192000, 4, 32)
        body = b'WAVEfmt ' + struct.pack('<I', 16) + fmt + b'data' + struct.pack('<I', len(payload)) + payload
        source.write_bytes(b'RIFF' + struct.pack('<I', len(body)) + body)
        r = subprocess.run([str(ARGS.binary), '--input', str(source)], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('non-finite', r.stderr.lower())


if __name__ == '__main__':
    suite = (unittest.defaultTestLoader.loadTestsFromName(ARGS.test, TraceTests)
             if ARGS.test else unittest.defaultTestLoader.loadTestsFromTestCase(TraceTests))
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
