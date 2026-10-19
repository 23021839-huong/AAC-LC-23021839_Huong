"""Run the existing native four-case pipeline separately for each prepared WAV."""
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

from run_psy_experiments import ROOT, CASES, FIELDS, PROFILE_FIELDS, RUN_FIELDS, build, write_csv, write_json

EXTRA_FIELDS = ['input_id', 'input_label', 'source_kind', 'input_sha256', 'case_directory',
                'tns_present_frame_channels', 'tns_applied_frame_channels', 'short_frame_channels',
                'total_frame_channels', 'mean_logged_tonality']


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def summarize(output, rows, manifest):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    ids = [entry['input_id'] for entry in manifest['inputs']]
    labels = [entry.get('short_label', entry['input_id'].replace('_', '\n', 1)) for entry in manifest['inputs']]
    colors = ['#2775ad', '#e19b36', '#7560a5', '#288866']
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), layout='constrained')
    x = np.arange(len(ids))
    for case_index, (case, _, _, _, _) in enumerate(CASES):
        selected = [next(r for r in rows if r['input_id']==name and r['experiment_id']==case) for name in ids]
        for ax, field, title, units in [(axes[0, 0], 'distortion_rate_percent', 'Full-file aligned NRMSE', '%'),
                                         (axes[0, 1], 'encoding_time_mean_ms', 'Encode-only mean and sample SD', 'ms')]:
            valid = [i for i, r in enumerate(selected) if r['status']=='PASS']
            values = [float(selected[i][field]) for i in valid]
            err = [float(selected[i]['encoding_time_std_ms']) for i in valid] if field.startswith('encoding') else None
            ax.bar(x[valid] + (case_index-1.5)*.18, values, .18, label=case, color=colors[case_index],
                   yerr=err, capsize=3)
            ax.set(title=title, ylabel=units, xticks=x, xticklabels=labels)
            ax.grid(axis='y', alpha=.2);ax.set_axisbelow(True)
    axes[0, 0].legend(ncol=2)
    on = [next(r for r in rows if r['input_id']==name and r['experiment_id']=='EXP01') for name in ids]
    valid = [i for i,r in enumerate(on) if r['status']=='PASS']
    fractions = [100*int(on[i]['tns_applied_frame_channels'])/int(on[i]['total_frame_channels']) for i in valid]
    shorts = [100*int(on[i]['short_frame_channels'])/int(on[i]['total_frame_channels']) for i in valid]
    axes[1, 0].bar(x[valid]-.15, fractions, .3, label='TNS applied (EXP01)', color='#2775ad')
    axes[1, 0].bar(x[valid]+.15, shorts, .3, label='SHORT sequence', color='#e19b36')
    axes[1, 0].set(title='Actual decisions, enabled is not always applied', ylabel='% of frame/channels', xticks=x, xticklabels=labels, ylim=(0, 100))
    axes[1, 0].legend();axes[1, 0].grid(axis='y', alpha=.2);axes[1, 0].set_axisbelow(True)
    values = [float(on[i]['mean_logged_tonality']) for i in valid]
    axes[1, 1].bar(x[valid], values, color='#7560a5', width=.5)
    axes[1, 1].set(title='Original estimator: mean logged SFB tonality (EXP01)', ylabel='Mean Q15 /32768',
                   xticks=x, xticklabels=labels, ylim=(0, 1.05))
    axes[1, 1].grid(axis='y', alpha=.2);axes[1, 1].set_axisbelow(True)
    fig.suptitle('Input-dependent Psy behavior: 5 WAV inputs x 4 native cases', fontsize=18)
    fig.supxlabel('PCM16 mono 48 kHz /64 kb/s /common RMS /same duration\nCompare tool effects within each input. Native PNS OFF: tonality output has no downstream consumer.', fontsize=10)
    fig.savefig(output/'input_effects.png', dpi=180);plt.close(fig)
    text = ['# Khảo sát thay đổi input cho Psychoacoustic Model', '',
            f"Năm WAV dài {manifest['duration_seconds']:g} giây, PCM16/48 kHz/mono, "
            f"RMS chung {manifest['common_effective_rms_dbfs']:.3f} dBFS. "
            + manifest.get('description', 'Có hai bản từ WAV gốc và ba tín hiệu tổng hợp được ghi rõ nguồn gốc; không phải AAC output giả.'), '',
            '| Input | NRMSE TNS ON (%) | NRMSE TNS OFF (%) | OFF − ON (điểm %) | TNS filters ON | Frame/channel TNS áp dụng | Frame/channel SHORT | Tonality mean khi ON |',
            '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name in ids:
        a = next(r for r in rows if r['input_id']==name and r['experiment_id']=='EXP01')
        b = next(r for r in rows if r['input_id']==name and r['experiment_id']=='EXP02')
        if a['status']==b['status']=='PASS':
            text.append(f"| {name} | {float(a['distortion_rate_percent']):.5f} | {float(b['distortion_rate_percent']):.5f} | "
                        f"{float(b['distortion_rate_percent'])-float(a['distortion_rate_percent']):+.5f} | {a['encoder_tns_filters']} | "
                        f"{a['tns_applied_frame_channels']}/{a['total_frame_channels']} | "
                        f"{a['short_frame_channels']}/{a['total_frame_channels']} | {float(a['mean_logged_tonality']):.5f} |")
        else:
            text.append(f"| {name} | {a['status']} | {b['status']} | — | — | — | — | — |")
    text += ['', '## Cách đọc kết quả', '',
             'So sánh EXP01/EXP02 và EXP03/EXP04 để tách ảnh hưởng TNS trong từng WAV. '
             'So sánh EXP01/EXP03 và EXP02/EXP04 để tách chi phí chạy/bypass Tonality. '
             'Không xếp hạng chất lượng encoder bằng NRMSE giữa hai WAV có nội dung khác nhau.', '',
             'PNS là cấu hình gốc của encoder tại mono48k/64kb/s, vẫn OFF trên bộ này. '
             'Tonality ON có estimator chạy thật và output thay đổi theo âm thanh, nhưng không có PNS dùng output đó. '
             'Vì thế đổi tính chất input không tự tạo hiệu ứng Tonality lên bitstream. '
             'Trường `mean_logged_tonality` là mean theo frame của mean SFB do logger tính, không phải điểm chất lượng. '
             'Đây là trung bình SFB không có trọng số năng lượng, nên không dùng nó để phân loại chất lượng hoặc suy ra cao độ. '
             'Các SFB im lặng có thể nhận tonality gần 1 theo source gốc.', '',
             'TNS ON cho phép FDK lựa chọn filter theo phổ/window. TNS OFF có syntax filter=0. '
             'NRMSE mô tả sai số waveform và không thay thế phép nghe/pre-echo. '
             'Thời gian đo có SD trong CSV; không suy ra tốc độ PL từ số đo CPU.', '',
             '## Tài liệu và file', '',
             '- [Bảng đầy đủ 20 case](suite_comparison.csv), [200 lượt encode](suite_runs.csv), [profile riêng](suite_profile.csv).',
             '- [Đồ thị tác động input](input_effects.png).',
             '- Mỗi dòng CSV có `case_directory`: mở thư mục đó để lấy bốn AAC/WAV, trace, alignment JSON và năm plot riêng.',
             '- [Nguồn, cách tạo và lệnh chạy](README.md).', '']
    (output/'summary.md').write_text('\n'.join(text), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT/'my_workspace/psychoacoustic_model/input/psy_suite/manifest.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'my_workspace/psychoacoustic_model/experiments/psy_suite')
    parser.add_argument('--runs', type=int, default=10)
    parser.add_argument('--profile-runs', type=int, default=10)
    parser.add_argument('--skip-build', action='store_true')
    args = parser.parse_args(argv)
    if not 10 <= args.runs <= 1000 or not 1 <= args.profile_runs <= 1000:
        parser.error('Require 10..1000 main runs and 1..1000 profile runs')
    output = args.output_dir.resolve();output.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    campaign = output/'campaigns'/run_id;campaign.mkdir(parents=True)
    status = dict(complete=False, run_id=run_id, cases={}, input_manifest=str(args.manifest.resolve()))
    status_path = output/'suite_status.json';write_json(status_path, status)
    comparison=[];main_runs=[];profile_runs=[]
    for name in ('input_effects.png', 'summary.md'):(output/name).unlink(missing_ok=True)
    write_csv(output/'suite_comparison.csv', [], EXTRA_FIELDS+FIELDS)
    write_csv(output/'suite_runs.csv', [], ['input_id', *RUN_FIELDS])
    write_csv(output/'suite_profile.csv', [], ['input_id', *PROFILE_FIELDS])
    try:
        manifest_path=args.manifest.resolve()
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if not manifest['complete'] or len(manifest['inputs']) != 5:
            raise ValueError('Require a complete five-input manifest')
        for entry in manifest['inputs']:
            source=manifest_path.parent/entry['filename']
            if hashlib.sha256(source.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('Input hash changed: '+entry['input_id'])
        if not args.skip_build:
            build(ROOT/'build/psy-experiments', True, campaign/'build_research')
            build(ROOT/'build/psy-experiments-baseline', False, campaign/'build_baseline')
        for entry in manifest['inputs']:
            name=entry['input_id'];source=manifest_path.parent/entry['filename'];case_folder=campaign/name
            print(f"Starting {name}: {entry['duration_seconds']:g} seconds, {entry['source_kind']}", flush=True)
            command=[sys.executable, ROOT/'my_workspace/psychoacoustic_model/experiments/psy/scripts/run_psy_experiments.py', '--input', source,
                     '--output-dir', case_folder, '--bitrate', '64000', '--runs', str(args.runs),
                     '--profile-runs', str(args.profile_runs), '--skip-build']
            process=subprocess.run(list(map(str, command)), capture_output=True, text=True)
            (campaign/(name+'.log')).write_text(process.stdout+process.stderr, encoding='utf-8')
            print(process.stdout, end='', flush=True)
            if process.stderr:print(process.stderr, file=sys.stderr, flush=True)
            child_status=json.loads((case_folder/'results/pipeline_status.json').read_text())
            child_rows=read_csv(case_folder/'results/psy_comparison.csv')
            for row in child_rows:
                row.update(input_id=name, input_label=entry['label'], source_kind=entry['source_kind'],
                           input_sha256=entry['sha256'], case_directory=str(case_folder))
                for key in EXTRA_FIELDS[5:]:row[key]=''
                if row['status']=='PASS':
                    trace=read_csv(case_folder/'logs'/f"{row['experiment_id'].lower()}_psy_trace.csv")
                    tone=[float(t['tonality_value']) for t in trace if t['tonality_value']]
                    row.update(tns_present_frame_channels=sum(int(t['tns_filter_count'])>0 for t in trace),
                               tns_applied_frame_channels=sum(int(t['tns_applied']) for t in trace),
                               short_frame_channels=sum(t['window_sequence']=='EIGHT_SHORT_SEQUENCE' for t in trace),
                               total_frame_channels=len(trace), mean_logged_tonality=statistics.mean(tone) if tone else '')
                comparison.append(row)
            main_runs.extend(dict(input_id=name, **r) for r in read_csv(case_folder/'results/psy_runs.csv'))
            profile_runs.extend(dict(input_id=name, **r) for r in read_csv(case_folder/'results/psy_profile.csv'))
            status['cases'][name]=dict(complete=child_status['complete'], returncode=process.returncode, case_directory=str(case_folder),
                                      case_statuses={r['experiment_id']:r['status'] for r in child_rows})
            write_csv(output/'suite_comparison.csv', comparison, EXTRA_FIELDS+FIELDS)
            write_csv(output/'suite_runs.csv', main_runs, ['input_id', *RUN_FIELDS])
            write_csv(output/'suite_profile.csv', profile_runs, ['input_id', *PROFILE_FIELDS])
            write_json(status_path, status)
        if len(comparison)!=20 or any(r['status']!='PASS' for r in comparison):
            raise ValueError('Not all 20 cases passed; read case statuses/logs, missing metrics are left blank')
        if any(not item['complete'] or item['returncode']!=0 for item in status['cases'].values()):
            raise ValueError('A child pipeline did not finish its checks/plots; suite remains incomplete')
        summarize(output, comparison, manifest)
        status.update(complete=True, passed_cases=len(comparison), main_runs=len(main_runs), profile_runs=len(profile_runs),
                      manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest())
        write_json(status_path, status)
        print('Completed input suite:', output/'suite_comparison.csv')
        return 0
    except Exception as exc:
        status['error']=str(exc);write_json(status_path,status);print('ERROR:',exc,file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
