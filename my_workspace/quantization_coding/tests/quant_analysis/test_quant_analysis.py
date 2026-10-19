"""Parser fixtures are unit inputs only, never presented as native DSP output."""
import importlib
import copy
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'my_workspace/quantization_coding/tools'))
sys.path.insert(0,str(ROOT/'my_workspace/psychoacoustic_model/tools'))


def record(raw, fraction=31, exponent=0, unit='pcm', width=32, valid=None):
    return dict(schema_version=1,sequence=1,frame=0,element=0,channel=0,
        stage='input',name='spectrum',loop_kind='none',phase='input',iteration=-1,
        candidate=-1,sfb=-1,index=0,count=len(raw),bit_width=width,signed=True,
        fraction_bits=fraction,exponent=exponent,unit=unit,raw=raw,
        raw_hex=[None if v is None else f'{v&((1<<width)-1):0{width//4}X}' for v in raw],
        valid_indices=list(range(len(raw))) if valid is None else valid,
        sample_rate=48000,bitrate=64000,frame_length=1024,block_type=0,
        window_shape=0,mdct_scale=0,sfb_count=1,sfb_per_group=1,max_sfb_per_group=1,
        grouping_mask=0,group_lengths=[1,0,0,0],stage_mask=255,
        iteration_log=True,line_log=False,source='fixture',function='fixture',source_line=1)


class TraceTests(unittest.TestCase):
    def api(self):
        try:
            return importlib.import_module('quant_trace_data')
        except ImportError:
            self.fail('Quant native trace parser/reconstruction is not implemented')

    def test_fixed_point_and_half_scale_reconstruction(self):
        api=self.api()
        self.assertEqual(api.reconstruct(record([1073741824],31,3))[0],4.0)
        self.assertEqual(api.reconstruct(record([536870912],31,4))[0],4.0)
        self.assertEqual(api.reconstruct(record([65536],16,0,'pe'))[0],1.0)
        self.assertEqual(api.reconstruct(record([7],0,0,'pe'))[0],7.0)
        self.assertEqual(api.reconstruct(record([-2147483648,0],31,0,'ld64')).tolist(),[0.0,1.0])
        ff=record([16777216],31,0,'form_factor');ff['mdct_scale']=2
        self.assertEqual(api.reconstruct(ff)[0],1.0)

    def test_padding_bit_width_and_schema_rejected(self):
        api=self.api()
        good=record([123,None],valid=[0])
        self.assertTrue(api.validate_record(good))
        for bad in [record([123,456],valid=[0]),record([None],valid=[0]),
                    record([32768],0,0,'quantized_integer',16)]:
            with self.assertRaises(ValueError):api.validate_record(bad)
        bad=record([1]);bad['raw_hex']=['00000002']
        with self.assertRaises(ValueError):api.validate_record(bad)

    def test_loader_reports_bad_line_and_empty_trace(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'trace.jsonl'
            path.write_text(json.dumps(record([1]))+'\nnot-json\n')
            with self.assertRaisesRegex(ValueError,':2:'):api.load_trace(path)
            path.write_text('')
            with self.assertRaises(ValueError):api.load_trace(path)

    def test_invalid_group_geometry_is_rejected(self):
        api=self.api()
        for key,value in [('sfb_per_group',0),('max_sfb_per_group',2),('block_type',9)]:
            bad=record([1]);bad[key]=value
            with self.assertRaises(ValueError):api.validate_record(bad)

    def test_each_selected_stage_is_required_for_successful_validation(self):
        # A dropped stage must not become a valid campaign with None/zero summaries.
        api=self.api()
        records=[r for r in api.load_trace(ROOT/'my_workspace/quantization_coding/output/quant/native_trace.jsonl') if r['frame']==10]
        for stage in api.STAGES:
            with self.subTest(stage=stage):
                with self.assertRaisesRegex(ValueError,'missing'):
                    api.validate([r for r in records if r['stage']!=stage])

    def test_missing_final_bit_component_is_not_zero(self):
        api=self.api()
        records=[r for r in api.load_trace(ROOT/'my_workspace/quantization_coding/output/quant/native_trace.jsonl') if r['frame']==10]
        with self.assertRaisesRegex(ValueError,'missing'):
            api.validate([r for r in records if not (r['stage']=='final' and r['name']=='noise_bits')])

    def test_explicit_stage_and_iteration_toggles_allow_omitted_payload(self):
        import copy
        api=self.api()
        records=copy.deepcopy([r for r in api.load_trace(ROOT/'my_workspace/quantization_coding/output/quant/native_trace.jsonl') if r['frame']==10])
        records=[r for r in records if r['stage'] in ('input','context','build','final','quantization') and r['candidate']<0]
        for r in records:r['stage_mask']=64;r['iteration_log']=False
        self.assertTrue(api.validate(records)['valid'])

    def test_exported_event_preserves_loop_kind_and_source(self):
        module=importlib.import_module('analyze_quant_outputs')
        r=record([123]);r['loop_kind']='scalefactor';r['phase']='distortion_trial';r['_line']=7
        row=list(module.event_rows([r]))[0]
        fields=dict(zip(module.EVENT_HEADER.split(),row))
        self.assertEqual(fields.get('loop_kind'),'scalefactor')
        self.assertEqual(fields.get('cpp_line'),1)
        self.assertEqual(fields.get('trace_line'),7)

    def test_export_real_native_trace_and_vectors(self):
        self.api()
        try:
            exporter=importlib.import_module('analyze_quant_outputs')
        except ImportError:
            self.fail('Quant TXT/vector exporter is not implemented')
        trace=ROOT/'my_workspace/quantization_coding/output/quant/native_trace.jsonl'
        self.assertTrue(trace.is_file(),'Run the native original-WAV campaign first')
        with tempfile.TemporaryDirectory() as temp:
            report=exporter.export(trace,Path(temp))
            self.assertTrue(report['valid'])
            for name in ['01_form_factor.txt','02_pe_per_sfb.txt','04_threshold_before.txt',
                         '05_scalefactor_initial.txt','07_spectrum_quantized.txt','08_iteration_trace.txt']:
                self.assertTrue((Path(temp)/'frame_000010/channel_0'/name).is_file())
            vector=json.loads((Path(temp)/'frame_000010/channel_0/vectors/metadata.json').read_text())
            self.assertEqual(vector['provenance'],'native FDK-AAC QUANT_DEBUG')
            self.assertEqual(vector['coefficient_count'],1024)


class CliTests(unittest.TestCase):
    def run_cli(self,*options):
        script=ROOT/'my_workspace/quantization_coding/tools/run_quant_analysis.py'
        self.assertTrue(script.is_file(),'Quant Linux/Python orchestrator is not implemented')
        return subprocess.run([sys.executable,str(script),*map(str,options)],capture_output=True,text=True)

    def test_psy_text_without_wav_is_rejected(self):
        result=self.run_cli('--input',ROOT/'my_workspace/psychoacoustic_model/output/psy')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('state',result.stderr.lower())

    def test_invalid_selection_rejected_before_build(self):
        for options in [('--frames','9:3'),('--channel','2'),('--stages','fictional')]:
            result=self.run_cli(*options,'--skip-build')
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('Traceback',result.stderr)

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);marker=directory/'keep.txt';marker.write_text('user data')
            result=self.run_cli('--output-dir',directory,'--skip-build')
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(marker.read_text(),'user data')

    def test_overwrite_rejects_non_quant_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/'result';directory.mkdir()
            marker=directory/'keep.txt';marker.write_text('user data')
            (directory/'run_status.json').write_text('{"complete":true,"psy_debug":true}')
            result=self.run_cli('--output-dir',directory,'--skip-build','--overwrite','--no-plots')
            self.assertNotEqual(result.returncode,0)
            self.assertTrue(marker.is_file(),'Foreign output must not be moved by Quant overwrite')

    def test_plot_ancestor_overlap_rejected_before_campaign_creation(self):
        # Moving an identified plot ancestor must never move the new data/input.
        for contains in ('output','wav','psy'):
            with self.subTest(contains=contains),tempfile.TemporaryDirectory() as temp:
                base=Path(temp);plots=base/'plots';plots.mkdir()
                (plots/'quant_plot_campaign.json').write_text('{"provenance":"native FDK-AAC QUANT_DEBUG"}')
                keep=plots/'keep.png';keep.write_bytes(b'user result')
                out=plots/'data' if contains=='output' else base/'data'
                options=[]
                if contains=='wav':
                    source=plots/'input.wav';source.write_bytes(b'input')
                    options=['--wav',source]
                if contains=='psy':options=['--wav',ROOT/'my_workspace/INPUT/data/abc_votay.wav','--input',plots]
                result=self.run_cli('--output-dir',out,'--plots-dir',plots,'--overwrite',
                    '--skip-build','--binary',base/'missing.exe',*options)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('overlap',result.stderr.lower())
                self.assertFalse(out.exists(),'Reject all path relationships before creating a campaign')
                self.assertEqual(keep.read_bytes(),b'user result')


class PsyAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from quant_trace_data import load_trace
        from psy_trace_data import load_trace as load_psy
        cls.records=[r for r in load_trace(ROOT/'my_workspace/quantization_coding/output/quant/native_trace.jsonl') if r['frame']==22]
        cls.psy=[r for r in load_psy(ROOT/'my_workspace/psychoacoustic_model/output/psy/native_trace.jsonl') if r['frame']==22]
        cls.manifest=json.loads((ROOT/'my_workspace/psychoacoustic_model/output/psy/survey_manifest.json').read_text())

    def fixture(self,directory,stereo_fields=False):
        # Controlled audit fixtures, not claimed to be stereo DSP output.
        records=copy.deepcopy(self.records);psy=copy.deepcopy(self.psy)
        if stereo_fields:
            qs=next(r for r in records if r['stage']=='input' and r['name']=='common_window')
            ps=next(r for r in psy if r['stage']=='output' and r['name']=='sfb_count')
            for name in ('common_window','ms_digest'):
                if name=='ms_digest':
                    q=copy.deepcopy(qs);q['name']=name;records.append(q)
                p=copy.deepcopy(ps);p.update(name=name,raw=[0]);psy.append(p)
            q=copy.deepcopy(next(r for r in records if r['stage']=='input' and r['name']=='is_book'));q['name']='ms_mask';records.append(q)
            p=copy.deepcopy(next(r for r in psy if r['stage']=='output' and r['name']=='is_book'));p['name']='ms_mask';psy.append(p)
        path=directory/'native_trace.jsonl'
        path.write_text(''.join(json.dumps(r)+'\n' for r in psy),encoding='utf-8')
        manifest=copy.deepcopy(self.manifest)
        manifest['trace_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        (directory/'survey_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        return records,manifest

    def audit(self,directory,records,manifest):
        from run_quant_analysis import audit_psy
        return audit_psy(directory,records,manifest['input_sha256'],manifest['configuration'])

    def test_audit_rejects_changed_observed_native_tool_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);records,manifest=self.fixture(directory,stereo_fields=True)
            self.assertTrue(self.audit(directory,records,manifest)['matched'])
            for name in ('common_window','ms_digest','tns_coef_res'):
                changed=copy.deepcopy(records)
                r=next(r for r in changed if r['stage']=='input' and r['name']==name)
                r['raw'][0]+=1;r['raw_hex'][0]=f"{r['raw'][0]:08X}"
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError,'mismatch'):
                        self.audit(directory,changed,manifest)

    def test_audit_rejects_trace_changed_since_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);records,manifest=self.fixture(directory)
            path=directory/'native_trace.jsonl'
            path.write_text(path.read_text().replace('\n',' \n'),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'trace.*hash|provenance'):
                self.audit(directory,records,manifest)

    def test_audit_reports_fields_unavailable_from_mono_psy_producer(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);records,manifest=self.fixture(directory)
            report=self.audit(directory,records,manifest)
            self.assertTrue(report['matched'])
            self.assertIn('common_window',report.get('unavailable_fields',{}))
            self.assertNotIn('common_window',report.get('checked_fields',[]))


class PlotTests(unittest.TestCase):
    def test_real_native_pngs_and_selection(self):
        try:
            module=importlib.import_module('plot_quant_stages')
        except ImportError:
            self.fail('Quant native PNG plotter is not implemented')
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            result=module.plot(ROOT/'my_workspace/quantization_coding/output/quant/native_trace.jsonl',Path(temp),10,0)
            self.assertEqual(result['frame'],10);self.assertEqual(result['channel'],0)
            self.assertEqual(len(result['plots']),15)
            for name in result['plots']:
                with Image.open(Path(temp)/name) as img:
                    self.assertGreater(img.width,500);self.assertGreater(img.height,200)
                    self.assertEqual(img.format,'PNG')


if __name__=='__main__':unittest.main()
