"""Protect resampling, no-repeat assembly, clipping and portable suite validation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import wave

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / 'my_workspace/psychoacoustic_model/experiments/psy/scripts'
sys.path.insert(0, str(SCRIPTS))


class ExtendedInputTests(unittest.TestCase):
    def module(self, name):
        path = SCRIPTS / (name + '.py')
        self.assertTrue(path.exists(), 'Missing extended input preparation/runner')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_excerpt_resamples_without_changing_pitch_and_downmixes(self):
        module = self.module('prepare_extended_psy_inputs')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'stereo.wav'
            rate = 16000
            t = np.arange(4 * rate) / rate
            x = .3 * np.sin(2 * np.pi * 220 * t)
            sf.write(path, np.column_stack((x, .5 * x)), rate, subtype='PCM_16')
            y, info = module.prepare_excerpt(path, 1, 2)
            self.assertEqual(len(y), 96000)
            self.assertEqual(info['source_channels'], 2)
            peak = np.fft.rfftfreq(len(y), 1 / 48000)[np.argmax(np.abs(np.fft.rfft(y * np.hanning(len(y)))))]
            self.assertAlmostEqual(peak, 220, delta=1)
            self.assertAlmostEqual(np.sqrt(np.mean(y*y)), .225 / np.sqrt(2), delta=.002)
            with self.assertRaises(ValueError):
                module.prepare_excerpt(path, 3, 2)

    def test_montage_refuses_to_repeat_when_sources_are_too_short(self):
        module = self.module('prepare_extended_psy_inputs')
        parts = [np.ones(48000), np.full(48000, .25)]
        y = module.assemble_parts(parts, 2)
        self.assertEqual(len(y), 96000)
        self.assertEqual(y[24000], 1)
        self.assertEqual(y[72000], .25)
        self.assertEqual(y[48000], 0)
        with self.assertRaises(ValueError):
            module.assemble_parts(parts, 3)

    def test_common_rms_retains_peak_headroom_for_sparse_transients(self):
        module = self.module('prepare_extended_psy_inputs')
        x = np.ones(10000)
        y = np.zeros(10000); y[123] = 1
        target = module.common_rms_dbfs([x, y], -24)
        self.assertAlmostEqual(target, -41, places=6)
        a, b = [module.to_pcm16(v, target) for v in (x, y)]
        self.assertLessEqual(max(np.max(np.abs(a.astype(np.int32))), np.max(np.abs(b.astype(np.int32)))), 29205)
        self.assertAlmostEqual(np.sqrt(np.mean(a.astype(float)**2)), np.sqrt(np.mean(b.astype(float)**2)), delta=.5)
        with self.assertRaises(ValueError):
            module.to_pcm16(np.zeros(10), -24)

    def test_source_selection_excludes_old_ids_and_duplicate_takes(self):
        module = self.module('prepare_extended_psy_inputs')
        rows = [dict(category='dog', src_file='old', filename='a.wav'),
                dict(category='dog', src_file='new1', filename='b.wav'),
                dict(category='dog', src_file='new1', filename='c.wav'),
                dict(category='dog', src_file='new2', filename='d.wav')]
        chosen = module.select_esc_sources(rows, ['dog'], 2, {'old'})
        self.assertEqual([r['filename'] for r in chosen], ['b.wav', 'd.wav'])
        with self.assertRaises(ValueError):
            module.select_esc_sources(rows, ['dog'], 3, {'old'})

    def test_individual_normalization_does_not_quieten_all_inputs_for_one_spike(self):
        module = self.module('prepare_extended_psy_inputs')
        self.assertTrue(hasattr(module, 'normalization_targets'), 'Missing per-file headroom normalization')
        x = np.ones(10000)
        y = np.zeros(10000); y[123] = 1
        self.assertEqual(module.normalization_targets([x, y], -24, 'individual'), [-24, -41])
        self.assertEqual(module.normalization_targets([x, y], -24, 'common'), [-41, -41])

    def test_runner_accepts_fifteen_variable_length_inputs_and_rejects_corruption(self):
        module = self.module('run_psy_extended_suite')
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            entries = []
            for i in range(15):
                duration = 10 + i
                path = folder / ('sample_%02d.wav' % i)
                pcm = np.full(duration * 48000, 123, dtype='<i2')
                with wave.open(str(path), 'wb') as w:
                    w.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
                    w.writeframes(pcm.tobytes())
                entries.append(dict(input_id='sample_%02d' % i, filename=path.name,
                                    duration_seconds=duration, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                    label='fixture', source_kind='test fixture'))
            path = folder / 'manifest.json'
            path.write_text(json.dumps(dict(complete=True, inputs=entries)), encoding='utf-8')
            manifest = module.load_manifest(path)
            self.assertEqual(len(manifest['inputs']), 15)
            self.assertEqual(manifest['inputs'][-1]['duration_seconds'], 24)
            (folder / entries[3]['filename']).write_bytes(b'corrupted')
            with self.assertRaises(ValueError):
                module.load_manifest(path)


if __name__ == '__main__':
    unittest.main()
