"""Read native Psy events. Reconstruction is visualization, never a replacement DSP."""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

NO_NOISE_PNS = -(1 << 31)
BLOCKS = ('LONG', 'START', 'SHORT', 'STOP')


def validate_record(r):
    required = ('frame', 'channel', 'window', 'block_type', 'window_shape', 'sample_rate',
                'frame_length', 'window_length', 'stage', 'name', 'count', 'index',
                'fraction_bits', 'exponent', 'unit', 'raw')
    if any(k not in r for k in required):
        raise ValueError('missing metadata: ' + ','.join(k for k in required if k not in r))
    if not isinstance(r['raw'], list) or r['count'] != len(r['raw']) or not 0 <= r['count'] <= 2048:
        raise ValueError('buffer count mismatch')
    if r['frame'] < 0 or r['channel'] not in (0, 1) or r['block_type'] not in range(4):
        raise ValueError('invalid frame/channel/block')
    short = r['block_type'] == 2
    if r['frame_length'] != 1024 or r['window_length'] != (128 if short else 1024):
        raise ValueError('invalid AAC-LC dimensions')
    if r['window'] < -1 or r['window'] >= (8 if short else 1):
        raise ValueError('invalid window index')
    if r['sample_rate'] <= 0 or r['fraction_bits'] not in (0, 15, 31):
        raise ValueError('invalid fixed-point format')
    if not isinstance(r['exponent'], int) or not -128 <= r['exponent'] <= 128:
        raise ValueError('invalid exponent')
    width = r.get('bit_width', 16 if r['fraction_bits'] == 15 else 32)
    if width not in (16, 32):
        raise ValueError('unsupported raw bit width')
    if 'valid_indices' in r:
        indices = r['valid_indices']
        if not isinstance(indices, list) or any(not isinstance(i, int) or i < 0 or i >= r['count'] for i in indices) or indices != sorted(set(indices)):
            raise ValueError('invalid native valid_indices')
    valid = set(r.get('valid_indices', range(r['count'])))
    for i, v in enumerate(r['raw']):
        if v is None and i not in valid:
            continue
        if not isinstance(v, int) or isinstance(v, bool) or not -(1 << (width-1)) <= v < (1 << (width-1)):
            raise ValueError('raw value outside signed bit width or null in a valid native slot')
    if r['name'] == 'offsets':
        offsets = [r['raw'][i] for i in r.get('valid_indices', range(r['count']))]
        if len(offsets) < 2 or offsets[0] != 0 or any(b <= a for a, b in zip(offsets, offsets[1:])):
            raise ValueError('inconsistent SFB offsets')
        limit = 1024 if r['stage'] == 'output' else r['window_length']
        if offsets[-1] > limit:
            raise ValueError('SFB offset outside spectrum')
    return r


def load_trace(path):
    records = []
    with Path(path).open(encoding='utf-8') as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                r = validate_record(json.loads(line))
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f'{path}:{line_number}: {exc}') from exc
            r['_line'] = line_number
            records.append(r)
    if not records:
        raise ValueError('empty native trace')
    return records


def reconstruct(r):
    raw = np.asarray(r['raw'], dtype=np.float64)
    if r['unit'] == 'ld64':
        values = np.exp2(raw / (1 << r['fraction_bits']) * 64 + r['exponent'])
        result = np.where(raw == -(1 << 31), 0.0, values)
    else:
        result = np.ldexp(raw / (1 << r['fraction_bits']), r['exponent'])
    if 'valid_indices' in r:
        valid = np.zeros(r['count'], dtype=bool)
        valid[r['valid_indices']] = True
        result = np.where(valid, result, np.nan)
    return result


def group_records(records):
    result = defaultdict(list)
    for r in records:
        result[(r['frame'], r['channel'])].append(r)
    return dict(sorted(result.items()))


def find(records, stage, name, window=None):
    return next((r for r in records if r['stage'] == stage and r['name'] == name and
                 (window is None or r['window'] == window)), None)


def validate(records):
    groups = group_records(records)
    summary = []
    energy_checks = 0
    for (frame, channel), rs in groups.items():
        for r in rs:
            validate_record(r)
        mdct = find(rs, 'mdct', 'input')
        output = find(rs, 'output', 'spectrum')
        offsets = find(rs, 'context', 'offsets')
        if mdct is None or output is None or offsets is None:
            raise ValueError(f'frame {frame} channel {channel}: incomplete native stage sequence')
        if mdct['count'] != 1024 or output['count'] != 1024 or offsets['raw'][-1] != mdct['window_length']:
            raise ValueError('spectrum/SFB size mismatch')
        identity = ('frame', 'channel', 'block_type', 'window_shape', 'sample_rate', 'frame_length', 'window_length')
        if any(any(r[key] != mdct[key] for key in identity) for r in rs):
            raise ValueError('inconsistent frame/channel/window metadata')
        for r in rs:
            if r['stage'] in ('energy', 'masking') and r['unit'] == 'pcm_squared' and any(v < 0 for v in r['raw'] if v is not None):
                raise ValueError('negative linear energy/threshold')
            if r['stage'] == 'tonality' and r['name'] == 'index' and any(not 0 <= v <= 32767 for v in r['raw']):
                raise ValueError('tonality outside Q15 [0,1]')
            if r['stage'] == 'energy' and r['name'] == 'local.energy':
                scaled = find(rs, 'energy', 'scaled.energy', r['window'])
                if scaled:
                    shift = r['exponent'] - scaled['exponent']
                    expected = r['raw'][0] << shift if shift >= 0 else r['raw'][0] >> min(-shift, 31)
                    if expected != scaled['raw'][r['index']]:
                        raise ValueError('native energy normalization differs from recorded local shift')
                    energy_checks += 1
        enabled = find(rs, 'context', 'pns_enabled')['raw'][0]
        noise = find(rs, 'output', 'noise_nrg')
        if not enabled and any(v != NO_NOISE_PNS for v in noise['raw'] if v is not None):
            raise ValueError('disabled PNS has a coded noise band')
        if not enabled and find(rs, 'tonality', 'index') is not None:
            raise ValueError('tonality computed although PNS disabled')
        filters = [r for r in rs if r['stage'] == 'tns' and r['name'] == 'final.num_filters']
        summary.append(dict(frame=frame, channel=channel, block=BLOCKS[mdct['block_type']],
                            mdct_exponent=mdct['exponent'], output_exponent=output['exponent'],
                            windows=8 if mdct['block_type'] == 2 else 1,
                            sfb_count=len(offsets['raw'])-1,
                            pns_enabled=bool(enabled), pns_bands=sum(v is not None and v != NO_NOISE_PNS for v in noise['raw']),
                            tns_filters=sum(r['raw'][0] for r in filters) if filters else None,
                            tns_observed=bool(filters),
                            tonality_observed=find(rs, 'tonality', 'index') is not None))
    return dict(valid=True, schema_version=1, record_count=len(records),
                native_energy_shift_checks=energy_checks, frames=summary,
                note='Raw values are native FDK. Floating values are derived display only; frame IDs include priming/flush.')
