#!/usr/bin/env python3
"""Read native FDK dumps, print statistics and plot; never run an FFT/MDCT."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def statistics(values):
    # Convert BEFORE squaring: INT32_MIN squared / complex magnitude can overflow.
    a = np.asarray(values, dtype=np.float64).ravel()
    if not a.size or not np.isfinite(a).all():
        raise ValueError('statistics require nonempty finite data')
    return {'count': int(a.size), 'min': float(a.min()), 'max': float(a.max()),
            'mean': float(a.mean()), 'rms': float(np.sqrt(np.mean(a * a)))}


def reconstruct(raw, fraction_bits, exponents):
    return np.ldexp(np.asarray(raw, dtype=np.float64) / float(2 ** fraction_bits),
                    np.asarray(exponents, dtype=np.int32))


def read_dump(path, columns, count):
    path = Path(path)
    if path.stat().st_size == 0:
        raise ValueError(str(path) + ': empty dump')
    a = np.loadtxt(path, dtype=np.int64, ndmin=2)
    if a.shape[1] != columns:
        raise ValueError(str(path) + ': wrong number of columns')
    if a.shape[0] != count:
        raise ValueError(str(path) + ': wrong number of rows')
    if not np.array_equal(a[:, 0], np.arange(count)):
        raise ValueError(str(path) + ': indices must be contiguous')
    return a[:, 1:]


def load_trace(directory):
    d = Path(directory)
    status = json.loads((d / 'run_status.json').read_text(encoding='utf-8'))
    if not status.get('complete'):
        raise ValueError('Native encoder run did not complete; refusing partial/stale dumps')
    if not status.get('mdct_debug'):
        raise ValueError('Latest encoder run has MDCT_DEBUG=OFF; no current stage dumps')
    meta = json.loads((d / 'stage_metadata.json').read_text(encoding='utf-8'))
    if meta.get('schema_version') != 1 or meta.get('pcm_samples') != 2048:
        raise ValueError('expected a complete AAC-LC 1024 trace, schema_version=1')
    names = [('pcm', '00_pcm_input.txt', 2, 2048),
             ('fold', '01_window_fold.txt', 2, 1024),
             ('pre', '02_preprocessing.txt', 3, 512),
             ('fft', '03_fft.txt', 3, 512),
             ('post', '04_postprocessing.txt', 2, 1024),
             ('mdct', '05_mdct_output.txt', 2, 1024),
             ('exponents', '05_mdct_exponents.txt', 2, 1024)]
    data = {name: read_dump(d / file, cols, count) for name, file, cols, count in names}
    for name in ['pcm', 'fold', 'post', 'mdct', 'exponents']:
        data[name] = data[name][:, 0]
    if np.any(data['pcm'] < -32768) or np.any(data['pcm'] > 32767):
        raise ValueError('PCM dump is outside PCM16 range')
    for name in ['fold', 'pre', 'fft', 'post', 'mdct']:
        if np.any(data[name] < -2147483648) or np.any(data[name] > 2147483647):
            raise ValueError(name + ': dump is outside signed Q31 storage range')
    if not np.array_equal(data['post'], data['mdct']):
        raise ValueError('post and final MDCT buffers differ at the transform boundary')
    end = 0
    for s in meta['subtransforms']:
        if s['scalar_offset'] != end or s['M'] != s['L'] // 2:
            raise ValueError('inconsistent subtransform geometry')
        end += s['L']
        if not np.all(data['exponents'][s['scalar_offset']:end] ==
                      s['exponents']['postprocessing']['effective']):
            raise ValueError('coefficient exponent dump disagrees with metadata')
    if end != 1024:
        raise ValueError('subtransforms must cover all 1024 coefficients')
    data['magnitude'] = np.hypot(data['fft'][:, 0].astype(np.float64),
                                 data['fft'][:, 1].astype(np.float64))
    data['restored'] = reconstruct(data['mdct'], meta['data_fraction_bits'], data['exponents'])
    return meta, data


def scale_text(meta, name):
    values = sorted({s['exponents'][name]['effective'] for s in meta['subtransforms']})
    variables = sorted({s['exponents'][name]['variable'] for s in meta['subtransforms']})
    return 'effective e=' + '/'.join(map(str, values)) + ', variable e=' + '/'.join(map(str, variables))


def boundaries(ax, meta, complex_data):
    for s in meta['subtransforms'][1:]:
        x = s['scalar_offset'] // (2 if complex_data else 1)
        ax.axvline(x, color='#9CAAB6', linewidth=0.7, linestyle='--', alpha=0.7)


def draw(ax, values, meta, complex_data=False, labels=None, title='', ylabel='Fixed-point value'):
    a = np.asarray(values)
    if a.ndim == 1:
        ax.plot(np.arange(a.size), a, color='#147A96', linewidth=0.8)
    else:
        for i in range(a.shape[1]):
            ax.plot(np.arange(a.shape[0]), a[:, i], linewidth=0.75,
                    label=(labels or ['Real', 'Imaginary'])[i], color=['#147A96', '#B55835'][i])
        ax.legend(loc='upper right', frameon=False, fontsize=9)
    if title:
        ax.set_title(title, loc='left', fontsize=11, fontweight='bold')
    ax.set_ylabel(ylabel)
    ax.set_xlabel('Complex index (subtransforms concatenated)' if complex_data else 'Sample / coefficient index')
    ax.grid(alpha=0.18)
    ax.axhline(0, color='#8696A6', linewidth=0.5)
    ax.spines[['top', 'right']].set_visible(False)
    if a.shape[0] != 2048:
        boundaries(ax, meta, complex_data)


def generate(directory, plot_dir):
    directory, plot_dir = Path(directory), Path(plot_dir)
    meta, d = load_trace(directory)
    plot_dir.mkdir(parents=True, exist_ok=True)
    context = f"FDK AAC-LC, transform frame {meta['selected_frame']}, channel {meta['channel']}, {meta['block_type']}"
    stats = {'pcm': statistics(d['pcm']), 'window_fold': statistics(d['fold']),
             'pre_real': statistics(d['pre'][:, 0]), 'pre_imag': statistics(d['pre'][:, 1]),
             'fft_real': statistics(d['fft'][:, 0]), 'fft_imag': statistics(d['fft'][:, 1]),
             'fft_magnitude_raw': statistics(d['magnitude']), 'postprocessing': statistics(d['post']),
             'mdct_mantissa_raw': statistics(d['mdct']), 'mdct_restored': statistics(d['restored'])}
    (directory / 'stage_statistics.json').write_text(json.dumps(stats, indent=2) + '\n')
    np.savetxt(directory / '03_fft_magnitude.txt',
               np.column_stack([np.arange(512), d['magnitude']]), fmt=['%d', '%.17g'])
    np.savetxt(directory / '05_mdct_reconstructed.txt',
               np.column_stack([np.arange(1024), d['restored']]), fmt=['%d', '%.17g'])
    tasks = [
        ('00_pcm_input.png', d['pcm'], False, 'PCM input: 2048 samples, PCM16 raw', 'PCM16 integer'),
        ('01_window_fold.png', d['fold'], False, 'Window/Fold: ' + scale_text(meta, 'window_fold'), 'Q31 stored integer'),
        ('02_preprocessing.png', d['pre'], True, 'Pre-processing: ' + scale_text(meta, 'preprocessing'), 'Q31 stored integer'),
        ('03_fft_real.png', d['fft'][:, 0], True, 'FFT real: ' + scale_text(meta, 'fft'), 'Q31 stored integer'),
        ('03_fft_imag.png', d['fft'][:, 1], True, 'FFT imaginary: ' + scale_text(meta, 'fft'), 'Q31 stored integer'),
        ('03_fft_magnitude.png', d['magnitude'], True, 'FFT magnitude from raw Re/Im, visualization only', 'hypot(Re, Im), raw units'),
        ('04_postprocessing.png', d['post'], False, 'Post-processing: ' + scale_text(meta, 'postprocessing'), 'Q31 stored integer'),
        ('05_mdct_output.png', d['mdct'], False, 'Final MDCT: mantissa raw, exponent in 05_mdct_exponents.txt', 'Q31 stored integer'),
        ('05_mdct_reconstructed.png', d['restored'], False, 'Final MDCT: stored_integer / 2^31 * 2^e (FDK convention)', 'Restored FDK value'),
    ]
    for filename, values, complex_data, title, ylabel in tasks:
        fig, ax = plt.subplots(figsize=(12.8, 3.6), constrained_layout=True)
        fig.suptitle(context, fontsize=12)
        draw(ax, values, meta, complex_data, title=title, ylabel=ylabel)
        fig.savefig(plot_dir / filename, dpi=150)
        plt.close(fig)
    overview = [('PCM input', d['pcm'], False, None),
                ('Window/Fold', d['fold'], False, 'window_fold'),
                ('Pre-processing', d['pre'], True, 'preprocessing'),
                ('FFT output', d['fft'], True, 'fft'),
                ('Post-processing', d['post'], False, 'postprocessing'),
                ('Final MDCT', d['mdct'], False, 'postprocessing')]
    maximum = max(float(np.max(np.abs(d[key]))) for key in ['fold', 'pre', 'fft', 'post', 'mdct'])
    maximum = maximum if maximum > 0 else 1.0
    fig, axes = plt.subplots(6, 1, figsize=(14, 15), constrained_layout=True)
    fig.suptitle(context + '\nRaw pipeline: common Q31 y-range, no per-stage normalization', fontsize=15)
    for ax, (title, values, complex_data, stage) in zip(axes, overview):
        if stage:
            title += ' / ' + scale_text(meta, stage)
        draw(ax, values, meta, complex_data, title=title,
             ylabel='PCM16 integer' if stage is None else 'Q31 integer')
        if stage is not None:
            ax.set_ylim(-maximum * 1.08, maximum * 1.08)
    fig.savefig(plot_dir / 'mdct_pipeline_overview.png', dpi=150)
    plt.close(fig)
    print(context)
    for name, s in stats.items():
        print(f"{name:20} n={s['count']:4} min={s['min']:.9g} max={s['max']:.9g} "
              f"mean={s['mean']:.9g} RMS={s['rms']:.9g}")
    print('No peak normalization. SHORT boundaries are dashed; each FFT is independent.')
    print('Plots:', plot_dir.resolve())
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('my_workspace/window_mdct/output'))
    parser.add_argument('--plot-dir', type=Path, default=Path('my_workspace/window_mdct/plots'))
    args = parser.parse_args()
    try:
        generate(args.data_dir, args.plot_dir)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, 'Error: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
