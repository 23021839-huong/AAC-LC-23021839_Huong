"""Prepare real PCM test inputs; SciPy is used only before native AAC encoding."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import wave
import numpy as np
from scipy.signal import butter, resample_poly, sosfilt, spectrogram, welch

ROOT = Path(__file__).resolve().parents[5]
RATE = 48000
NAMES = ['a01_original_long', 'a02_high_pitch', 'a03_low_stable', 'a04_transient', 'a05_noise_like']
LABELS = ['Original looped', 'Original pitch/speed x1.5', 'Stable low harmonics 110 Hz',
          'Synthetic clap-like transients', 'Synthetic band-limited noise']


def raise_pitch_by_rate(x, numerator=3, denominator=2):
    """At unchanged playback Fs, pitch/speed rise by numerator/denominator.

    This is band-limited rate conversion, not duration-preserving pitch shift.
    """
    return resample_poly(x, denominator, numerator)


def loop_to_length(x, count, crossfade_samples=2400):
    if len(x) <= crossfade_samples or count <= 0:
        raise ValueError('Source too short for the loop crossfade')
    output = np.empty(count + len(x), dtype=np.float64)
    output[:len(x)] = x
    pos = len(x)
    weights = np.linspace(0, 1, crossfade_samples, endpoint=False)
    while pos < count:
        output[pos-crossfade_samples:pos] = (output[pos-crossfade_samples:pos] * (1-weights)
                                                       + x[:crossfade_samples] * weights)
        output[pos:pos+len(x)-crossfade_samples] = x[crossfade_samples:]
        pos += len(x) - crossfade_samples
    return output[:count].copy()


def make_low_stable(rate, count, seed):
    t = np.arange(count) / rate
    x = .35 * sum(weight * np.sin(2*np.pi*110*harmonic*t + phase)
                  for harmonic, weight, phase in [(1, 1., 0.), (2, .35, .4), (3, .16, .7), (4, .08, .9)])
    # A short unique broadband signature makes a periodic waveform alignable.
    # It is disclosed in the manifest and included in full-file distortion.
    size = round(.12 * rate)
    start = min(round(4. * rate), count // 2)
    size = min(size, count - start)
    rng = np.random.default_rng(seed)
    signature = sosfilt(butter(4, [800, 9000], 'bandpass', fs=rate, output='sos'), rng.standard_normal(size))
    x[start:start+size] += 1.2 * signature * np.hanning(size)
    return x


def make_transient(rate, count, seed):
    rng = np.random.default_rng(seed)
    x = .002 * rng.standard_normal(count)
    starts = np.arange(.35, count/rate-.25, .4) + rng.uniform(-.055, .055, len(np.arange(.35, count/rate-.25, .4)))
    size = round(.20 * rate)
    t = np.arange(size) / rate
    envelope = np.minimum(t/.001, 1) * np.exp(-t/.022)
    for time in starts:
        start = round(time*rate)
        burst = sosfilt(butter(2, [600, 14000], 'bandpass', fs=rate, output='sos'), rng.standard_normal(size))
        x[start:start+size] += (.9 * burst + .24*np.sin(2*np.pi*150*t)) * envelope
    return x


def make_noise_like(rate, count, seed):
    rng = np.random.default_rng(seed)
    x = sosfilt(butter(4, [250, 12000], 'bandpass', fs=rate, output='sos'), rng.standard_normal(count))
    return x * (.85 + .15*np.sin(2*np.pi*.7*np.arange(count)/rate))


def signal_features(x, rate):
    rms = np.sqrt(np.mean(x*x))
    peak = np.max(np.abs(x))
    f, power = welch(x, fs=rate, nperseg=4096)
    active = (f >= 100) & (f <= 12000)
    flatness = np.exp(np.mean(np.log(np.maximum(power[active], 1e-30)))) / np.mean(power[active])
    return dict(rms_dbfs=float(20*np.log10(rms)), peak_dbfs=float(20*np.log10(peak)),
                crest_db=float(20*np.log10(peak/rms)),
                spectral_centroid_hz=float(np.sum(f*power)/np.sum(power)),
                dominant_frequency_hz=float(f[np.argmax(power)]),
                energy_below_500_hz_percent=float(100*np.sum(power[f<500])/np.sum(power)),
                spectral_flatness_100_12000_hz=float(flatness))


def input_plot(signals, output, labels=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(5, 2, figsize=(14, 15), layout='constrained')
    for row, (x, label) in enumerate(zip(signals, labels or LABELS)):
        step = 4800
        blocks = x[:len(x)//step*step].reshape(-1, step)
        times = (np.arange(len(blocks))+.5)*step/RATE
        rms = 20*np.log10(np.maximum(np.sqrt(np.mean(blocks*blocks, axis=1)), 1e-6))
        axes[row, 0].plot(times, rms, color='#2879af', linewidth=1)
        axes[row, 0].set(title=label, xlabel='Time (s)', ylabel='100 ms RMS (dBFS)', ylim=(-65, -5))
        axes[row, 0].grid(alpha=.2)
        frequencies, stimes, psd = spectrogram(x, fs=RATE, nperseg=2048, noverlap=1024)
        axes[row, 1].pcolormesh(stimes, frequencies, 10*np.log10(np.maximum(psd, 1e-15)),
                              shading='auto', cmap='magma', vmin=-110, vmax=-35, rasterized=True)
        axes[row, 1].set(title='Spectrogram (PSD dB/Hz, same color scale)', xlabel='Time (s)', ylabel='Frequency (Hz)', ylim=(0, 16000))
    fig.suptitle('Psy input suite: same duration / PCM16 mono 48 kHz / common RMS', fontsize=17)
    fig.savefig(output/'input_overview.png', dpi=150)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'my_workspace/INPUT/data/abc_votay.wav')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'my_workspace/psychoacoustic_model/input/psy_suite')
    parser.add_argument('--duration', type=float, default=30.)
    parser.add_argument('--rms-dbfs', type=float, default=-24.)
    parser.add_argument('--seed', type=int, default=20261013)
    args = parser.parse_args(argv)
    if not 6 <= args.duration <= 120:
        parser.error('Require 6..120 seconds')
    if not -40 <= args.rms_dbfs <= -12:
        parser.error('Require RMS -40..-12 dBFS')
    source = args.source.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output/'manifest.json'
    manifest_path.write_text('{"complete":false}\n', encoding='utf-8')
    original_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with wave.open(str(source), 'rb') as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getcomptype()) != (RATE, 1, 2, 'NONE'):
            raise ValueError('Source must be PCM16 mono 48 kHz for this controlled suite')
        original = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float64)/32768.
    count = round(args.duration*RATE)
    raw = [loop_to_length(original, count), loop_to_length(raise_pitch_by_rate(original), count),
           make_low_stable(RATE, count, args.seed), make_transient(RATE, count, args.seed+1),
           make_noise_like(RATE, count, args.seed+2)]
    fade = round(.02*RATE)
    for x in raw:
        x[:fade] *= np.linspace(0, 1, fade)
        x[-fade:] *= np.linspace(1, 0, fade)
    # Common RMS may be lowered for all inputs to retain at least 1 dB peak headroom.
    effective_rms = min(args.rms_dbfs, *[-1-signal_features(x, RATE)['crest_db'] for x in raw])
    target_rms = 10**(effective_rms/20)
    entries = []
    signals = []
    for index, (name, label, x) in enumerate(zip(NAMES, LABELS, raw)):
        x *= target_rms/np.sqrt(np.mean(x*x))
        if np.max(np.abs(x)) >= 1:
            raise ValueError('Unexpected clipping before PCM quantization')
        pcm = np.rint(x*32768).astype('<i2')
        path = output/(name+'.wav')
        with wave.open(str(path), 'wb') as w:
            w.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            w.writeframes(pcm.tobytes())
        measured = pcm.astype(np.float64)/32768
        signals.append(measured)
        entry = dict(input_id=name, label=label, filename=path.name, source_kind='derived' if index<2 else 'synthetic diagnostic',
                     source=str(source) if index<2 else None, duration_seconds=count/RATE, sample_rate=RATE, channels=1,
                     bits_per_sample=16, samples_per_channel=count, clipped_samples=int(np.count_nonzero(np.abs(pcm.astype(np.int32))>=32767)),
                     sha256=hashlib.sha256(path.read_bytes()).hexdigest(), **signal_features(measured, RATE))
        if index == 0:entry['construction']='Source looped with 50 ms crossfades; pitch/speed unchanged.'
        if index == 1:entry['construction']='Source resample_poly(2,3), playback Fs unchanged; pitch/speed x1.5 (+7.01955 semitones), looped with 50 ms crossfades.'
        if index == 2:entry['construction']='Steady 110/220/330/440 Hz harmonic mixture, plus disclosed 120 ms unique alignment signature at 4 s; signature included in distortion.'
        if index == 3:entry['construction']='Seeded band-limited noise/kick bursts, 1 ms attack, 22 ms exponential decay, around 400 ms apart with jitter.'
        if index == 4:entry['construction']='Seeded Gaussian noise bandpass 250..12000 Hz, slow 0.7 Hz amplitude modulation.'
        entries.append(entry)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_digest
    manifest = dict(complete=True, source=str(source), source_sha256=original_digest, seed=args.seed,
                    requested_rms_dbfs=args.rms_dbfs, common_effective_rms_dbfs=effective_rms,
                    sample_rate=RATE, channels=1, duration_seconds=count/RATE, inputs=entries,
                    note='RMS matched, not perceptual LUFS matching. Synthetic audio is test input, not simulated AAC output.')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    with (output/'input_features.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[k for k in entries[0] if k!='construction']+['construction'])
        writer.writeheader();writer.writerows(entries)
    input_plot(signals, output)
    print(f'Prepared {len(entries)} WAV files, {count/RATE:g} seconds each, RMS {effective_rms:.3f} dBFS: {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
