import argparse
import csv
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT=Path(__file__).resolve().parents[4]
ARGS=None
MODES=['PSY_TONALITY_ON_TNS_ON','PSY_TONALITY_ON_TNS_OFF','PSY_TONALITY_OFF_TNS_ON','PSY_TONALITY_OFF_TNS_OFF']

class NativeTests(unittest.TestCase):
    def test_four_native_cases_and_original_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);streams=[];traces=[]
            for n,mode in enumerate(['BASELINE',*MODES]):
                binary=ARGS.baseline if n==0 else ARGS.binary
                out=folder/str(n)
                p=subprocess.run([str(binary),'--input',str(ROOT/'my_workspace/INPUT/data/abc_votay.wav'),'--output-dir',str(out),
                                  '--mode',mode,'--runs','1','--profile-runs','1','--expected-pns','0'],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                meta=json.loads((out/'run_metadata.json').read_text())
                self.assertTrue(meta['complete']);self.assertFalse(meta['main_timing_has_trace']);self.assertFalse(meta['main_timing_has_stage_clocks'])
                streams.append((out/'encoded.aac').read_bytes())
                if n:
                    with (out/'psy_trace.csv').open() as f:rows=list(csv.DictReader(f))
                    traces.append([(r['frame_index'],r['window_sequence'],r['window_shape'],r['mdct_hash']) for r in rows])
                    self.assertEqual(len(rows),454)
                    self.assertEqual(meta['effective_pns_enabled'],0)
                    tone=n in (1,2);tns=n in (1,3)
                    self.assertEqual(meta['tonality_applied_frames']>0,tone)
                    self.assertEqual(meta['encoder_tns_filters']>0,tns)
                    self.assertEqual(meta['encoder_tns_filters'],meta['decoder_tns_filters'])
                    if not tone:self.assertTrue(all(not r['tonality_value'] and not r['tonality_values_q15'] for r in rows))
            self.assertEqual(streams[0],streams[1]);self.assertEqual(streams[1],streams[3]);self.assertEqual(streams[2],streams[4])
            self.assertTrue(all(r==traces[0] for r in traces))

    def test_pns_enabled_off_case_is_unsupported(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'stereo.wav';raw=[]
            for i in range(48000):raw.extend(((i*37)%25000-12500,(i*53)%24000-12000))
            with wave.open(str(source),'wb') as w:w.setparams((2,2,48000,0,'NONE','not compressed'));w.writeframes(struct.pack('<%dh'%len(raw),*raw))
            p=subprocess.run([str(ARGS.binary),'--input',str(source),'--output-dir',str(Path(temp)/'out'),
                              '--mode',MODES[2],'--runs','1','--profile-runs','1','--expected-pns','1'],capture_output=True,text=True)
            self.assertEqual(p.returncode,2,p.stdout+p.stderr)
            self.assertIn('UNSUPPORTED:',p.stderr)
            self.assertFalse((Path(temp)/'out/encoded.aac').exists())

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True)
    ARGS,remaining=p.parse_known_args();ARGS.binary=ARGS.binary.resolve();ARGS.baseline=ARGS.baseline.resolve()
    unittest.main(argv=[sys.argv[0],*remaining])
