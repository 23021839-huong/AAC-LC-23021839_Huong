"""Download ESC-50 real recordings, preserve originals, prepare controlled WAV montages."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import math
from pathlib import Path
import urllib.request
import wave

import numpy as np
from scipy.signal import resample_poly
from prepare_psy_inputs import RATE, signal_features, input_plot
from run_psy_experiments import ROOT, write_json

REPOSITORY = 'https://github.com/karolpiczak/ESC-50'
GROUPS = [('b01_engine_low', 'engine', 'Real engine / low-frequency mechanical sound', 'Engine\nlow'),
          ('b02_birds_high', 'chirping_birds', 'Real chirping birds / high-frequency calls', 'Birds\nhigh'),
          ('b03_bells_tonal', 'church_bells', 'Real church bells / harmonic ringing and decay', 'Bells\ntonal'),
          ('b04_clapping', 'clapping', 'Real hand clapping / repeated transients', 'Clapping\ntransients'),
          ('b05_rain_noise', 'rain', 'Real rain / continuous broadband noise', 'Rain\nnoise')]


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent':'FDK-AAC-research-input-preparation'})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read()


def read_mono_pcm16(path):
    with wave.open(str(path), 'rb') as w:
        if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getcomptype()!='NONE':
            raise ValueError('Unexpected ESC-50 format: '+str(path))
        rate = w.getframerate(); frames=w.getnframes(); raw=w.readframes(frames)
    if len(raw)!=2*frames:
        raise ValueError('Truncated WAV: '+str(path))
    return np.frombuffer(raw, '<i2').astype(np.float64)/32768, rate


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'my_workspace/psychoacoustic_model/input/psy_external')
    parser.add_argument('--duration', type=float, default=30.)
    parser.add_argument('--rms-dbfs', type=float, default=-24.)
    args=parser.parse_args(argv)
    if not 6<=args.duration<=60 or not -40<=args.rms_dbfs<=-12:
        parser.error('Require 6..60 seconds and RMS -40..-12 dBFS')
    output=args.output_dir.resolve();output.mkdir(parents=True, exist_ok=True)
    metadata=output/'source_metadata';metadata.mkdir(exist_ok=True)
    originals=output/'originals';originals.mkdir(exist_ok=True)
    write_json(output/'manifest.json', dict(complete=False))
    repository_path=metadata/'repository.json'
    if repository_path.exists():
        repository=json.loads(repository_path.read_text())
    else:
        commit=json.loads(fetch('https://api.github.com/repos/karolpiczak/ESC-50/commits/master'))['sha']
        repository=dict(repository=REPOSITORY, commit=commit,
                        raw_base='https://raw.githubusercontent.com/karolpiczak/ESC-50/'+commit)
        write_json(repository_path, repository)
    for name in ('meta/esc50.csv', 'LICENSE', 'README.md'):
        path=metadata/Path(name).name
        if not path.exists():path.write_bytes(fetch(repository['raw_base']+'/'+name))
    license_text=(metadata/'LICENSE').read_text(encoding='utf-8')
    with (metadata/'esc50.csv').open(newline='', encoding='utf-8') as f:
        all_rows=list(csv.DictReader(f))
    selections={}
    for name, category, _, _ in GROUPS:
        rows=[];seen=set()
        for row in all_rows:
            if row['category']==category and row['src_file'] not in seen:
                rows.append(row);seen.add(row['src_file'])
                if len(rows)==math.ceil(args.duration/5):break
        if len(rows)!=math.ceil(args.duration/5):raise ValueError('Insufficient distinct sources')
        selections[name]=rows
    selected=[r for rows in selections.values() for r in rows]
    def download(row):
        path=originals/row['filename'];url=repository['raw_base']+'/audio/'+row['filename']
        if not path.exists():
            temporary=path.with_suffix('.wav.partial');temporary.write_bytes(fetch(url))
            x,rate=read_mono_pcm16(temporary)
            if rate!=44100 or len(x)!=5*rate:raise ValueError('Unexpected 5-second ESC-50 recording')
            temporary.replace(path)
        return path
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(download, selected))
    print(f'Downloaded/cached {len(selected)} distinct real recordings from ESC-50.', flush=True)
    count=round(args.duration*RATE);raw_signals=[];sources={}
    for name, _, _, _ in GROUPS:
        parts=[];references=[]
        for row in selections[name]:
            path=originals/row['filename'];x,rate=read_mono_pcm16(path)
            x=resample_poly(x, RATE//math.gcd(RATE,rate), rate//math.gcd(RATE,rate))
            rms=np.sqrt(np.mean(x*x))
            if rms==0:raise ValueError('Silent source: '+path.name)
            x=x/rms  # Equal RMS among real segments before global common-RMS matching.
            fade=round(.01*RATE);x[:fade]*=np.linspace(0,1,fade);x[-fade:]*=np.linspace(1,0,fade)
            parts.append(x)
            attribution=next((line for line in license_text.splitlines() if '/sounds/'+row['src_file']+'/' in line), '')
            if not attribution:raise ValueError('Missing original clip attribution: '+row['filename'])
            references.append(dict(filename=row['filename'], category=row['category'], src_file=row['src_file'],
                                   dataset_page=f"{REPOSITORY}/blob/{repository['commit']}/audio/{row['filename']}",
                                   download_url=repository['raw_base']+'/audio/'+row['filename'],
                                   sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                   sample_rate=rate, channels=1, bits_per_sample=16, duration_seconds=5,
                                   attribution=attribution))
        x=np.concatenate(parts)[:count]
        fade=round(.02*RATE);x[:fade]*=np.linspace(0,1,fade);x[-fade:]*=np.linspace(1,0,fade)
        raw_signals.append(x);sources[name]=references
    effective_rms=min(args.rms_dbfs, *[-1-signal_features(x, RATE)['crest_db'] for x in raw_signals])
    entries=[];final=[]
    for (name, category, label, short_label), x in zip(GROUPS, raw_signals):
        x*=10**(effective_rms/20)/np.sqrt(np.mean(x*x))
        if np.max(np.abs(x))>=1:raise ValueError('Unexpected clipping')
        pcm=np.rint(x*32768).astype('<i2');path=output/(name+'.wav')
        with wave.open(str(path), 'wb') as w:
            w.setparams((1,2,RATE,0,'NONE','not compressed'));w.writeframes(pcm.tobytes())
        measured=pcm.astype(np.float64)/32768;final.append(measured)
        entries.append(dict(input_id=name, filename=path.name, label=label, short_label=short_label,
                            source_kind='external real ESC-50 recordings, montage', category=category,
                            duration_seconds=count/RATE, samples_per_channel=count, sample_rate=RATE, channels=1, bits_per_sample=16,
                            clipped_samples=int(np.count_nonzero(np.abs(pcm.astype(np.int32))>=32767)),
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), sources=sources[name],
                            **signal_features(measured, RATE)))
    manifest=dict(complete=True, dataset='ESC-50', repository=repository,
                  description='Năm WAV được ghép từ các bản ghi thực ESC-50/Freesound ở nguồn bên ngoài; không có tín hiệu tổng hợp hoặc bản biến đổi từ abc_votay.wav.',
                  dataset_license='Creative Commons Attribution-NonCommercial 3.0; per-clip attributions preserved in source_metadata/LICENSE and manifest.',
                  preprocessing='Six distinct 5-second field recordings per category for 30 s. Resample 44.1k to48k preserving pitch/speed; equal-RMS each segment;10ms endpoint fades per segment;20ms global endpoint fades; no synthetic alignment marker.',
                  duration_seconds=count/RATE, sample_rate=RATE, channels=1, requested_rms_dbfs=args.rms_dbfs,
                  common_effective_rms_dbfs=effective_rms, inputs=entries)
    write_json(output/'manifest.json', manifest)
    fields=['input_id','filename','category','source_kind','duration_seconds','sample_rate','channels','bits_per_sample',
            'samples_per_channel','clipped_samples','sha256','rms_dbfs','peak_dbfs','crest_db','spectral_centroid_hz',
            'dominant_frequency_hz','energy_below_500_hz_percent','spectral_flatness_100_12000_hz']
    with (output/'input_features.csv').open('w', newline='', encoding='utf-8') as f:
        writer=csv.DictWriter(f, fieldnames=fields, extrasaction='ignore');writer.writeheader();writer.writerows(entries)
    attribution_lines=['# External input source attributions', '', f"Repository: {REPOSITORY}",
                       f"Pinned commit: {repository['commit']}", '',
                       'Dataset license: CC BY-NC 3.0; full original LICENSE is preserved in source_metadata/LICENSE.', '',
                       'Changes: resampling, RMS scaling, endpoint fades and joining distinct recordings into each WAV.', '']
    for entry in entries:
        attribution_lines += ['## '+entry['input_id'], '']
        for ref in entry['sources']:
            attribution_lines += ['- '+ref['filename']+' — '+ref['download_url'], '  '+ref['attribution']]
        attribution_lines.append('')
    (output/'SOURCES.md').write_text('\n'.join(attribution_lines), encoding='utf-8')
    input_plot(final, output, [e['label'] for e in entries])
    print(f'Prepared five external WAVs, {count/RATE:g} s each, common RMS {effective_rms:.3f} dBFS: {output}')
    return 0


if __name__=='__main__':raise SystemExit(main())
