#!/usr/bin/env python3
"""Validate native Psy JSONL and export lossless raw vectors plus derived tables."""
import argparse
import json
from pathlib import Path

from psy_trace_data import NO_NOISE_PNS, find, group_records, load_trace, reconstruct, validate


def write_events(path, records):
    with path.open('w', encoding='utf-8') as out:
        out.write('# Raw FDK vectors; reconstructed is Python-only display. Exponent uses raw * 2^(exponent-fraction_bits).\n')
        out.write('# ld64: 2^(64*raw/2^31+exponent); -2147483648 is zero sentinel. integer is not linear noise energy.\n')
        out.write('frame channel window name filter index raw fraction_bits exponent reconstructed unit native_valid source_line\n')
        for r in records:
            values = reconstruct(r)
            for i, (raw, val) in enumerate(zip(r['raw'], values)):
                out.write(f"{r['frame']} {r['channel']} {r['window']} {r['name']} {r.get('filter', -1)} {r['index']+i} {raw if raw is not None else 'NA'} "
                          f"{r['fraction_bits']} {r['exponent']} {val:.17g} {r['unit']} "
                          f"{int(i in r.get('valid_indices', range(r['count'])))} {r['_line']}\n")


def export(trace, output):
    records = load_trace(trace)
    report = validate(records)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        '02_band_energy.txt': lambda r: r['stage'] == 'energy',
        '03_masking_threshold.txt': lambda r: r['stage'] == 'masking',
        '04_tonality.txt': lambda r: r['stage'] == 'tonality',
        '05_tns_parameters.txt': lambda r: r['stage'] == 'tns' and r['name'] not in ('before', 'after', 'filter_input', 'filter_output'),
        '05_tns_before.txt': lambda r: r['stage'] == 'tns' and r['name'] in ('before', 'filter_input'),
        '05_tns_after.txt': lambda r: r['stage'] == 'tns' and r['name'] in ('after', 'filter_output'),
        '06_pns_intermediates.txt': lambda r: r['stage'] == 'pns',
        '07_psy_output.txt': lambda r: r['stage'] == 'output',
        '00_mdct_input.txt': lambda r: r['stage'] == 'mdct',
    }
    for name, predicate in files.items():
        selected = [r for r in records if predicate(r)]
        write_events(output / name, selected)
    with (output / '01_sfb_offsets.txt').open('w', encoding='utf-8') as out, \
         (output / '01_sfb_coefficients.txt').open('w', encoding='utf-8') as coef, \
         (output / '06_pns_decisions.txt').open('w', encoding='utf-8') as pns, \
         (output / '06_pns_energy.txt').open('w', encoding='utf-8') as energy:
        out.write('frame channel window sfb_index start_bin end_bin num_coefficients\n')
        coef.write('frame channel window sfb_index local_bin global_bin mdct_raw mdct_exponent reconstructed\n')
        pns.write('frame channel sfb_index pns_used noise_nrg_raw native_valid skip_reason\n')
        energy.write('# noise_nrg_raw is a coded logarithmic integer parameter, not linear energy; -2147483648 means NO_NOISE_PNS.\n')
        energy.write('frame channel sfb_index pns_used noise_nrg_raw native_valid band_energy_exponent band_energy_reconstructed\n')
        for (f, ch), rs in group_records(records).items():
            mdct = find(rs, 'mdct', 'input')
            offsets = find(rs, 'sfb', 'offsets')
            if offsets:
                decoded = reconstruct(mdct)
                for w in range(8 if mdct['block_type'] == 2 else 1):
                    base = w * mdct['window_length']
                    for b, (start, end) in enumerate(zip(offsets['raw'], offsets['raw'][1:])):
                        out.write(f'{f} {ch} {w} {b} {start} {end} {end-start}\n')
                        for k in range(start, end):
                            coef.write(f"{f} {ch} {w} {b} {k} {base+k} {mdct['raw'][base+k]} {mdct['exponent']} {decoded[base+k]:.17g}\n")
            noise = find(rs, 'pns', 'final.noise_nrg')
            final_energy = find(rs, 'output', 'energy')
            if noise:
                skip = find(rs, 'pns', 'skip_reason')
                reason = skip['raw'][0] if skip else -1
                values = reconstruct(final_energy)
                for b, nrg in enumerate(noise['raw']):
                    valid = b in noise.get('valid_indices', range(noise['count']))
                    used = int(nrg != NO_NOISE_PNS) if valid else 'NA'
                    pns.write(f"{f} {ch} {b} {used} {nrg if valid else 'NA'} {int(valid)} {reason}\n")
                    energy.write(f"{f} {ch} {b} {used} {nrg if valid else 'NA'} {int(valid)} {final_energy['exponent']} {values[b]:.17g}\n")
    (output / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    notes = ['# Native Psy survey', '',
             'Sequence: MDCT -> lowpass -> energy/headroom scaling -> tonality -> TNS detect/sync/filter -> energy update -> masking/pre-echo -> short grouping -> PNS detect -> stereo tools -> PNS coding -> PSY_OUT.',
             '', 'File rows identify frame/channel/window. end_bin is exclusive. Frame IDs include priming/flush.',
             'TNS before/after use their own exponents. Final PSY_OUT may be grouped and modified by stereo tools.',
             'PNS energy is an integer coding parameter; encoder does not synthesize random noise.', '',
             '| Frame | Ch | Block | MDCT e | Output e | TNS filters | PNS bands | Tonality observed |',
             '|---|---|---|---:|---:|---:|---:|---|']
    for r in report['frames']:
        notes.append(f"| {r['frame']} | {r['channel']} | {r['block']} | {r['mdct_exponent']} | {r['output_exponent']} | {r['tns_filters']} | {r['pns_bands']} | {r['tonality_observed']} |")
    notes += ['', 'Absent tonality: PNS disabled, SHORT/LFE skipped, or debug stage not selected.',
              'TNS config disabled: context.tns_enabled=0; enabled with zero filters: native decision rejected candidates.',
              'PNS skip_reason: 0=detection ran, 1=config disabled, 2=AAC-LC SHORT; -1=not observed.',
              'No hardcoded fake values are used for inactive stages. See native_trace.jsonl and validation.json.']
    (output / 'analysis.md').write_text('\n'.join(notes)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, default=Path('my_workspace/psychoacoustic_model/output/psy/native_trace.jsonl'))
    parser.add_argument('--output-dir', type=Path, default=Path('my_workspace/psychoacoustic_model/output/psy'))
    args = parser.parse_args()
    try:
        report = export(args.trace, args.output_dir)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Error: {exc}\n')
    print(f"Validated {len(report['frames'])} frame/channel pairs; {report['native_energy_shift_checks']} exact energy-shift checks")


if __name__ == '__main__':
    main()
