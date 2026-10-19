"""Windows controlled 2x2 experiment, using native FDK encode/decode only."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import uuid
from measure_distortion import inspect_adts,measure_files

ROOT=Path(__file__).resolve().parents[5]
CASES=[('EXP01','PSY_TONALITY_ON_TNS_ON','exp01_both_on',1,1),
       ('EXP02','PSY_TONALITY_ON_TNS_OFF','exp02_tonality_only',1,0),
       ('EXP03','PSY_TONALITY_OFF_TNS_ON','exp03_tns_only',0,1),
       ('EXP04','PSY_TONALITY_OFF_TNS_OFF','exp04_both_off',0,0)]
FIELDS=['experiment_id','tonality_enabled','tns_enabled','target_bitrate_kbps','actual_bitrate_kbps',
        'encoding_time_mean_ms','encoding_time_std_ms','mse','snr_db','distortion_rate_percent','aac_size_bytes','status',
        'error','encoding_time_min_ms','encoding_time_max_ms','aac_size_kib','coded_duration_seconds',
        'source_duration_seconds','adts_frames','sample_rate','channels','effective_pns_enabled','tonality_applied_frames',
        'encoder_tns_filters','decoder_tns_filters','compared_samples_per_channel','alignment_delay_samples',
        'alignment_correlation','runs','profile_runs','aac_sha256','baseline_identical','run_id']
IDENTITY_FIELDS=('experiment_id','tonality_enabled','tns_enabled','target_bitrate_kbps','runs','profile_runs','run_id')
RUN_FIELDS=['experiment_id','run_index','encoding_time_ms','aac_sha256','status','run_id']
PROFILE_FIELDS=['experiment_id','run_id','run_index','profile_encode_time_ms','psy_model_time_ms',
                'tonality_time_ms','tns_analysis_time_ms','tns_filtering_time_ms','psy_calls','tonality_calls',
                'tns_analysis_calls','tns_filtering_calls']
PLOT_NAMES=('bitrate_comparison.png','encoding_time_comparison.png','distortion_comparison.png',
            'filesize_comparison.png','psy_overview.png')

def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')

def write_csv(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def published_case_paths(folder,experiment,stem):
    return (folder/'encoded'/f'{stem}.aac',folder/'decoded'/f'{experiment.lower()}_decoded.wav',
            folder/'logs'/f'{experiment.lower()}_psy_trace.csv',
            folder/'logs'/f'{experiment.lower()}_distortion_alignment.json')

def blank_failed_row(row,status,error):
    identity={key:row[key] for key in IDENTITY_FIELDS}
    row.clear();row.update({key:'' for key in FIELDS});row.update(identity,status=status,error=str(error))

def invoke(argv,log):
    log.parent.mkdir(parents=True,exist_ok=True)
    p=subprocess.run(list(map(str,argv)),capture_output=True,text=True)
    log.write_text('COMMAND: '+subprocess.list2cmdline(list(map(str,argv)))+'\n'+p.stdout+p.stderr,encoding='utf-8')
    if p.returncode==2 and 'UNSUPPORTED:' in p.stderr:
        raise NotImplementedError(p.stderr.strip())
    if p.returncode:
        raise RuntimeError(f'Command failed ({p.returncode}): {p.stderr.strip() or p.stdout[-1500:]}')

def build(folder,enabled,logs):
    flags=['-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DBUILD_SHARED_LIBS=OFF','-DBUILD_PSY_EXPERIMENT=ON',
           '-DPSY_EXPERIMENT='+('ON' if enabled else 'OFF'),'-DPSY_DEBUG=OFF','-DQUANT_DEBUG=OFF','-DMDCT_DEBUG=OFF',
           '-DWINDOW_EXPERIMENT=OFF','-DFFT_EXPERIMENT=OFF','-DFDK_ENABLE_ENCODER_PROFILING=OFF']
    invoke(['cmake','-S',ROOT,'-B',folder,*flags],logs/'configure.log')
    invoke(['cmake','--build',folder,'--target','fdk_psy_experiment','--parallel','4'],logs/'build.log')

def traces(path):
    with path.open() as f:return list(csv.DictReader(f))

def validate_trace(rows,meta,tone,tns,pns):
    if len(rows)!=meta['adts_frames']*meta['channels']:raise ValueError('trace frame/channel count mismatch')
    if len({(r['frame_index'],r['channel_index']) for r in rows})!=len(rows):raise ValueError('duplicate trace context')
    for r in rows:
        if int(r['pns_enabled'])!=pns:raise ValueError('PNS differs from baseline')
        if tone is not None:
            if int(r['tonality_enabled'])!=tone:raise ValueError('Tonality configured state differs')
            expected=int(tone and r['window_sequence']!='EIGHT_SHORT_SEQUENCE')
            if int(r['tonality_applied'])!=expected:raise ValueError('Tonality actual execution differs from long/short gate')
            if not tone and (r['tonality_value'] or r['tonality_values_q15']):raise ValueError('Tonality OFF has stale output')
        if tns is not None and int(r['tns_enabled'])!=tns:raise ValueError('TNS enable state differs')
        if tns==0 and (int(r['tns_applied']) or int(r['tns_filter_count'])):raise ValueError('TNS OFF has filters')
    return [(r['frame_index'],r['channel_index'],r['window_sequence'],r['window_shape'],r['mdct_hash']) for r in rows]

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'my_workspace/INPUT/data/abc_votay.wav')
    p.add_argument('--bitrate',type=int,default=64000)
    p.add_argument('--runs',type=int,default=10)
    p.add_argument('--profile-runs',type=int,default=10)
    p.add_argument('--output-dir',type=Path,default=ROOT/'my_workspace/psychoacoustic_model/experiments/psy')
    p.add_argument('--build-dir',type=Path,default=ROOT/'build/psy-experiments')
    p.add_argument('--baseline-build-dir',type=Path,default=ROOT/'build/psy-experiments-baseline')
    p.add_argument('--skip-build',action='store_true')
    p.add_argument('--no-plots',action='store_true')
    a=p.parse_args(argv)
    if a.bitrate!=64000:p.error('Controlled bitrate must be64000')
    if not 10<=a.runs<=1000 or not 1<=a.profile_runs<=1000:p.error('Require10..1000 main runs and1..1000 profile runs')
    a.input=a.input.resolve();folder=a.output_dir.resolve();a.build_dir=a.build_dir.resolve();a.baseline_build_dir=a.baseline_build_dir.resolve()
    suffix='.exe' if sys.platform=='win32' else ''
    binary=a.build_dir/('fdk_psy_experiment'+suffix);baseline=a.baseline_build_dir/('fdk_psy_experiment'+suffix)
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    run=folder/'runs'/run_id;run.mkdir(parents=True)
    for d in ('encoded','decoded','logs','results','plots'):(folder/d).mkdir(parents=True,exist_ok=True)
    status={'complete':False,'run_id':run_id,'input':str(a.input),'platform':platform.platform(),
            'target_bitrate_bps':64000,'runs':a.runs,'profile_runs':a.profile_runs,'decoder':'native FDK original FFT, limiter0/conceal method0',
            'timing':'steady_clock sum of aacEncEncode calls only;10+ fresh encoders per case; no trace/stage clocks',
            'window_experiment':False,'fft_experiment':False,'experiments':{}}
    status_path=folder/'results/pipeline_status.json';write_json(status_path,status)
    rows=[];individual=[];profiles=[]
    for experiment,mode,stem,tone,tns in CASES:
        row={key:'' for key in FIELDS}
        row.update(experiment_id=experiment,tonality_enabled='ON' if tone else 'OFF',tns_enabled='ON' if tns else 'OFF',
                   target_bitrate_kbps=64,runs=a.runs,profile_runs=a.profile_runs,run_id=run_id,status='NOT_RUN')
        rows.append(row);status['experiments'][experiment]=row
    try:
        # Only invalidate the aliases owned by this pipeline. Historical run directories remain intact.
        for experiment,mode,stem,tone,tns in CASES:
            for path in published_case_paths(folder,experiment,stem):path.unlink(missing_ok=True)
        for name in PLOT_NAMES:(folder/'plots'/name).unlink(missing_ok=True)
        for name in ('analysis.md','verification.json'):(folder/'results'/name).unlink(missing_ok=True)
        write_csv(folder/'results/psy_comparison.csv',rows,FIELDS)
        write_csv(folder/'results/psy_runs.csv',[],RUN_FIELDS)
        write_csv(folder/'results/psy_profile.csv',[],PROFILE_FIELDS)
        write_json(status_path,status)
        status['input_sha256']=digest(a.input)
        if not a.skip_build:
            build(a.build_dir,True,run/'build_research');build(a.baseline_build_dir,False,run/'build_baseline')
        status['binary_sha256']=digest(binary);status['baseline_binary_sha256']=digest(baseline)
        common=['--input',a.input,'--bitrate',64000]
        original=run/'original_baseline'
        invoke([baseline,*common,'--mode','BASELINE','--runs',1,'--profile-runs',1,'--output-dir',original],run/'baseline.log')
        bm=json.loads((original/'run_metadata.json').read_text())
        if not bm['complete'] or bm['controls_compiled']:raise ValueError('Baseline must be PSY_EXPERIMENT=OFF')
        probe=run/'native_probe'
        invoke([binary,*common,'--mode','BASELINE','--runs',1,'--profile-runs',1,'--output-dir',probe],run/'probe.log')
        pm=json.loads((probe/'run_metadata.json').read_text());expected_pns=pm['effective_pns_enabled']
        if (probe/'encoded.aac').read_bytes()!=(original/'encoded.aac').read_bytes():raise ValueError('Native-default research hooks change baseline bitstream')
        upstream=validate_trace(traces(probe/'psy_trace.csv'),pm,None,None,expected_pns)
        status['native_pns_enabled']=expected_pns;status['baseline_sha256']=digest(original/'encoded.aac')
        for case_index,(experiment,mode,stem,tone,tns) in enumerate(CASES):
            row=rows[case_index]
            native=run/stem
            publication=published_case_paths(folder,experiment,stem)
            try:
                invoke([binary,*common,'--mode',mode,'--runs',a.runs,'--profile-runs',a.profile_runs,'--expected-pns',expected_pns,'--output-dir',native],run/f'{experiment}.log')
                m=json.loads((native/'run_metadata.json').read_text())
                if not m['complete'] or not m['controls_compiled'] or m['main_timing_has_trace'] or m['main_timing_has_stage_clocks']:raise ValueError('Runner mode/timing boundary invalid')
                ts=traces(native/'psy_trace.csv')
                if validate_trace(ts,m,tone,tns,expected_pns)!=upstream:raise ValueError('Window/MDCT changed between cases')
                data=(native/'encoded.aac').read_bytes();adts=inspect_adts(data,inspect_ics=True)
                if (adts['sample_rate'],adts['channels'],adts['adts_frames'])!=(m['sample_rate'],m['channels'],m['adts_frames']):raise ValueError('ADTS configuration mismatch')
                ch0=[r for r in ts if int(r['channel_index'])==0]
                for packet,r in zip(adts['frames'],ch0):
                    if packet['window_shape']!=int(r['window_shape']):raise ValueError('Bitstream window shape differs from native trace')
                    if packet['window_sequence_id']!=['ONLY_LONG_SEQUENCE','LONG_START_SEQUENCE','EIGHT_SHORT_SEQUENCE','LONG_STOP_SEQUENCE'].index(r['window_sequence']):raise ValueError('Bitstream window sequence differs from trace')
                distortion,aligned=measure_files(a.input,native/'decoded.wav',m['encoder_delay_samples']+m['decoder_additional_delay_samples'])
                write_json(native/'distortion_alignment.json',distortion)
                if distortion['metric_status']!='ok':raise ValueError('NRMSE unavailable: '+distortion['metric_status'])
                times=m['encoding_time_ms']
                if len(times)!=a.runs or any(v<=0 for v in times):raise ValueError('Missing/nonpositive encode times')
                row.update(actual_bitrate_kbps=adts['actual_bitrate_kbps'],encoding_time_mean_ms=statistics.mean(times),encoding_time_std_ms=statistics.stdev(times),
                           encoding_time_min_ms=min(times),encoding_time_max_ms=max(times),mse=distortion['mse'],snr_db=distortion['snr_db'],
                           distortion_rate_percent=distortion['nrmse_percent'],aac_size_bytes=len(data),aac_size_kib=len(data)/1024,
                           coded_duration_seconds=adts['coded_duration_seconds'],source_duration_seconds=distortion['source_duration_seconds'],
                           adts_frames=adts['adts_frames'],sample_rate=m['sample_rate'],channels=m['channels'],effective_pns_enabled=expected_pns,
                           tonality_applied_frames=m['tonality_applied_frames'],encoder_tns_filters=m['encoder_tns_filters'],decoder_tns_filters=m['decoder_tns_filters'],
                           compared_samples_per_channel=distortion['compared_samples_per_channel'],alignment_delay_samples=distortion['alignment_delay_samples'],
                           alignment_correlation=distortion['alignment_correlation'],aac_sha256=digest(native/'encoded.aac'),status='PASS')
                if experiment=='EXP01':
                    row['baseline_identical']=data==(original/'encoded.aac').read_bytes()
                    if not row['baseline_identical']:raise ValueError('EXP01 differs from original baseline')
                case_runs=[dict(experiment_id=experiment,run_index=n,encoding_time_ms=value,aac_sha256=row['aac_sha256'],status='PASS',run_id=run_id) for n,value in enumerate(times)]
                case_profiles=[]
                with (native/'native_profile.csv').open() as f:
                    for r in csv.DictReader(f):case_profiles.append(dict(experiment_id=experiment,run_id=run_id,**r))
                if len(case_profiles)!=a.profile_runs:raise ValueError('Missing profile runs')
                staged=native/'publication_stage';staged.mkdir()
                sources=[native/name for name in ('encoded.aac','decoded.wav','psy_trace.csv','distortion_alignment.json')]
                for src,dst in zip(sources,publication):shutil.copy2(src,staged/dst.name)
                for dst in publication:(staged/dst.name).replace(dst)
                individual.extend(case_runs);profiles.extend(case_profiles)
                print(f"{experiment}: {row['actual_bitrate_kbps']:.3f} kb/s, {row['encoding_time_mean_ms']:.3f} +/- {row['encoding_time_std_ms']:.3f} ms, NRMSE {row['distortion_rate_percent']:.4f}%, {len(data)} bytes",flush=True)
            except NotImplementedError as exc:blank_failed_row(row,'UNSUPPORTED',exc);print(experiment+': '+str(exc),flush=True)
            except Exception as exc:blank_failed_row(row,'ERROR',exc);print(experiment+': ERROR '+str(exc),flush=True)
            if row['status']!='PASS':
                for path in publication:path.unlink(missing_ok=True)
            write_csv(folder/'results/psy_comparison.csv',rows,FIELDS)
            write_csv(folder/'results/psy_runs.csv',individual,RUN_FIELDS)
            write_csv(folder/'results/psy_profile.csv',profiles,PROFILE_FIELDS)
            write_json(status_path,status)
        if any(r['status']=='ERROR' for r in rows):return 1
        status['window_mdct_equal']=True
        status['tonality_pair_bitstreams_identical']={f'{x}/{y}':status['experiments'][x]['aac_sha256']==status['experiments'][y]['aac_sha256']
            for x,y in (('EXP01','EXP03'),('EXP02','EXP04')) if status['experiments'][x]['status']==status['experiments'][y]['status']=='PASS'}
        if expected_pns==0 and not all(status['tonality_pair_bitstreams_identical'].values()):raise ValueError('Unused tonality changed downstream output')
        if not a.no_plots:
            from plot_psy_results import plot_results
            plot_results(folder/'results/psy_comparison.csv',folder/'plots')
        from report_psy_results import report_results
        report_results(folder)
        changed=['CMakeLists.txt','libAACenc/src/encoder/aacenc.cpp','libAACenc/src/psy_model/psy_main.cpp','libAACenc/src/psy_model/aacenc_tns.cpp','libAACdec/src/aacdec_tns.cpp']
        status['source_sha256']={name:digest(ROOT/name) for name in changed+['libAACenc/src/psy_model/psy_experiment.cpp','libAACenc/src/psy_experiment.h','libFDK/src/mdct.cpp','libFDK/src/dct.cpp','libFDK/src/fft.cpp']}
        status['complete']=True;write_json(status_path,status)
        print('Measured results:',folder/'results/psy_comparison.csv')
        return 0
    except Exception as exc:
        status['error']=str(exc);write_json(status_path,status);print('ERROR:',exc,file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
