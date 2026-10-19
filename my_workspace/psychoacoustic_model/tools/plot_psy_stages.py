#!/usr/bin/env python3
"""Plot real native Psy events; skipped algorithms are annotated, not synthesized."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from psy_trace_data import BLOCKS, NO_NOISE_PNS, find, group_records, load_trace, reconstruct, validate


def db(values):
    values = np.asarray(values)
    result = np.full(values.shape, np.nan, dtype=float)
    positive = values > 0
    result[positive] = 10 * np.log10(values[positive])
    return result


def plot(trace, directory, frame=None, channel=0, window=0):
    records = load_trace(trace)
    report = validate(records)
    groups = {k: v for k, v in group_records(records).items() if k[1] == channel}
    if not groups:
        raise ValueError('selected channel not present in trace')
    if frame is None:
        frame = max(groups, key=lambda k: float(np.nansum(reconstruct(find(groups[k], 'output', 'energy')))))[0]
    if (frame, channel) not in groups:
        raise ValueError('selected plot frame not present in trace')
    rs = groups[(frame, channel)]
    mdct = find(rs, 'mdct', 'input')
    windows = 8 if mdct['block_type'] == 2 else 1
    if not 0 <= window < windows:
        raise ValueError('plot window outside native frame')
    n = mdct['window_length']
    title = f"Frame {frame}, channel {channel}, {BLOCKS[mdct['block_type']]}, window {window}, Fs={mdct['sample_rate']} Hz"
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.size': 9, 'axes.grid': True, 'grid.alpha': .2})
    plots = []

    def missing(ax, text):
        ax.text(.5, .5, text, transform=ax.transAxes, ha='center', va='center', wrap=True)

    def spectrum(ax, boundaries=False):
        values = reconstruct(mdct)[window*n:(window+1)*n]
        ax.plot(values, linewidth=.8, color='#1768ac')
        if boundaries:
            offsets = find(rs, 'context', 'offsets')['raw']
            for off in offsets:
                ax.axvline(off, color='#bd5b17', alpha=.35, linewidth=.6)
        else:
            offsets = find(rs, 'context', 'offsets')['raw']
            for b, (start, end) in enumerate(zip(offsets, offsets[1:])):
                ax.plot(np.arange(start, end), values[start:end], linewidth=.9,
                        color=plt.get_cmap('tab20')(b % 20))
        ax.set(xlabel='Local MDCT bin', ylabel=f"MDCT value (raw/2^31 * 2^{mdct['exponent']})", title='Native MDCT input / SFB boundaries' if boundaries else 'Coefficients in SFBs')

    def band_energy(ax, logarithmic=False):
        r = find(rs, 'energy', 'post_tns.energy', window)
        if r:
            values = reconstruct(r)
            ax.plot(db(values) if logarithmic else values, '.-', linewidth=1)
            ax.set_title(f"Band energy after TNS; energy exponent={r['exponent']}")
        else:
            missing(ax, 'Energy debug stage not selected')
        ax.set(xlabel='Local SFB index', ylabel='Energy (dB re normalized PCM squared)' if logarithmic else 'Energy (normalized PCM squared)')

    def masking(ax, compare=False):
        count = 0
        if compare:
            r = find(rs, 'energy', 'post_tns.energy', window)
            if r:
                ax.plot(db(reconstruct(r)), '.-', label=f"Energy e={r['exponent']}")
                count += 1
        phases = ('final',) if compare else ('scaled.seed', 'post_tns.seed', 'clipped', 'spread', 'pcm_floor', 'pre_echo', 'final')
        for name in phases:
            r = find(rs, 'masking', name, window)
            if r:
                ax.plot(db(reconstruct(r)), '.-', linewidth=.9, label=f"{name}, e={r['exponent']}")
                count += 1
        if count:
            ax.legend(fontsize=7)
        else:
            missing(ax, 'Masking debug stage not selected')
        ax.set(xlabel='Local SFB index', ylabel='10 log10(value), re normalized PCM squared', title='Energy vs final pre-grouping threshold' if compare else 'Native threshold phases on one numeric scale')

    def tonality(ax):
        r = find(rs, 'tonality', 'index')
        if r:
            ax.plot(reconstruct(r), '.-', color='#6d3291')
        else:
            enabled = find(rs, 'context', 'pns_enabled')['raw'][0]
            reason = 'PNS config disabled' if not enabled else ('AAC-LC SHORT skips tonality' if windows == 8 else 'Tonality debug not selected')
            missing(ax, reason + '\nNo estimator output invented')
        ax.set(xlabel='SFB index', ylabel='Tonality (Q15 / 2^15)', ylim=(-.05, 1.05), title='Tonality: 0 noise-like / 1 tonal')

    def tns(ax):
        before, after = find(rs, 'tns', 'before'), find(rs, 'tns', 'after')
        if before and after:
            ax.plot(reconstruct(before)[window*n:(window+1)*n], label=f"Before e={before['exponent']}", alpha=.7)
            ax.plot(reconstruct(after)[window*n:(window+1)*n], label=f"After e={after['exponent']}", alpha=.7)
            ax.legend(fontsize=7)
            filters = find(rs, 'tns', 'final.num_filters', window)
            ax.set_title(f"TNS before/after; native filters={filters['raw'][0] if filters else 'unobserved'}")
        else:
            missing(ax, 'TNS debug stage not selected')
        ax.set(xlabel='Local MDCT bin', ylabel='MDCT value; separate exponents applied')

    def pns(ax, energy_plot=False):
        r = find(rs, 'pns', 'final.noise_nrg')
        if r:
            native_valid = np.zeros(r['count'], dtype=bool)
            native_valid[r.get('valid_indices', list(range(r['count'])))] = True
            used = np.asarray([v is not None and v != NO_NOISE_PNS for v in r['raw']]) & native_valid
            if energy_plot:
                ax.plot(np.flatnonzero(used), np.asarray(r['raw'])[used], 'o', label='Coded noise energy index')
                band = find(rs, 'output', 'energy')
                if band:
                    other = ax.twinx()
                    other.plot(db(reconstruct(band)), color='#1768ac', alpha=.5, linewidth=.9)
                    other.set_ylabel('Band energy (dB re normalized PCM squared)', color='#1768ac')
                if not used.any():
                    missing(ax, 'No native PNS band selected\nNO_NOISE_PNS remains a sentinel')
                ax.set_ylabel('noiseNrg integer (not linear energy)')
            else:
                ax.bar(np.flatnonzero(native_valid), used[native_valid].astype(int), color='#238b45')
                ax.set(ylim=(-.05, 1.15), ylabel='PNS used: 0 / 1')
            ax.set_title('Final PNS after stereo/PNS coding; grouped SFB for SHORT')
        else:
            missing(ax, 'PNS debug stage not selected')
        ax.set_xlabel('Final output SFB index')

    figures = [
        ('01_sfb_boundaries.png', lambda ax: spectrum(ax, True)),
        ('01_sfb_coefficients.png', spectrum),
        ('02_band_energy.png', band_energy),
        ('02_band_energy_db.png', lambda ax: band_energy(ax, True)),
        ('03_masking_threshold.png', masking),
        ('03_energy_vs_threshold.png', lambda ax: masking(ax, True)),
        ('04_tonality.png', tonality),
        ('05_tns_before_after.png', tns),
        ('06_pns_decisions.png', pns),
        ('06_pns_energy.png', lambda ax: pns(ax, True)),
    ]
    for name, draw in figures:
        fig, ax = plt.subplots(figsize=(11, 4.7))
        draw(ax)
        fig.suptitle(title, fontsize=10)
        fig.tight_layout(rect=(0, 0, 1, .94))
        fig.savefig(directory/name, dpi=150)
        plt.close(fig)
        plots.append(name)
    fig, axes = plt.subplots(2, 1, figsize=(11, 7))
    refs = [r for r in rs if r['stage'] == 'tns' and r['name'].startswith('reflection_') and r['window'] == window]
    coefs = [r for r in rs if r['stage'] == 'tns' and r['name'] == 'final.quantized_coef' and r['window'] == window]
    for r in refs:
        axes[0].plot(reconstruct(r), '.-', label=r['name'])
    for r in coefs:
        axes[1].plot(r['raw'], '.-', label=f"Filter {r.get('filter', r['index'])}")
    for ax, events, label in zip(axes, (refs, coefs), ('Candidate ParCor (decoded fixed point)', 'Accepted quantized coefficient index')):
        if events:
            ax.legend()
        else:
            missing(ax, 'No native coefficients at this step')
        ax.set(xlabel='Coefficient index', ylabel=label)
    fig.suptitle(title)
    fig.tight_layout(rect=(0, 0, 1, .94))
    fig.savefig(directory/'05_tns_coefficients.png', dpi=150)
    plt.close(fig)
    plots.append('05_tns_coefficients.png')
    fig, axes = plt.subplots(3, 2, figsize=(14, 11))
    for ax, draw in zip(axes.flat, (lambda ax: spectrum(ax, True), lambda ax: masking(ax, True), tonality, tns, pns, lambda ax: pns(ax, True))):
        draw(ax)
    fig.suptitle(title + '\nNative FDK Psy survey; reconstructed values are display only', fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .94))
    fig.savefig(directory/'psy_overview.png', dpi=150)
    plt.close(fig)
    plots.append('psy_overview.png')
    timeline = [r for r in report['frames'] if r['channel'] == channel]
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    x = [r['frame'] for r in timeline]
    axes[0].plot(x, [r['output_exponent'] for r in timeline], '.-')
    axes[0].set_ylabel('Output spectrum exponent')
    axes[1].plot(x, [r['tns_filters'] if r['tns_observed'] else np.nan for r in timeline], '.-', label='TNS filters (unobserved omitted)')
    axes[1].plot(x, [r['pns_bands'] for r in timeline], '.-', label='PNS bands')
    axes[1].legend()
    axes[1].set_ylabel('Native tool counts')
    axes[2].plot(x, [BLOCKS.index(r['block']) for r in timeline], '.-')
    axes[2].set(yticks=range(4), yticklabels=BLOCKS, ylabel='Window sequence', xlabel='Native frame index (priming/flush included)')
    fig.suptitle(f'Psy evolution over {len(timeline)} selected frames, channel {channel}')
    fig.tight_layout()
    fig.savefig(directory/'07_frame_evolution.png', dpi=150)
    plt.close(fig)
    plots.append('07_frame_evolution.png')
    return dict(frame=frame, channel=channel, window=window, plots=plots)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace', type=Path, default=Path('my_workspace/psychoacoustic_model/output/psy/native_trace.jsonl'))
    p.add_argument('--output-dir', type=Path, default=Path('my_workspace/psychoacoustic_model/plots/psy'))
    p.add_argument('--frame', type=int)
    p.add_argument('--channel', type=int, default=0)
    p.add_argument('--window', type=int, default=0)
    a = p.parse_args()
    try:
        result = plot(a.trace, a.output_dir, a.frame, a.channel, a.window)
    except (OSError, ValueError) as exc:
        p.exit(1, f'Error: {exc}\n')
    print(f"Created {len(result['plots'])} PNGs for frame {result['frame']}, channel {result['channel']}")


if __name__ == '__main__':
    main()
