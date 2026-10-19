"""Prepare 15 externally recorded PCM16 inputs, 10..300 s, without looping."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import time
import urllib.request
import wave
import zipfile

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, spectrogram

from prepare_psy_inputs import RATE, signal_features
from run_psy_experiments import ROOT, write_json

COMMIT = '33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6'
REPO = 'https://github.com/karolpiczak/ESC-50'
RAW = 'https://raw.githubusercontent.com/karolpiczak/ESC-50/' + COMMIT
GROUPS = [
    ('c01_alarm_tonal', 10, ['clock_alarm'], 'Clock alarm / tonal pulses', 'Alarm', 'Âm báo có cao độ, kiểm tra phổ tập trung và bật/tắt theo thời gian'),
    ('c02_glass_impulses', 15, ['glass_breaking'], 'Breaking glass / sharp attacks', 'Glass', 'Xung ngắn, đỉnh mạnh và nhiều thành phần tần số cao'),
    ('c03_dog_vocal', 20, ['dog'], 'Dog barking / irregular vocal bursts', 'Barks', 'Âm hữu thanh thay đổi và các khoảng nghỉ'),
    ('c04_keyboard_clicks', 30, ['keyboard_typing', 'mouse_click'], 'Keyboard and mouse / repeated clicks', 'Clicks', 'Nhiều attack nhỏ, mật độ sự kiện biến đổi'),
    ('c05_footsteps', 45, ['footsteps'], 'Footsteps / low-frequency impacts', 'Steps', 'Xung trầm và nhịp không hoàn toàn đều'),
    ('c06_thunder', 60, ['thunderstorm'], 'Thunderstorm / low rumbles and attacks', 'Thunder', 'Rumble trầm, attack và decay dài'),
    ('c07_insects_high', 75, ['crickets', 'insects'], 'Crickets and insects / high-frequency texture', 'Insects', 'Âm cao, tuần hoàn xen với texture nhiễu'),
    ('c08_waves_wind', 90, ['sea_waves', 'wind'], 'Sea waves and wind / changing noise envelope', 'Waves/wind', 'Phổ rộng với envelope thay đổi chậm'),
    ('c09_fire_crackle', 120, ['crackling_fire'], 'Crackling fire / noisy texture and micro-attacks', 'Fire', 'Nền nhiễu xen các xung nhỏ'),
    ('c10_machines_low', 180, ['engine', 'washing_machine', 'vacuum_cleaner'], 'Machines / hum and rotating mechanical noise', 'Machines', 'Âm cơ khí liên tục, thành phần trầm và các harmonic'),
    ('c11_transport_mix', 240, ['airplane', 'train', 'helicopter', 'car_horn'], 'Transport / motors and horns', 'Transport', 'Đổi đặc trưng giữa động cơ, tiếng lăn và còi'),
]
EXTERNAL = [
    dict(input_id='c12_speech_female', duration=150, start=45, filename='prideandprejudice_01_austen.mp3',
         url='https://archive.org/download/prideandprejudice_1005_librivox/prideandprejudice_01_austen.mp3',
         page='https://librivox.org/4023', label='Female narration / Elizabeth Klett', short_label='Speech F',
         purpose_vi='Giọng đọc nữ, nguyên âm harmonic xen phụ âm nhiễu và khoảng nghỉ',
         attribution='Jane Austen, Pride and Prejudice, chapter 1; read by Elizabeth Klett for LibriVox.',
         license='LibriVox states public domain in the USA; retain the source copyright notice.', codec='MP3'),
    dict(input_id='c13_speech_male', duration=210, start=120, filename='adventuresofsherlockholmes_01_doyle_128kb.mp3',
         url='https://archive.org/download/adventuressherlockholmes_v4_1501_librivox/adventuresofsherlockholmes_01_doyle_128kb.mp3',
         page='https://librivox.org/9481', label='Male narration / David Clarke', short_label='Speech M',
         purpose_vi='Giọng đọc nam, âm trầm hữu thanh xen phụ âm và ngắt câu',
         attribution='Arthur Conan Doyle, A Scandal in Bohemia; read by David Clarke for LibriVox.',
         license='LibriVox states public domain in the USA; retain the source copyright notice.', codec='MP3'),
    dict(input_id='c14_piano_slow', duration=270, start=15, filename='moonlight_adagio_pitman.ogg',
         url='https://upload.wikimedia.org/wikipedia/commons/4/48/Ludwig_van_Beethoven_-_sonata_no._14_in_c_sharp_minor_%27moonlight%27%2C_op._27_no._2_-_i._adagio_sostenuto.ogg',
         page="https://commons.wikimedia.org/wiki/File:Ludwig_van_Beethoven_-_sonata_no._14_in_c_sharp_minor_'moonlight',_op._27_no._2_-_i._adagio_sostenuto.ogg",
         label='Piano / Moonlight Adagio, Paul Pitman', short_label='Piano slow',
         purpose_vi='Piano chậm, harmonic và decay kéo dài, không phải MIDI tổng hợp',
         attribution='Beethoven, Moonlight Sonata I, Adagio sostenuto; Paul Pitman / Musopen, via Wikimedia Commons. https://musopen.org/',
         license='Recording dedicated to public domain by Musopen; Commons also requests Musopen attribution; see source page.', codec='Ogg Vorbis'),
    dict(input_id='c15_piano_fast', duration=300, start=30, filename='moonlight_presto_pitman.ogg',
         url='https://upload.wikimedia.org/wikipedia/commons/1/1d/Moonlight_Sonata_Presto.ogg',
         page='https://commons.wikimedia.org/wiki/File:Moonlight_Sonata_Presto.ogg',
         label='Piano / Moonlight Presto, Paul Pitman', short_label='Piano fast',
         purpose_vi='Piano nhanh, nhiều attack và chuyển động phổ trong bản ghi dài',
         attribution='Beethoven, Moonlight Sonata III, Presto; Paul Pitman / Musopen, via Wikimedia Commons. https://musopen.org/',
         license='Public-domain recording supplied by Musopen; retain attribution and original Commons source notice.', codec='Ogg Vorbis'),
]


def download(url, path):
    """Cache original bytes; publish only a completed HTTP transfer."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.partial')
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'FDK-AAC-research-inputs/1.0'})
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as out:
                shutil.copyfileobj(response, out, length=1024*1024)
                expected = response.headers.get('Content-Length')
            if expected and temporary.stat().st_size != int(expected):
                raise ValueError('Incomplete HTTP transfer: ' + url)
            temporary.replace(path)
            return path
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def prepare_excerpt(path, start, duration):
    with sf.SoundFile(path) as recording:
        rate, channels = recording.samplerate, recording.channels
        first, count = round(start*rate), round(duration*rate)
        if first < 0 or count <= 0 or first + count > len(recording):
            raise ValueError('Source is too short for requested excerpt: ' + str(path))
        source_seconds = len(recording)/rate
        recording.seek(first)
        x = recording.read(count, dtype='float64', always_2d=True).mean(axis=1)
    factor = math.gcd(RATE, rate)
    if rate != RATE:
        x = resample_poly(x, RATE//factor, rate//factor)
    target = round(duration*RATE)
    if len(x) < target:
        raise ValueError('Resampler returned insufficient samples')
    return x[:target], dict(source_sample_rate=rate, source_channels=channels,
                           source_duration_seconds=source_seconds, excerpt_start_seconds=start,
                           excerpt_duration_seconds=duration, source_codec=sf.info(path).format)


def assemble_parts(parts, duration):
    target = round(duration*RATE)
    if sum(len(x) for x in parts) < target:
        raise ValueError('Insufficient real samples; looping/padding is prohibited')
    faded = []
    for part in parts:
        x = part.copy()
        size = min(round(.01*RATE), len(x)//2)
        x[:size] *= np.linspace(0, 1, size)
        x[-size:] *= np.linspace(1, 0, size)
        faded.append(x)
    return np.concatenate(faded)[:target]


def select_esc_sources(rows, categories, count, excluded):
    chosen, seen = [], set(excluded)
    pools = [[r for r in rows if r['category'] == category] for category in categories]
    while len(chosen) < count:
        progress = False
        for pool in pools:
            while pool and pool[0]['src_file'] in seen:
                pool.pop(0)
            if pool and len(chosen) < count:
                row = pool.pop(0); chosen.append(row); seen.add(row['src_file']); progress = True
        if not progress:
            raise ValueError('Insufficient distinct external source IDs: ' + ','.join(categories))
    return chosen


def common_rms_dbfs(signals, requested):
    crests = []
    for x in signals:
        rms = np.sqrt(np.mean(x*x))
        if not np.isfinite(x).all() or not rms:
            raise ValueError('Empty, silent or non-finite signal')
        crests.append(20*np.log10(np.max(np.abs(x))/rms))
    return float(min(requested, *[-1-c for c in crests]))


def normalization_targets(signals, requested, mode):
    if mode == 'common':
        return [common_rms_dbfs(signals, requested)]*len(signals)
    if mode != 'individual':
        raise ValueError('Unknown RMS matching mode')
    return [common_rms_dbfs([x], requested) for x in signals]


def to_pcm16(x, rms_dbfs):
    rms = np.sqrt(np.mean(x*x))
    if not rms or not np.isfinite(x).all():
        raise ValueError('Cannot normalize silent/non-finite signal')
    scaled = x * (10**(rms_dbfs/20)/rms)
    if np.max(np.abs(scaled)) >= 1:
        raise ValueError('Requested gain would clip')
    return np.rint(scaled*32768).astype('<i2')


def write_wav(path, pcm):
    temporary = path.with_suffix('.wav.partial')
    with wave.open(str(temporary), 'wb') as w:
        w.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        w.writeframes(pcm.tobytes())
    temporary.replace(path)


def extra_features(x):
    step = 4800
    blocks = x[:len(x)//step*step].reshape(-1, step)
    envelope = 20*np.log10(np.maximum(np.sqrt(np.mean(blocks*blocks, axis=1)), 1e-12))
    return dict(zero_crossing_rate=float(np.mean(np.signbit(x[1:]) != np.signbit(x[:-1]))),
                rms_100ms_p10_dbfs=float(np.percentile(envelope, 10)),
                rms_100ms_p90_dbfs=float(np.percentile(envelope, 90)),
                envelope_range_p90_p10_db=float(np.percentile(envelope, 90)-np.percentile(envelope, 10)),
                quiet_100ms_below_minus50_dbfs_percent=float(100*np.mean(envelope < -50)))


def plots(entries, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for page in range(3):
        selected = entries[page*5:(page+1)*5]
        fig, axes = plt.subplots(len(selected), 2, figsize=(14, 15), layout='constrained', squeeze=False)
        for row, entry in enumerate(selected):
            x, _ = sf.read(output/entry['filename'], dtype='float64')
            blocks = x.reshape(-1, 4800)
            t = (np.arange(len(blocks))+.5)/10
            env = 20*np.log10(np.maximum(np.sqrt(np.mean(blocks*blocks, axis=1)), 1e-6))
            axes[row, 0].plot(t, env, linewidth=.8)
            axes[row, 0].set(title=entry['input_id']+' / '+str(entry['duration_seconds'])+' s',
                             xlabel='Time (s)', ylabel='100 ms RMS (dBFS)', ylim=(-65, -5))
            axes[row, 0].grid(alpha=.2)
            f, st, psd = spectrogram(x, fs=RATE, nperseg=2048, noverlap=0)
            stride = max(1, len(st)//1600)
            axes[row, 1].pcolormesh(st[::stride], f, 10*np.log10(np.maximum(psd[:, ::stride], 1e-15)),
                                   shading='auto', cmap='magma', vmin=-110, vmax=-35, rasterized=True)
            axes[row, 1].set(title=entry['label'], xlabel='Time (s)', ylabel='Frequency (Hz)', ylim=(0, 16000))
        fig.suptitle('External recorded inputs / PCM16 mono 48 kHz / page '+str(page+1), fontsize=17)
        fig.savefig(output/('input_overview_%02d.png' % (page+1)), dpi=120); plt.close(fig)


def write_docs(output, entries, targets, mode):
    lines = ['# Bộ 15 WAV bổ sung cho khảo sát Psy', '',
             'Tất cả file là PCM16, mono, 48 kHz; thời lượng 10–300 giây. '
             f'Chuẩn hóa RMS theo chế độ {mode}; mức thực tế từ {min(targets):.3f} đến {max(targets):.3f} dBFS, giữ ít nhất 1 dB headroom. '
             'Đây là RMS matching, không phải LUFS matching.', '',
             '| File | Giây | Đặc trưng dự kiến khảo sát | Loại nguồn |', '|---|---:|---|---|']
    for entry in entries:
        lines.append(f"| {entry['filename']} | {entry['duration_seconds']:g} | {entry['purpose_vi']} | {entry['source_kind']} |")
    lines += ['', 'Các mô tả trên là tính chất âm học cần khảo sát; các số đo thực tế nằm trong input_features.csv. '
              'Spectral flatness/tâm phổ không thay thế estimator Tonality gốc của FDK.', '',
              '11 file môi trường ghép các clip thật 5 giây, mỗi source ID chỉ dùng một lần trong bộ mới và tránh source ID của bộ 5 WAV cũ. '
              'Không lặp clip, không thêm tín hiệu tổng hợp. Các điểm nối có fade 10 ms và được ghi trong manifest. '
              '2 file giọng đọc và 2 file piano là đoạn liên tục, không ghép/lặp.', '',
              'Chuẩn bị: downmix bằng trung bình kênh nếu cần; resample_poly giữ cao độ/tốc độ; '
              'bỏ DC toàn file; fade đầu/cuối 20 ms; một gain cố định cho mỗi file; lượng tử PCM16. '
              'Giữ biến đổi envelope trong đoạn gốc, không AGC/không nâng cao độ. '
              'Mặc định mỗi file nhắm RMS −24 dBFS; khi crest factor quá lớn, hạ gain của riêng file đó để tránh clipping. '
              'Không ép toàn bộ bộ dữ liệu xuống mức của file xung thưa. Vì RMS không hoàn toàn bằng nhau, '
              'không quy mọi khác biệt giữa input chỉ cho nội dung âm thanh; so ON/OFF trên cùng file. '
              'Có thể tạo một thư mục riêng với --rms-mode common nếu cần thí nghiệm giữ RMS giống nhau.', '',
              'Không coi file 300 giây là bản ghi raw lossless: giọng đọc có nguồn MP3, piano có nguồn Ogg Vorbis; '
              'các lỗi mã hóa có sẵn trong nguồn vẫn tồn tại sau chuyển WAV.', '',
              '## Chạy trên Linux hoặc Windows', '',
              'Chạy từ thư mục gốc source FDK đã sửa, dùng đúng các thư viện lib* và CMakeLists.txt của dự án.', '',
              '```bash', 'python -m pip install numpy scipy soundfile pandas matplotlib',
              'python experiments/psy/scripts/run_psy_extended_suite.py --manifest input/psy_external_extended/manifest.json --output-dir experiments/psy_extended --runs 10 --profile-runs 10',
              '```', '',
              'Lệnh đầy đủ tạo 60 case, 600 lượt đo encode và 600 lượt profile riêng. '
              'Runner mới nhận 1–20 input và độ dài từng file độc lập, không sửa runner 5 WAV cũ. '
              'AAC-LC/64 kb/s; PNS theo cấu hình native. Bốn case chỉ điều khiển Tonality/TNS; chưa bật/tắt PNS độc lập. '
              'Chưa chạy toàn campaign 60 case khi chuẩn bị bộ dữ liệu.', '',
              'Để kiểm tra manifest/WAV/hash trước khi build:', '```bash',
              'python experiments/psy/scripts/run_psy_extended_suite.py --manifest input/psy_external_extended/manifest.json --validate-only',
              '```', '',
              'Dùng --input-ids c01_alarm_tonal,c15_piano_fast để chạy nhóm nhỏ; --skip-build dùng sau lần build thành công.', '',
              '## Cách đánh giá', '',
              'So sánh ON/OFF trong cùng một input. Do độ dài khác nhau, dùng encoding_time_ms/source_duration_seconds '
              'hoặc real-time factor để so chi phí giữa input; không chỉ so tổng thời gian. '
              'Không dùng NRMSE giữa nội dung khác nhau để xếp hạng chất lượng codec. '
              'TNS thay đổi phân bố nhiễu theo thời gian, cần nghe/đo pre-echo bên cạnh NRMSE. '
              'Không kết luận lợi ích Tonality từ cấu hình PNS OFF.', '',
              'Nguồn/giấy phép: SOURCES.md, manifest.json và source_metadata/. '
              'Originals/ giữ nguyên byte tải về, nhưng không đưa vào ZIP nhẹ để chuyển server. '
              'Các WAV đầu ra là dữ liệu test đã xử lý, không phải bản ghi 30 phút liên tục.', '']
    (output/'README.md').write_text('\n'.join(lines), encoding='utf-8')
    source_lines = ['# Nguồn và attribution', '',
                    'ESC-50: dataset CC BY-NC 3.0; giữ attribution từng clip và LICENSE gốc. '
                    'LibriVox ghi public domain tại USA trên trang catalog. '
                    'Piano: bản ghi Paul Pitman/Musopen từ Commons, giữ attribution và ghi chú license của từng trang.', '']
    for entry in entries:
        source_lines += ['## '+entry['input_id'], '']
        for ref in entry['sources']:
            source_lines += ['- '+ref['filename']+' — '+ref['source_page'],
                             '  Download: '+ref['download_url'], '  '+ref['attribution'],
                             '  License: '+ref['license'], '  SHA256: '+ref['sha256']]
        source_lines.append('')
    (output/'SOURCES.md').write_text('\n'.join(source_lines), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'my_workspace/psychoacoustic_model/input/psy_external_extended')
    parser.add_argument('--rms-dbfs', type=float, default=-24)
    parser.add_argument('--rms-mode', choices=('individual', 'common'), default='individual')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--overwrite', action='store_true', help='Regenerate this named corpus using cached originals')
    args = parser.parse_args(argv)
    if not -50 <= args.rms_dbfs <= -12 or not 1 <= args.jobs <= 8:
        parser.error('Require RMS -50..-12 dBFS and 1..8 download jobs')
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=True)
    metadata = output/'source_metadata'; metadata.mkdir(exist_ok=True)
    originals = output/'originals'; originals.mkdir(exist_ok=True)
    if (output/'manifest.json').exists():
        previous_output = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
        if previous_output.get('complete') and (not args.overwrite or previous_output.get('corpus_id') != 'psy_external_extended_15'):
            raise ValueError('Prepared corpus already complete; use a new output directory or --overwrite for this named corpus')
    write_json(output/'manifest.json', dict(complete=False))
    for name in ('meta/esc50.csv', 'LICENSE', 'README.md'):
        path = metadata/Path(name).name
        cached = ROOT/'my_workspace/psychoacoustic_model/input/psy_external/source_metadata'/path.name
        if not path.exists() and cached.exists(): shutil.copyfile(cached, path)
        download(RAW+'/'+name, path)
    with (metadata/'esc50.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    exclusion_path = metadata/'previous_source_ids.json'
    if exclusion_path.exists():
        excluded = set(json.loads(exclusion_path.read_text(encoding='utf-8')))
    else:
        previous = ROOT/'my_workspace/psychoacoustic_model/input/psy_external/manifest.json'
        old = json.loads(previous.read_text(encoding='utf-8')) if previous.exists() else dict(inputs=[])
        excluded = {s['src_file'] for e in old['inputs'] for s in e['sources'] if 'src_file' in s}
        write_json(exclusion_path, sorted(excluded))
    all_excluded = set(excluded); selections = {}
    for name, duration, categories, *_ in GROUPS:
        selected = select_esc_sources(rows, categories, math.ceil(duration/5), all_excluded)
        selections[name] = selected; all_excluded.update(r['src_file'] for r in selected)
    write_json(metadata/'selection.json', selections)
    write_json(metadata/'external_sources.json', EXTERNAL)
    license_text = (metadata/'LICENSE').read_text(encoding='utf-8')
    jobs = [(RAW+'/audio/'+r['filename'], originals/r['filename']) for selection in selections.values() for r in selection]
    jobs += [(entry['url'], originals/entry['filename']) for entry in EXTERNAL]
    print(f'Downloading/caching {len(jobs)} original recordings; {len(excluded)} previous source IDs excluded.', flush=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        pending = {executor.submit(download, url, path): path for url, path in jobs}
        for count, future in enumerate(as_completed(pending), 1):
            future.result()
            if count % 20 == 0 or count == len(jobs): print(f'Downloaded/cached {count}/{len(jobs)}', flush=True)
    entries, signals = [], []
    for name, duration, categories, label, short_label, purpose in GROUPS:
        parts, references = [], []
        for row in selections[name]:
            path = originals/row['filename']; x, source_info = prepare_excerpt(path, 0, 5)
            if source_info['source_sample_rate'] != 44100 or source_info['source_channels'] != 1:
                raise ValueError('Unexpected ESC-50 source format')
            parts.append(x)
            attribution = next((line for line in license_text.splitlines() if '/sounds/'+row['src_file']+'/' in line), '')
            if not attribution: raise ValueError('Missing ESC attribution: '+path.name)
            references.append(dict(filename=path.name, src_file=row['src_file'], category=row['category'],
                                   source_page=REPO+'/blob/'+COMMIT+'/audio/'+path.name, download_url=RAW+'/audio/'+path.name,
                                   sha256=hashlib.sha256(path.read_bytes()).hexdigest(), attribution=attribution,
                                   license='ESC-50 dataset CC BY-NC 3.0; per-clip notice above', **source_info))
        signals.append(assemble_parts(parts, duration))
        entries.append(dict(input_id=name, filename=name+'.wav', duration_seconds=duration, label=label,
                            short_label=short_label, purpose_vi=purpose, categories=categories,
                            source_kind='external real ESC-50 recordings, montage', join_times_seconds=list(range(5, duration, 5)),
                            repeated_source_count=0, sources=references))
    for entry in EXTERNAL:
        path = originals/entry['filename']; x, source_info = prepare_excerpt(path, entry['start'], entry['duration'])
        signals.append(x)
        ref = dict(filename=path.name, source_page=entry['page'], download_url=entry['url'],
                   sha256=hashlib.sha256(path.read_bytes()).hexdigest(), attribution=entry['attribution'],
                   license=entry['license'], original_lossy_codec=entry['codec'], **source_info)
        entries.append(dict(input_id=entry['input_id'], filename=entry['input_id']+'.wav', duration_seconds=entry['duration'],
                            label=entry['label'], short_label=entry['short_label'], purpose_vi=entry['purpose_vi'],
                            source_kind='external continuous recording excerpt', join_times_seconds=[], repeated_source_count=0, sources=[ref]))
    for x in signals:
        x -= np.mean(x)
        fade = round(.02*RATE)
        x[:fade] *= np.linspace(0, 1, fade); x[-fade:] *= np.linspace(1, 0, fade)
    targets = normalization_targets(signals, args.rms_dbfs, args.rms_mode)
    for entry, x, target in zip(entries, signals, targets):
        pcm = to_pcm16(x, target); path = output/entry['filename']; write_wav(path, pcm)
        measured = pcm.astype(np.float64)/32768
        entry.update(sample_rate=RATE, channels=1, bits_per_sample=16, samples_per_channel=len(pcm),
                     requested_rms_dbfs=args.rms_dbfs, effective_target_rms_dbfs=target,
                     clipped_samples=int(np.sum(np.abs(pcm.astype(np.int32)) >= 32767)),
                     sha256=hashlib.sha256(path.read_bytes()).hexdigest(), **signal_features(measured, RATE), **extra_features(measured))
        print(f"Prepared {entry['filename']}: {entry['duration_seconds']} s, RMS {entry['rms_dbfs']:.3f} dBFS", flush=True)
    signals.clear()
    fields = ['input_id','filename','duration_seconds','source_kind','sample_rate','channels','bits_per_sample',
              'samples_per_channel','clipped_samples','requested_rms_dbfs','effective_target_rms_dbfs','rms_dbfs','peak_dbfs','crest_db','spectral_centroid_hz','dominant_frequency_hz',
              'energy_below_500_hz_percent','spectral_flatness_100_12000_hz','zero_crossing_rate','envelope_range_p90_p10_db',
              'rms_100ms_p10_dbfs','rms_100ms_p90_dbfs','quiet_100ms_below_minus50_dbfs_percent','sha256']
    with (output/'input_features.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(entries)
    write_docs(output, entries, targets, args.rms_mode)
    plots(entries, output)
    manifest = dict(complete=True, corpus_id='psy_external_extended_15', input_count=len(entries), sample_rate=RATE, channels=1,
                    min_duration_seconds=min(e['duration_seconds'] for e in entries), max_duration_seconds=max(e['duration_seconds'] for e in entries),
                    total_duration_seconds=sum(e['duration_seconds'] for e in entries), requested_rms_dbfs=args.rms_dbfs,
                    rms_matching_mode=args.rms_mode, common_effective_rms_dbfs=targets[0] if args.rms_mode=='common' else None,
                    min_effective_rms_dbfs=min(targets), max_effective_rms_dbfs=max(targets), source_count=len(jobs), esc50_commit=COMMIT,
                    preprocessing='No looping/synthesis. Mono mean; polyphase resampling; 10 ms montage endpoint fades; whole-file DC removal and 20 ms endpoint fades; one fixed RMS-matching gain per output; PCM16.',
                    description='15 external real recordings/montages with independently selected durations from 10 to300 s; source codec/joins/offsets are explicit.',
                    inputs=entries)
    write_json(output/'manifest.json', manifest)
    package = output/'psy_external_extended_15_wavs.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file() and path != package and 'originals' not in path.relative_to(output).parts:
                archive.write(path, str(Path('my_workspace/psychoacoustic_model/input/psy_external_extended')/path.relative_to(output)))
        for path in sorted((ROOT/'my_workspace/psychoacoustic_model/experiments/psy/scripts').glob('*.py')):
            archive.write(path, path.relative_to(ROOT).as_posix())
        archive.writestr('experiments/psy/scripts/extended_requirements.txt', 'numpy>=1.24\nscipy>=1.10\nsoundfile>=0.13\npandas>=2.0\nmatplotlib>=3.6\n')
    print(f'Complete: {len(entries)} WAVs, {manifest["total_duration_seconds"]} s, ZIP {package.stat().st_size/1e6:.1f} MB: {package}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
