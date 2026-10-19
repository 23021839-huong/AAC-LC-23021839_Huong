"""Run native four-case Psy tests on 1..20 verified WAVs of variable duration."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import uuid
import wave

from run_psy_experiments import ROOT, CASES, FIELDS, PROFILE_FIELDS, RUN_FIELDS, build, write_csv, write_json
from run_psy_input_suite import EXTRA_FIELDS, read_csv

EXTRA = EXTRA_FIELDS + ['encode_ms_per_source_second', 'encoding_real_time_factor']


def load_manifest(path):
    manifest = json.loads(path.read_text(encoding='utf-8'))
    entries = manifest.get('inputs', [])
    if not manifest.get('complete') or not 1 <= len(entries) <= 20:
        raise ValueError('Require complete manifest with 1..20 inputs')
    ids = [entry['input_id'] for entry in entries]
    if len(set(ids)) != len(ids) or any(not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in name) for name in ids):
        raise ValueError('Invalid or duplicate input ID')
    base = path.parent.resolve()
    for entry in entries:
        source = (base/entry['filename']).resolve()
        if source.parent != base or source.suffix.lower() != '.wav':
            raise ValueError('Input must be a WAV directly within manifest folder')
        if hashlib.sha256(source.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Input hash changed: '+entry['input_id'])
        with wave.open(str(source), 'rb') as w:
            if (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getcomptype()) != (48000, 1, 2, 'NONE'):
                raise ValueError('Require PCM16 mono 48 kHz: '+entry['input_id'])
            frames = w.getnframes()
            if len(w.readframes(frames)) != frames*2:
                raise ValueError('Truncated WAV: '+entry['input_id'])
            if not 10 <= frames/48000 <= 300 or abs(frames/48000-entry['duration_seconds']) > 1/48000:
                raise ValueError('Duration mismatch or outside10..300 s: '+entry['input_id'])
    return manifest


def summarize(output, rows, entries):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    text = ['# Khảo sát bổ sung theo input', '', f"{len(entries)} WAV × 4 chế độ = {len(rows)} case.", '',
            '| Input | Giây | TNS ON NRMSE % | TNS OFF NRMSE % | TNS dùng % | ON ms/s | OFF ms/s |',
            '|---|---:|---:|---:|---:|---:|---:|']
    for entry in entries:
        a, b = [next(row for row in rows if row['input_id']==entry['input_id'] and row['experiment_id']==case) for case in ('EXP01', 'EXP02')]
        if a['status'] == b['status'] == 'PASS':
            fraction = 100*int(a['tns_applied_frame_channels'])/int(a['total_frame_channels'])
            text.append(f"| {entry['input_id']} | {entry['duration_seconds']:g} | {float(a['distortion_rate_percent']):.5f} | {float(b['distortion_rate_percent']):.5f} | {fraction:.2f} | {float(a['encode_ms_per_source_second']):.3f} | {float(b['encode_ms_per_source_second']):.3f} |")
        else:
            text.append(f"| {entry['input_id']} | {entry['duration_seconds']:g} | {a['status']} | {b['status']} | — | — | — |")
    text += ['', 'So ON/OFF trong cùng WAV. Độ dài khác nhau: ms/s và RTF giúp so chi phí; SD vẫn nằm trong CSV. '
             'NRMSE không thay thế phép nghe/pre-echo. PNS theo cấu hình native; không giả lập PNS ON/OFF. '
             'Tonality ON khi PNS OFF chỉ đo chạy/bypass estimator, chưa đo lợi ích perceptual của consumer PNS.', '']
    (output/'summary.md').write_text('\n'.join(text), encoding='utf-8')
    # Five inputs per page keep labels readable for 15..20 inputs.
    for page, start in enumerate(range(0, len(entries), 5), 1):
        selected = entries[start:start+5]; x = np.arange(len(selected)); fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout='constrained')
        for i, (case, *_rest) in enumerate(CASES):
            group = [next(r for r in rows if r['input_id']==e['input_id'] and r['experiment_id']==case) for e in selected]
            indices = [j for j, r in enumerate(group) if r['status']=='PASS']
            for ax, field, units in [(axes[0], 'distortion_rate_percent', 'Aligned NRMSE (%)'), (axes[1], 'encode_ms_per_source_second', 'Encode-only ms / source second')]:
                ax.bar(x[indices]+(i-1.5)*.18, [float(group[j][field]) for j in indices], .18, label=case)
                ax.set(ylabel=units, xticks=x, xticklabels=[e.get('short_label', e['input_id']) for e in selected]); ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
        axes[0].legend(ncol=4); fig.suptitle(f'Input effects / page {page} / native AAC-LC64kb/s')
        fig.savefig(output/f'input_effects_{page:02d}.png', dpi=150); plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT/'my_workspace/psychoacoustic_model/input/psy_external_extended/manifest.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'my_workspace/psychoacoustic_model/experiments/psy_extended')
    parser.add_argument('--input-ids', help='Comma-separated subset of manifest input IDs')
    parser.add_argument('--runs', type=int, default=10)
    parser.add_argument('--profile-runs', type=int, default=10)
    parser.add_argument('--build-dir', type=Path, default=ROOT/'build/psy-experiments')
    parser.add_argument('--baseline-build-dir', type=Path, default=ROOT/'build/psy-experiments-baseline')
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv)
    if not 10 <= args.runs <= 1000 or not 1 <= args.profile_runs <= 1000:
        parser.error('Require10..1000 main runs and1..1000 profile runs')
    path = args.manifest.resolve()
    try:
        manifest = load_manifest(path)
        entries = manifest['inputs']
        if args.input_ids:
            requested = args.input_ids.split(',')
            if len(set(requested)) != len(requested) or set(requested)-{e['input_id'] for e in entries}:
                raise ValueError('Unknown or duplicate input IDs')
            entries = [e for e in entries if e['input_id'] in requested]
        print(f"Validated {len(manifest['inputs'])} input WAVs; selected {len(entries)} ({sum(e['duration_seconds'] for e in entries):g} source seconds)", flush=True)
        if args.validate_only:
            return 0
    except Exception as exc:
        print('ERROR:', exc, file=sys.stderr); return 1
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    campaign = output/'campaigns'/run_id; campaign.mkdir(parents=True)
    status = dict(complete=False, run_id=run_id, manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  selected_inputs=[e['input_id'] for e in entries], expected_cases=4*len(entries), cases={})
    status_path = output/'suite_status.json'; write_json(status_path, status)
    rows, runs, profiles = [], [], []
    for name in ('summary.md', *[f'input_effects_{i:02d}.png' for i in range(1, 5)]): (output/name).unlink(missing_ok=True)
    write_csv(output/'suite_comparison.csv', rows, EXTRA+FIELDS)
    write_csv(output/'suite_runs.csv', runs, ['input_id', *RUN_FIELDS])
    write_csv(output/'suite_profile.csv', profiles, ['input_id', *PROFILE_FIELDS])
    try:
        if not args.skip_build:
            build(args.build_dir.resolve(), True, campaign/'build_research')
            build(args.baseline_build_dir.resolve(), False, campaign/'build_baseline')
        for entry in entries:
            name = entry['input_id']; child = campaign/name
            print(f"Starting {name}: {entry['duration_seconds']:g} s", flush=True)
            command = [sys.executable, ROOT/'my_workspace/psychoacoustic_model/experiments/psy/scripts/run_psy_experiments.py', '--input', path.parent/entry['filename'],
                       '--output-dir', child, '--runs', args.runs, '--profile-runs', args.profile_runs, '--skip-build',
                       '--build-dir', args.build_dir.resolve(), '--baseline-build-dir', args.baseline_build_dir.resolve()]
            process = subprocess.run(list(map(str, command)), capture_output=True, text=True)
            (campaign/(name+'.log')).write_text(process.stdout+process.stderr, encoding='utf-8')
            print(process.stdout, end='', flush=True)
            child_rows = read_csv(child/'results/psy_comparison.csv')
            child_status = json.loads((child/'results/pipeline_status.json').read_text(encoding='utf-8'))
            for row in child_rows:
                row.update(input_id=name, input_label=entry['label'], source_kind=entry['source_kind'], input_sha256=entry['sha256'], case_directory=str(child))
                for key in EXTRA[5:]: row[key] = ''
                if row['status'] == 'PASS':
                    trace = read_csv(child/'logs'/f"{row['experiment_id'].lower()}_psy_trace.csv")
                    tone = [float(t['tonality_value']) for t in trace if t['tonality_value']]
                    row.update(tns_present_frame_channels=sum(int(t['tns_filter_count'])>0 for t in trace),
                               tns_applied_frame_channels=sum(int(t['tns_applied']) for t in trace),
                               short_frame_channels=sum(t['window_sequence']=='EIGHT_SHORT_SEQUENCE' for t in trace),
                               total_frame_channels=len(trace), mean_logged_tonality=statistics.mean(tone) if tone else '',
                               encode_ms_per_source_second=float(row['encoding_time_mean_ms'])/entry['duration_seconds'],
                               encoding_real_time_factor=float(row['encoding_time_mean_ms'])/1000/entry['duration_seconds'])
                rows.append(row)
            runs.extend(dict(input_id=name, **r) for r in read_csv(child/'results/psy_runs.csv'))
            profiles.extend(dict(input_id=name, **r) for r in read_csv(child/'results/psy_profile.csv'))
            status['cases'][name] = dict(complete=child_status['complete'], returncode=process.returncode,
                                        case_directory=str(child), statuses={r['experiment_id']:r['status'] for r in child_rows})
            write_csv(output/'suite_comparison.csv', rows, EXTRA+FIELDS)
            write_csv(output/'suite_runs.csv', runs, ['input_id', *RUN_FIELDS])
            write_csv(output/'suite_profile.csv', profiles, ['input_id', *PROFILE_FIELDS]); write_json(status_path, status)
        summarize(output, rows, entries)
        if len(rows) != 4*len(entries) or any(r['status'] != 'PASS' for r in rows) or any(not c['complete'] or c['returncode'] for c in status['cases'].values()):
            raise ValueError('Some cases did not pass; inspect CSV/status. Missing metrics remain blank.')
        status.update(complete=True, passed_cases=len(rows), main_runs=len(runs), profile_runs=len(profiles))
        write_json(status_path, status); print('Completed:', output/'suite_comparison.csv'); return 0
    except Exception as exc:
        status['error'] = str(exc); write_json(status_path, status); print('ERROR:', exc, file=sys.stderr); return 1


if __name__ == '__main__':
    raise SystemExit(main())
