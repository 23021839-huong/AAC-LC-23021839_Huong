#!/usr/bin/env python3
"""Build/run/export the native FDK AAC-LC quantization survey."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[3]
STAGES=('form_factor','pe','bit_allocation','threshold','scalefactor','global_gain','quantization','iterations')


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
    return h.hexdigest()


def run(command):
    print('+ '+' '.join(map(str,command)),flush=True)
    subprocess.run(list(map(str,command)),cwd=ROOT,check=True)


def build(directory,debug,jobs,generator):
    command=['cmake','-S',ROOT,'-B',directory,'-DCMAKE_BUILD_TYPE=Release',
        '-DBUILD_SHARED_LIBS=OFF','-DBUILD_QUANT_TRACE=ON','-DQUANT_DEBUG='+('ON' if debug else 'OFF'),
        '-DPSY_DEBUG=OFF','-DMDCT_DEBUG=OFF']
    if generator:command+=['-G',generator]
    run(command);run(['cmake','--build',directory,'--target','fdk_quant_trace','--parallel',jobs])
    binary=directory/('fdk_quant_trace.exe' if os.name=='nt' else 'fdk_quant_trace')
    if not binary.is_file():binary=directory/'Release'/binary.name
    if not binary.is_file():raise ValueError('CMake did not produce fdk_quant_trace')
    return binary


def prepare_campaign(directory,overwrite,plot=False):
    directory=directory.resolve()
    if directory==ROOT or ROOT.is_relative_to(directory):raise ValueError('Workspace root/ancestor cannot be a result directory')
    if directory.exists() and any(directory.iterdir()):
        if not overwrite:raise ValueError(f'Output directory not empty: {directory}; choose a new campaign or --overwrite')
        marker=directory/('quant_plot_campaign.json' if plot else 'run_status.json')
        if not marker.is_file():raise ValueError('Refusing overwrite: directory is not an identified Quant campaign')
        owner=json.loads(marker.read_text(encoding='utf-8'))
        if plot and owner.get('provenance')!='native FDK-AAC QUANT_DEBUG' or not plot and not isinstance(owner.get('quant_debug'),bool):
            raise ValueError('Refusing overwrite: marker belongs to another workflow')
        backup=directory.with_name(directory.name+'.previous-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
        shutil.move(str(directory),str(backup))
        print('Previous campaign preserved at '+str(backup),flush=True)
    directory.mkdir(parents=True,exist_ok=True)


def audit_psy(directory,records,wav_hash,configuration):
    from quant_trace_data import group_records,find
    sys.path.insert(0, str(ROOT / 'my_workspace/psychoacoustic_model/tools'))
    from psy_trace_data import load_trace as load_psy,group_records as group_psy,find as find_psy
    manifest_path=directory/'survey_manifest.json'
    trace_path=directory/'native_trace.jsonl'
    if not manifest_path.is_file() or not trace_path.is_file():raise ValueError('Psy TXT alone lacks QC/adaptive state and audit metadata; native_trace.jsonl and survey_manifest.json plus --wav are required')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if not manifest.get('complete') or manifest.get('input_sha256')!=wav_hash:raise ValueError('Psy audit WAV/provenance mismatch')
    trace_hash=sha256(trace_path)
    if manifest.get('trace_sha256')!=trace_hash:raise ValueError('Psy trace hash/provenance mismatch with supplied manifest')
    config=manifest.get('configuration',{})
    for key in ('aot','bitrate','afterburner','bandwidth'):
        if config.get(key)!=configuration.get(key):raise ValueError(f'Psy audit configuration mismatch: {key}')
    psy=group_psy(load_psy(trace_path));checked=0;fields=set();unavailable={}
    names=('spectrum','offsets','energy','energy_ld','threshold_ld','min_snr_ld','spread_energy','noise_nrg','is_book','is_scale')
    for key,rs in group_records(records).items():
        if key not in psy:raise ValueError(f'Psy audit frame/channel missing: {key}')
        context=find(rs,'input','spectrum')
        for name,field in [('sfb_count','sfb_count'),('sfb_per_group','sfb_per_group'),
                           ('max_sfb_per_group','max_sfb_per_group'),('grouping_mask','grouping_mask')]:
            value=find_psy(psy[key],'output',name)
            if value is None or value['raw'][0]!=context[field]:raise ValueError(f'Psy geometry mismatch: {key} {name}')
            fields.add(name)
        for name in names:
            q=find(rs,'input',name);p=find_psy(psy[key],'output',name)
            if q is None or p is None or q['count']!=p['count']:raise ValueError(f'Psy interface missing/count mismatch: {key} {name}')
            if any(q[field]!=p[field] for field in ('exponent','fraction_bits','block_type','window_shape','sample_rate','frame_length')):raise ValueError(f'Psy scaling/window mismatch: {key} {name}')
            pvalid=set(p.get('valid_indices',range(p['count'])))
            # QC only reads coded/initialized bands; Psy may additionally expose other valid zero bands.
            for i in q['valid_indices']:
                if i not in pvalid or q['raw'][i]!=p['raw'][i]:raise ValueError(f'Psy raw/mask mismatch: {key} {name}[{i}]')
                checked+=1
            fields.add(name)
        stereo=find(rs,'input','ms_mask') is not None
        for name in ('common_window','ms_digest'):
            q=find(rs,'input',name);p=find_psy(psy[key],'output',name)
            if q is None:
                if stereo:raise ValueError(f'Psy stereo interface mismatch: missing {name}')
                continue
            if p is None:
                if stereo:raise ValueError(f'Psy stereo interface mismatch: missing {name}')
                unavailable[name]='Existing Psy producer does not export mono stereo-tool fields; no equality claim for this field.'
                continue
            if q['raw']!=p['raw']:raise ValueError(f'Psy tool mismatch: {key} {name}')
            checked+=1;fields.add(name)
        if find(rs,'input','ms_mask'):
            q=find(rs,'input','ms_mask');p=find_psy(psy[key],'output','ms_mask')
            if p is None or q['count']!=p['count'] or any(i not in p.get('valid_indices',range(p['count'])) or q['raw'][i]!=p['raw'][i] for i in q['valid_indices']):raise ValueError('Psy MS mask mismatch')
            checked+=len(q['valid_indices']);fields.add('ms_mask')
        for q in [r for r in rs if r['stage']=='input' and r['name']=='tns_num_filters']:
            matches=[r for r in psy[key] if r['stage']=='tns' and r['name']=='final.num_filters' and r['window']==q['index']]
            if not matches or matches[-1]['raw']!=q['raw']:raise ValueError('Psy TNS audit requires matching final TNS trace')
            checked+=1;fields.add('tns_num_filters')
        for q in [r for r in rs if r['stage']=='input' and r['name']=='tns_coef_res']:
            matches=[r for r in psy[key] if r['stage']=='tns' and r['name']=='final.coef_res' and r['window']==q['index']]
            if not matches or matches[-1]['raw']!=q['raw']:raise ValueError('Psy TNS coefficient resolution mismatch')
            checked+=1;fields.add('tns_coef_res')
        for q in [r for r in rs if r['stage']=='input' and r['name'] in ('tns_order','tns_length','tns_direction','tns_coefficients')]:
            # FDK TNS_INFO has MAX_NUM_OF_FILTERS=2; producer records filter IDs as window*2+filter.
            window,filter_id=divmod(q['index'],2)
            name={'tns_order':'final.order','tns_length':'final.length','tns_direction':'final.direction','tns_coefficients':'final.quantized_coef'}[q['name']]
            matches=[r for r in psy[key] if r['stage']=='tns' and r['name']==name and r['window']==window and r.get('filter')==filter_id]
            if not matches or matches[-1]['raw']!=q['raw']:raise ValueError('Psy TNS parameter mismatch')
            checked+=q['count'];fields.add(q['name'])
    unavailable['tns_coef_compress']='Writer-only decision observed in Quant final/tns_write; existing Psy producer has no writer event.'
    return dict(matched=True,checked_raw_values=checked,source=str(directory),
        psy_trace_sha256=trace_hash,trace_hash_verified=True,checked_fields=sorted(fields),
        unavailable_fields=unavailable,match_scope='Only fields listed in checked_fields; not a full-state checkpoint',
        mode='Audit of native Psy/QC interface; no standalone replay')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wav',type=Path)
    p.add_argument('--input',type=Path,help='Psy campaign to audit; requires WAV, not an independent QC checkpoint')
    selection=p.add_mutually_exclusive_group();selection.add_argument('--frame',type=int);selection.add_argument('--frames')
    p.add_argument('--channel',default='0');p.add_argument('--bitrate',type=int)
    p.add_argument('--sample-rate',type=int);p.add_argument('--bandwidth',type=int)
    p.add_argument('--afterburner',type=int,choices=(0,1),default=1)
    p.add_argument('--stages',default='all');p.add_argument('--no-iteration-log',action='store_true')
    p.add_argument('--line-trace',action='store_true');p.add_argument('--overwrite',action='store_true')
    p.add_argument('--output-dir',type=Path,default=ROOT/'my_workspace/quantization_coding/output/quant')
    p.add_argument('--plots-dir',type=Path,default=ROOT/'my_workspace/quantization_coding/plots/quant')
    p.add_argument('--build-dir',type=Path,default=ROOT/'build');p.add_argument('--binary',type=Path)
    p.add_argument('--normal-binary',type=Path);p.add_argument('--skip-build',action='store_true')
    p.add_argument('--verify-bitstream',action='store_true');p.add_argument('--no-plots',action='store_true')
    p.add_argument('--plot-frame',type=int);p.add_argument('--generator',default='Ninja' if shutil.which('ninja') else None)
    p.add_argument('--jobs',type=int,default=min(4,os.cpu_count() or 1))
    a=p.parse_args(argv)
    if a.input and not a.wav:p.error('Psy TXT does not contain complete QC/internal state. Supply --wav for native interface audit; standalone replay is not supported.')
    manifest=None
    try:
        if a.frames:
            parts=a.frames.split(':')
            if len(parts)!=2:raise ValueError('frames must be START:END')
            first,end=map(int,parts)
        else:first=a.frame if a.frame is not None else 0;end=first+1
        if not 0<=first<end<=2147483647:raise ValueError('Invalid frame range')
        if a.channel not in ('0','1','all'):raise ValueError('channel must be 0, 1 or all')
        if any(s not in STAGES+('all',) for s in a.stages.split(',')):raise ValueError('Unknown/empty stage')
        if a.jobs<1 or a.bitrate is not None and a.bitrate<=0:raise ValueError('Invalid jobs/bitrate')
        wav=(a.wav or ROOT/'my_workspace/INPUT/data/abc_votay.wav').resolve()
        if not wav.is_file():raise ValueError('WAV not found: '+str(wav))
        out=a.output_dir.resolve();plots=a.plots_dir.resolve();build_dir=a.build_dir.resolve()
        if wav.is_relative_to(out) or a.input and (a.input.resolve().is_relative_to(out) or out.is_relative_to(a.input.resolve())):
            raise ValueError('Result directory must not overlap WAV/Psy input')
        if not a.no_plots and (out.is_relative_to(plots) or wav.is_relative_to(plots) or
                a.input and (a.input.resolve().is_relative_to(plots) or plots.is_relative_to(a.input.resolve()))):
            raise ValueError('Plots directory must not overlap/contain output or WAV/Psy input')
        # Check destinations before building; overwrite only identified, recoverable campaigns.
        if out.exists() and any(out.iterdir()) and not a.overwrite:raise ValueError('Output directory not empty: '+str(out))
        if not a.no_plots and plots.exists() and any(plots.iterdir()) and not a.overwrite:raise ValueError('Plots directory not empty: '+str(plots))
        prepare_campaign(out,a.overwrite)
        manifest=dict(complete=False,provenance='native FDK-AAC QUANT_DEBUG',source=str(wav),input_sha256=sha256(wav),
            selection=dict(first=first,end=end,channel=a.channel),platform=platform.platform(),python=sys.version)
        (out/'survey_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        executable='fdk_quant_trace.exe' if os.name=='nt' else 'fdk_quant_trace'
        binary=a.binary.resolve() if a.binary else build_dir/'quant-analysis-debug'/executable
        if not a.skip_build and not a.binary:binary=build(build_dir/'quant-analysis-debug',True,a.jobs,a.generator)
        if not binary.is_file():raise ValueError('Instrumented runner missing; build or supply --binary')
        options=['--wav',wav,'--frames',f'{first}:{end}','--channel',a.channel,
                 '--afterburner',a.afterburner,'--stages',a.stages]
        for key in ('bitrate','sample_rate','bandwidth'):
            value=getattr(a,key)
            if value is not None:options+=['--'+key.replace('_','-'),value]
        if a.no_iteration_log:options+=['--no-iteration-log']
        if a.line_trace:options+=['--line-trace']
        if a.verify_bitstream:options+=['--decode-check']
        # Manifest exists already; native overwrite only touches known native files.
        run([binary,*options,'--output-dir',out,'--overwrite'])
        status=json.loads((out/'run_status.json').read_text())
        if not status.get('complete') or not status.get('quant_debug') or not status.get('trace_enabled'):raise ValueError('Expected completed QUANT_DEBUG native runner with trace')
        from analyze_quant_outputs import export
        from quant_trace_data import load_trace
        report=export(out/'native_trace.jsonl',out)
        info=json.loads((out/'input_info.json').read_text())
        config=dict(aot=2,frame_length=1024,bitrate=info['bitrate'],bandwidth=a.bandwidth,
                    afterburner=a.afterburner,stages=a.stages,iteration_log=not a.no_iteration_log,line_log=a.line_trace)
        manifest.update(configuration=config,binary=str(binary),binary_sha256=sha256(binary),
            encoded_sha256=sha256(out/'encoded.aac'),trace_sha256=sha256(out/'native_trace.jsonl'),
            frame_channel_pairs=len(report['frames']),decoded_packets=status.get('decoded_packets'))
        if a.input:manifest['psy_audit']=audit_psy(a.input.resolve(),load_trace(out/'native_trace.jsonl'),manifest['input_sha256'],config)
        if a.verify_bitstream:
            normal=a.normal_binary.resolve() if a.normal_binary else build_dir/'quant-analysis-normal'/executable
            if not a.skip_build and not a.normal_binary:normal=build(build_dir/'quant-analysis-normal',False,a.jobs,a.generator)
            if not normal.is_file():raise ValueError('Independent normal runner missing')
            reference=out/'normal_reference';run([normal,*options,'--output-dir',reference])
            normal_status=json.loads((reference/'run_status.json').read_text())
            if not normal_status.get('complete') or normal_status.get('quant_debug'):raise ValueError('Normal reference must be an independent QUANT_DEBUG=OFF build')
            no_trace=out/'debug_no_trace_reference';run([binary,*options,'--no-trace','--output-dir',no_trace])
            same=(out/'encoded.aac').read_bytes()==(reference/'encoded.aac').read_bytes()==(no_trace/'encoded.aac').read_bytes()
            manifest['bitstream_comparison']=dict(identical=same,normal_binary_sha256=sha256(normal),
                normal_encoded_sha256=sha256(reference/'encoded.aac'),debug_no_trace_encoded_sha256=sha256(no_trace/'encoded.aac'))
            if not same:raise ValueError('Instrumentation changed native AAC bitstream')
        if not a.no_plots:
            from plot_quant_stages import plot
            prepare_campaign(plots,a.overwrite,plot=True)
            manifest['plots']=[plot(out/'native_trace.jsonl',plots/(f'channel_{ch}' if a.channel=='all' else ''),a.plot_frame,ch)
                               for ch in sorted({r['channel'] for r in report['frames']})]
            (plots/'quant_plot_campaign.json').write_text(json.dumps(dict(source=str(out),complete=True,provenance='native FDK-AAC QUANT_DEBUG'),indent=2),encoding='utf-8')
        source_paths=[ROOT/'CMakeLists.txt',ROOT/'my_workspace/quantization_coding/run_quant_analysis.sh']
        source_paths+=list((ROOT/'libAACenc').rglob('*.cpp'))+list((ROOT/'libAACenc').rglob('*.h'))
        source_paths+=list((ROOT/'libFDK/include').rglob('*.h'))+list((ROOT/'libFDK/src').glob('*.cpp'))
        source_paths+=list((ROOT/'my_workspace/quantization_coding/tools').glob('*quant*.py'))+[ROOT/'my_workspace/quantization_coding/tools/fdk_quant_trace.cpp',ROOT/'my_workspace/fdk_model_testing/tools/wav_pcm.cpp']
        manifest['source_sha256']={str(path.relative_to(ROOT)).replace('\\','/'):sha256(path) for path in sorted(set(source_paths))}
        manifest['source_hash_role']='Workspace at survey time; externally supplied binaries require source-to-binary provenance from their build.'
        cache=binary.parent/'CMakeCache.txt'
        if not cache.is_file():cache=binary.parent.parent/'CMakeCache.txt'
        if cache.is_file():
            settings={}
            for line in cache.read_text(encoding='utf-8').splitlines():
                if line.startswith(('CMAKE_CXX_COMPILER:','CMAKE_CXX_FLAGS:','CMAKE_CXX_FLAGS_RELEASE:','CMAKE_BUILD_TYPE:','QUANT_DEBUG:','PSY_DEBUG:','CMAKE_GENERATOR:')):
                    name,value=line.split('=',1);settings[name]=value
            manifest['build_profile']=dict(cache_sha256=sha256(cache),settings=settings)
        ref=ROOT/'.git/refs/heads/master'
        manifest['checkout_master_ref']=ref.read_text().strip() if ref.is_file() else None
        manifest['complete']=True
        (out/'survey_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(f"Survey complete: {len(report['frames'])} frame/channel pairs; output {out}")
    except (OSError,ValueError,KeyError,ImportError,subprocess.CalledProcessError) as e:
        if manifest is not None:
            manifest['complete']=False;manifest['error']=str(e)
            (a.output_dir.resolve()/'survey_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        p.exit(1,f'Error: {e}\n')
    return 0


if __name__=='__main__':sys.exit(main())
