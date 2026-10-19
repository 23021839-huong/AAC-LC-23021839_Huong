"""Integration inputs are PCM; every encoder output is produced by native FDK."""
import argparse
import json
import math
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[4]
ARGS = None


def wav(path, rate=48000, channels=1, kind='sine'):
    rng = random.Random(42)
    samples = []
    for i in range(rate // 2):
        for channel in range(channels):
            if kind == 'silence':
                value = 0
            elif kind == 'noise':
                value = rng.randint(-18000, 18000)
            elif kind == 'transient':
                value = rng.randint(-24000, 24000) if rate//5 <= i < rate//5+800 else 0
            else:
                value = int(12000*math.sin(2*math.pi*(997+271*channel)*i/rate))
            samples.append(value)
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
        stream.writeframes(struct.pack('<%dh' % len(samples), *samples))


class NativeSmoke(unittest.TestCase):
    def call(self, binary, source, directory, *options):
        self.assertTrue(binary.is_file(), f'Native quantization runner missing: {binary}')
        return subprocess.run([str(binary), '--wav', str(source), '--output-dir', str(directory),
                               *map(str, options)], capture_output=True, text=True)

    def test_native_interface_and_bitstream_invariance(self):
        # Missing/incorrect frame hooks, scale, selector or algorithm side effects fail this test.
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base/'input.wav'
            wav(source)
            for label, binary in [('debug', ARGS.debug), ('normal', ARGS.normal)]:
                result = self.call(binary, source, base/label, '--frame', 10, '--channel', 0)
                self.assertEqual(result.returncode, 0, result.stderr)
            records = [json.loads(line) for line in (base/'debug/native_trace.jsonl').read_text().splitlines()]
            self.assertTrue(records)
            self.assertEqual({r['frame'] for r in records}, {10})
            self.assertEqual({r['channel'] for r in records}, {0})
            spectrum = next(r for r in records if r['stage'] == 'input' and r['name'] == 'spectrum')
            self.assertEqual(len(spectrum['raw']), 1024)
            self.assertEqual(spectrum['bit_width'], 32)
            self.assertEqual(spectrum['fraction_bits'], 31)
            self.assertTrue(spectrum['valid_indices'])
            self.assertFalse((base/'normal/native_trace.jsonl').exists())
            self.assertEqual((base/'debug/encoded.aac').read_bytes(), (base/'normal/encoded.aac').read_bytes())
            status = json.loads((base/'debug/run_status.json').read_text())
            self.assertTrue(status['complete'])
            self.assertTrue(status['quant_debug'])

    def test_stereo_selector_and_out_of_range(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base/'stereo.wav'
            wav(source, channels=2)
            result = self.call(ARGS.debug, source, base/'selected', '--frames', '5:8', '--channel', 1)
            self.assertEqual(result.returncode, 0, result.stderr)
            records = [json.loads(line) for line in (base/'selected/native_trace.jsonl').read_text().splitlines()]
            self.assertEqual({r['channel'] for r in records}, {1})
            self.assertEqual({r['frame'] for r in records}, {5, 6, 7})
            for name, options in [('channel', ('--channel', 2)), ('range', ('--frame', 10000))]:
                result = self.call(ARGS.debug, source, base/name, *options)
                self.assertNotEqual(result.returncode, 0)

    def test_output_collision_and_debug_no_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base/'input.wav'
            wav(source)
            first = self.call(ARGS.debug, source, base/'out', '--no-trace')
            self.assertEqual(first.returncode, 0, first.stderr)
            before = (base/'out/encoded.aac').read_bytes()
            second = self.call(ARGS.debug, source, base/'out')
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual((base/'out/encoded.aac').read_bytes(), before)
            self.assertFalse((base/'out/native_trace.jsonl').exists())


class NativeStages(unittest.TestCase):
    call = NativeSmoke.call

    def test_tns_compression_is_observed_at_native_writer(self):
        # An unused Psy member must not be presented as the writer's decision.
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            result=self.call(ARGS.debug,ROOT/'my_workspace/INPUT/data/abc_votay.wav',base/'out','--frame',22)
            self.assertEqual(result.returncode,0,result.stderr)
            records=[json.loads(line) for line in (base/'out/native_trace.jsonl').read_text().splitlines()]
            coefficients=next(r for r in records if r['stage']=='input' and r['name']=='tns_coefficients' and r['index']==0)
            self.assertEqual(coefficients['raw'],[-1,2,2,0,0,0,1,0,-1])
            with self.subTest(epoch='input'):
                self.assertFalse(any(r['stage']=='input' and r['name']=='tns_coef_compress' for r in records))
            with self.subTest(epoch='writer'):
                events=[r for r in records if r['stage']=='final' and r['name']=='tns_coef_compress' and r['index']==0]
                self.assertEqual(len(events),1)
                self.assertEqual(events[0]['raw'],[1])
                self.assertEqual(events[0]['phase'],'tns_write')

    def test_shared_stereo_decisions_obey_each_channel_selector(self):
        # Dropping shared decisions when the previous loop ends on ch1 fails this.
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);source=base/'noise.wav';wav(source,channels=2,kind='noise')
            for selector in ('0','1','all'):
                result=self.call(ARGS.debug,source,base/selector,'--frames','5:12','--channel',selector,'--bitrate',64000)
                self.assertEqual(result.returncode,0,result.stderr)
                records=[json.loads(line) for line in (base/selector/'native_trace.jsonl').read_text().splitlines()]
                for channel in ((0,1) if selector=='all' else (int(selector),)):
                    rs=[r for r in records if r['channel']==channel]
                    with self.subTest(selector=selector,channel=channel,stage='rate'):
                        self.assertEqual({r['frame'] for r in rs if r['name']=='rate.accepted'},set(range(5,12)))
                    with self.subTest(selector=selector,channel=channel,stage='threshold'):
                        self.assertTrue(any(r['name']=='first_guess.pe' for r in rs))
                if selector=='all':
                    for name in ('rate.accepted','first_guess.pe','second_guess.pe'):
                        left=[(r['frame'],r['iteration'],r['raw']) for r in records if r['channel']==0 and r['name']==name]
                        right=[(r['frame'],r['iteration'],r['raw']) for r in records if r['channel']==1 and r['name']==name]
                        self.assertEqual(left,right,name)

    def test_all_native_stages_and_line_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base/'noise.wav'
            wav(source, kind='noise')
            result = self.call(ARGS.debug, source, base/'debug', '--frame', 10,
                               '--bitrate', 32000, '--line-trace')
            self.assertEqual(result.returncode, 0, result.stderr)
            records = [json.loads(line) for line in (base/'debug/native_trace.jsonl').read_text().splitlines()]
            keys = {(r['stage'], r['name']) for r in records}
            for key in [('form_factor','accumulator'), ('form_factor','ld'),
                        ('pe','initial.sfb_pe'), ('pe','initial.channel_pe'),
                        ('threshold','after.threshold_ld'), ('scalefactor','seed.absolute'),
                        ('scalefactor','optimized.absolute'), ('scalefactor','normalized.relative'),
                        ('global_gain','initial'), ('quantization','line.table_index'),
                        ('quantization','line.mul_q'), ('final','reconstructed_spectrum'),
                        ('iterations','trial.distortion_ld'), ('iterations','rate.bits')]:
                self.assertIn(key, keys, f'Native stage missing: {key}')
            self.assertTrue(any(r['loop_kind'] == 'scalefactor' for r in records))
            self.assertTrue(any(r['loop_kind'] == 'rate' for r in records))
            q = next(r for r in records if r['stage']=='final' and r['name']=='quantized_spectrum')
            self.assertTrue(all(v is None or abs(v)<=8191 for v in q['raw']))
            inverse = next(r for r in records if r['stage']=='final' and r['name']=='reconstructed_spectrum')
            self.assertEqual(inverse['exponent'], inverse['mdct_scale']+1)
            normal = self.call(ARGS.normal, source, base/'normal', '--frame', 10, '--bitrate', 32000)
            self.assertEqual(normal.returncode, 0, normal.stderr)
            self.assertEqual((base/'debug/encoded.aac').read_bytes(), (base/'normal/encoded.aac').read_bytes())

    def test_stage_subset_preserves_bits(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base/'input.wav'
            wav(source, channels=2, kind='transient')
            for name, options in [('subset', ('--stages','form_factor,quantization','--no-iteration-log')),
                                  ('full', ()), ('disabled', ('--no-trace',))]:
                result = self.call(ARGS.debug, source, base/name, '--frames','0:18',
                                   '--channel','all', '--afterburner',0, *options)
                self.assertEqual(result.returncode, 0, result.stderr)
            outputs = [(base/name/'encoded.aac').read_bytes() for name in ('subset','full','disabled')]
            self.assertEqual(outputs[0], outputs[1]); self.assertEqual(outputs[0], outputs[2])
            records = [json.loads(line) for line in (base/'subset/native_trace.jsonl').read_text().splitlines()]
            self.assertNotIn('iterations', {r['stage'] for r in records})
            self.assertNotIn('pe', {r['stage'] for r in records})

    def test_iteration_toggle_keeps_final_scalefactors(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);source=base/'noise.wav';wav(source,kind='noise')
            result=self.call(ARGS.debug,source,base/'out','--frame',10,'--no-iteration-log')
            self.assertEqual(result.returncode,0,result.stderr)
            records=[json.loads(line) for line in (base/'out/native_trace.jsonl').read_text().splitlines()]
            self.assertFalse(any(r['candidate']>=0 for r in records),'Per-candidate payload must obey iteration logging toggle')
            self.assertTrue(any(r['name']=='normalized.relative' for r in records))

    def test_native_decoder_accepts_encoded_packets(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);source=base/'sine.wav';wav(source,channels=2)
            result=self.call(ARGS.debug,source,base/'out','--frame',10,'--decode-check')
            self.assertEqual(result.returncode,0,result.stderr)
            status=json.loads((base/'out/run_status.json').read_text())
            self.assertEqual(status['decoded_packets'],status['packets'])

    def test_signal_matrix_invariance_and_geometry(self):
        import sys
        sys.path.insert(0,str(ROOT/'my_workspace/quantization_coding/tools'))
        from quant_trace_data import load_trace,validate
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);results=[]
            for kind,rate,channels,bitrate,afterburner in (
                ('silence',48000,1,64000,1),('noise',48000,1,32000,1),
                ('sine',44100,2,96000,1),('transient',48000,2,64000,0)):
                source=base/(kind+'.wav');wav(source,rate,channels,kind)
                for mode,binary in [('debug',ARGS.debug),('normal',ARGS.normal)]:
                    result=self.call(binary,source,base/(kind+'_'+mode),'--frames','0:18',
                        '--channel','all','--bitrate',bitrate,'--afterburner',afterburner)
                    self.assertEqual(result.returncode,0,result.stderr)
                left=base/(kind+'_debug');right=base/(kind+'_normal')
                self.assertEqual((left/'encoded.aac').read_bytes(),(right/'encoded.aac').read_bytes())
                report=validate(load_trace(left/'native_trace.jsonl'))
                self.assertEqual(len(report['frames']),18*channels)
                results.append(dict(kind=kind,rate=rate,channels=channels,bitrate=bitrate,
                    afterburner=afterburner,identical=True,valid=report['valid'],coverage=report['coverage']))
            folder=ROOT/'my_workspace/quantization_coding/output/quant_validation';folder.mkdir(parents=True,exist_ok=True)
            (folder/'signal_matrix.json').write_text(json.dumps(results,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', type=Path, required=True)
    parser.add_argument('--normal', type=Path, required=True)
    ARGS, remaining = parser.parse_known_args()
    unittest.main(argv=[__file__, *remaining])
