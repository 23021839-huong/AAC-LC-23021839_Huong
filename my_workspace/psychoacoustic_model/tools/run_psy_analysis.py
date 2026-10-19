#!/usr/bin/env python3
"""Build, run and visualize the original FDK AAC-LC psychoacoustic pipeline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run(command, cwd=ROOT):
    print('+ ' + ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=cwd, check=True)


def build(directory, debug, jobs, generator):
    command = ['cmake', '-S', ROOT, '-B', directory, '-DCMAKE_BUILD_TYPE=Release',
               '-DBUILD_SHARED_LIBS=OFF', '-DBUILD_PSY_TRACE=ON',
               '-DPSY_DEBUG=' + ('ON' if debug else 'OFF')]
    if generator:
        command += ['-G', generator]
    run(command)
    run(['cmake', '--build', directory, '--target', 'fdk_psy_trace', '--parallel', jobs])
    binary = directory / ('fdk_psy_trace.exe' if os.name == 'nt' else 'fdk_psy_trace')
    if not binary.is_file():
        binary = directory / 'Release' / binary.name
    if not binary.is_file():
        raise ValueError('CMake did not create fdk_psy_trace')
    return binary


def audit_mdct(path, metadata_path, exponents_path, records):
    import numpy as np
    from psy_trace_data import find, group_records
    parent = path.parent
    meta_path = metadata_path or parent / 'stage_metadata.json'
    exp_path = exponents_path or parent / '05_mdct_exponents.txt'
    if not meta_path.is_file() or not exp_path.is_file():
        raise ValueError('MDCT audit requires stage_metadata.json and 05_mdct_exponents.txt; coefficients alone are insufficient')
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    key = (meta['selected_frame'], meta['channel'])
    groups = group_records(records)
    if key not in groups:
        raise ValueError(f'MDCT metadata selects frame/channel {key}, outside the requested trace')
    raw = np.loadtxt(path, dtype=np.int64, ndmin=2)
    exp = np.loadtxt(exp_path, dtype=np.int64, ndmin=2)
    mdct = find(groups[key], 'mdct', 'input')
    for table in (raw, exp):
        if table.shape != (1024, 2) or not np.array_equal(table[:, 0], np.arange(1024)):
            raise ValueError('MDCT raw/exponent file must contain 1024 ordered index/value rows')
    if not np.array_equal(raw[:, 1], mdct['raw']) or not np.all(exp[:, 1] == mdct['exponent']):
        raise ValueError('External MDCT raw coefficients/exponent differ from the native interface; check WAV/frame/configuration')
    if meta['block_type'] != ('LONG', 'START', 'SHORT', 'STOP')[mdct['block_type']]:
        raise ValueError('External MDCT window sequence differs from native interface')
    if meta['window_shape'] != ('SINE', 'KBD')[mdct['window_shape']]:
        raise ValueError('External MDCT window shape differs from native interface')
    return dict(matched=True, frame=key[0], channel=key[1], coefficient_count=1024,
                path=str(path), sha256=sha256(path), mode='audit against native encoder; not independent replay')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wav', type=Path, help='PCM WAV through native encoder (default input/abc_votay.wav)')
    p.add_argument('--input', type=Path, help='Existing MDCT text to audit; requires --wav and companion metadata/state-producing encode')
    p.add_argument('--mdct-metadata', type=Path)
    p.add_argument('--mdct-exponents', type=Path)
    selection = p.add_mutually_exclusive_group()
    selection.add_argument('--frame', type=int)
    selection.add_argument('--frames', help='START:END, end-exclusive native frame range')
    p.add_argument('--channel', default='0', help='zero-based channel or all')
    p.add_argument('--sample-rate', type=int, help='assert WAV sample rate; never resample')
    p.add_argument('--bitrate', type=int, help='total CBR bps; default 64000*channels')
    p.add_argument('--bandwidth', type=int)
    p.add_argument('--afterburner', type=int, choices=(0, 1), default=1)
    p.add_argument('--stages', default='all', help='all or comma-separated sfb,energy,masking,tonality,tns,pns; controls debug only')
    p.add_argument('--output-dir', type=Path, default=ROOT/'my_workspace/psychoacoustic_model/output/psy')
    p.add_argument('--plots-dir', type=Path, default=ROOT/'my_workspace/psychoacoustic_model/plots/psy')
    p.add_argument('--build-dir', type=Path, default=ROOT/'build')
    p.add_argument('--binary', type=Path)
    p.add_argument('--normal-binary', type=Path)
    p.add_argument('--skip-build', action='store_true')
    p.add_argument('--verify-bitstream', action='store_true')
    p.add_argument('--no-plots', action='store_true')
    p.add_argument('--plot-frame', type=int, help='default highest total-energy selected frame per channel')
    p.add_argument('--plot-window', type=int, default=0)
    p.add_argument('--generator', default='Ninja' if shutil.which('ninja') else None)
    p.add_argument('--jobs', type=int, default=min(4, os.cpu_count() or 1))
    a = p.parse_args(argv)
    if a.input and not a.wav:
        p.error('MDCT text does not include complete Psy configuration/history/grouping. Supply --wav and a matching frame for native-interface audit; standalone replay is not supported.')
    a.wav = (a.wav or ROOT/'my_workspace/INPUT/data/abc_votay.wav').resolve()
    a.output_dir = a.output_dir.resolve()
    a.plots_dir = a.plots_dir.resolve()
    a.build_dir = a.build_dir.resolve()
    try:
        if a.frames:
            parts = a.frames.split(':')
            if len(parts) != 2:
                raise ValueError('frames must be START:END')
            first, end = map(int, parts)
        else:
            first = a.frame if a.frame is not None else 0
            end = first+1
        if not 0 <= first < end <= 2147483647 or a.jobs < 1:
            raise ValueError('invalid frame range/jobs')
        if a.channel != 'all' and a.channel not in ('0', '1'):
            raise ValueError('channel must be 0, 1 or all')
        if any(s not in ('all', 'sfb', 'energy', 'masking', 'tonality', 'tns', 'pns') for s in a.stages.split(',')):
            raise ValueError('unknown/empty debug stage')
        if not a.wav.is_file():
            raise ValueError('WAV not found: ' + str(a.wav))
        executable = 'fdk_psy_trace.exe' if os.name == 'nt' else 'fdk_psy_trace'
        binary = a.binary.resolve() if a.binary else a.build_dir/'psy-analysis-debug'/executable
        if not a.skip_build and not a.binary:
            binary = build(a.build_dir/'psy-analysis-debug', True, a.jobs, a.generator)
        if not binary.is_file():
            raise ValueError('instrumented runner not found; build first or set --binary')
        options = ['--input', a.wav, '--frames', f'{first}:{end}', '--channel', a.channel,
                   '--afterburner', a.afterburner, '--stages', a.stages]
        for name in ('sample_rate', 'bitrate', 'bandwidth'):
            value = getattr(a, name)
            if value is not None:
                options += ['--'+name.replace('_', '-'), value]
        a.output_dir.mkdir(parents=True, exist_ok=True)
        # Prevent a normal or failed run from leaving an old successful trace/manifest.
        for name in ('native_trace.jsonl', 'survey_manifest.json', 'validation.json'):
            (a.output_dir/name).unlink(missing_ok=True)
        run([binary, *options, '--output-dir', a.output_dir])
        status = json.loads((a.output_dir/'run_status.json').read_text(encoding='utf-8'))
        if not status['complete'] or not status['psy_debug']:
            raise ValueError('runner is not a completed PSY_DEBUG build')
        from analyze_psy_outputs import export
        from psy_trace_data import load_trace
        trace = a.output_dir/'native_trace.jsonl'
        report = export(trace, a.output_dir)
        input_info = json.loads((a.output_dir/'input_info.json').read_text(encoding='utf-8'))
        manifest = dict(complete=True, source=str(a.wav), input_sha256=sha256(a.wav),
                        binary=str(binary), binary_sha256=sha256(binary),
                        encoded_sha256=sha256(a.output_dir/'encoded.aac'),
                        trace_sha256=sha256(trace), selection=dict(first=first, end=end, channel=a.channel),
                        configuration=dict(aot=2, frame_length=1024, bitrate=a.bitrate or 64000*input_info['channels'],
                                           bandwidth=a.bandwidth, afterburner=a.afterburner, stages=a.stages),
                        platform=platform.platform(), python=sys.version,
                        frame_channel_pairs=len(report['frames']))
        if a.input:
            manifest['mdct_audit'] = audit_mdct(a.input.resolve(), a.mdct_metadata, a.mdct_exponents, load_trace(trace))
        if a.verify_bitstream:
            normal = a.normal_binary.resolve() if a.normal_binary else a.build_dir/'psy-analysis-normal'/executable
            if not a.skip_build and not a.normal_binary:
                normal = build(a.build_dir/'psy-analysis-normal', False, a.jobs, a.generator)
            reference = a.output_dir/'normal_reference'
            run([normal, *options, '--output-dir', reference])
            normal_status = json.loads((reference/'run_status.json').read_text(encoding='utf-8'))
            if not normal_status['complete'] or normal_status['psy_debug']:
                raise ValueError('Normal reference must be a completed PSY_DEBUG=OFF runner, not another debug binary')
            equal = (a.output_dir/'encoded.aac').read_bytes() == (reference/'encoded.aac').read_bytes()
            manifest['bitstream_comparison'] = dict(identical=equal, normal_binary_sha256=sha256(normal),
                                                   normal_encoded_sha256=sha256(reference/'encoded.aac'))
            if not equal:
                raise ValueError('instrumentation changed AAC bitstream')
        if not a.no_plots:
            from plot_psy_stages import plot
            channels = sorted({r['channel'] for r in report['frames']})
            manifest['plots'] = [plot(trace, a.plots_dir/(f'channel_{ch}' if len(channels)>1 else ''),
                                      a.plot_frame, ch, a.plot_window) for ch in channels]
        source_paths = ['CMakeLists.txt', 'libAACenc/src/psy_debug.h', 'libAACenc/src/psy_debug_api.h',
                        'libAACenc/src/psy_model/psy_debug.cpp', 'libAACenc/src/encoder/aacenc.cpp']
        source_paths += ['libAACenc/src/psy_model/'+name+'.cpp' for name in
                         ('psy_main', 'band_nrg', 'tonality', 'aacenc_tns', 'aacenc_pns', 'noisedet')]
        manifest['source_sha256'] = {name: sha256(ROOT/name) for name in source_paths}
        (a.output_dir/'survey_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(f"Survey complete: {len(report['frames'])} frame/channel pairs. Outputs: {a.output_dir}")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        p.exit(1, f'Error: {exc}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
