"""Read native FDK events. Floating reconstruction is display, not a DSP model."""
from collections import defaultdict, Counter
import json
from pathlib import Path
import numpy as np

STAGES=('form_factor','pe','bit_allocation','threshold','scalefactor','global_gain','quantization','iterations')
BLOCKS=('LONG','START','SHORT','STOP')
ZERO_LD=-(1<<31)
# Unconditional observation points for the scoped native AAC-LC CBR workflow.
# Per-line/candidate/conditional recovery events are deliberately not mandatory.
MANDATORY_STAGE_RECORDS={
    'form_factor':('ld',),
    'pe':('initial.sfb_pe','initial.channel_pe','computed.channel_pe'),
    'bit_allocation':('granted.average_bits','granted.available_bits','granted.reservoir',
        'before_commit.reservoir','committed.reservoir','committed.granted_dyn_bits',
        'committed.used_dyn_bits','committed.fill_bits','committed.alignment_bits'),
    'threshold':('before_weighted.threshold_ld','after.threshold_ld'),
    'scalefactor':('optimized.absolute','normalized.relative'),
    'global_gain':('initial','syntax'),
    'quantization':('normalized.spectrum',),
    'iterations':('rate.global_gain','rate.maximum_quantized','rate.range_valid','rate.bits','rate.accepted'),
}


def validate_record(r):
    required=('schema_version','sequence','frame','element','channel','stage','name','raw','raw_hex',
              'count','bit_width','signed','fraction_bits','exponent','unit','valid_indices',
              'sample_rate','frame_length','block_type','mdct_scale','sfb_count','sfb_per_group',
              'max_sfb_per_group','stage_mask','source','function','source_line')
    if any(k not in r for k in required):raise ValueError('missing event metadata')
    if r['schema_version']!=1:raise ValueError('unsupported schema version')
    if r['frame']<0 or r['channel'] not in (0,1) or r['block_type'] not in range(4):raise ValueError('invalid frame/channel/window')
    if r['frame_length']!=1024 or r['sample_rate']<=0:raise ValueError('invalid AAC-LC frame/Fs')
    bands,stride,active=r['sfb_count'],r['sfb_per_group'],r['max_sfb_per_group']
    if not all(isinstance(v,int) for v in (bands,stride,active)) or not 0<=active<=stride<=128 or stride<1 or not 0<=bands<=128 or bands%stride:raise ValueError('invalid SFB/group geometry')
    if not isinstance(r['stage_mask'],int) or not 0<=r['stage_mask']<=255:raise ValueError('invalid stage mask')
    width=r['bit_width']
    if width not in (8,16,32,64) or not 0<=r['fraction_bits']<width:raise ValueError('invalid raw format')
    if not isinstance(r['exponent'],int) or not -256<=r['exponent']<=256:raise ValueError('invalid exponent')
    if not isinstance(r['raw'],list) or not 0<=r['count']<=2048 or r['count']!=len(r['raw']) or len(r['raw_hex'])!=r['count']:raise ValueError('count mismatch')
    indices=r['valid_indices']
    if not isinstance(indices,list) or indices!=sorted(set(indices)) or any(not isinstance(i,int) or not 0<=i<r['count'] for i in indices):raise ValueError('invalid validity mask')
    valid=set(indices)
    lo=-(1<<(width-1)) if r['signed'] else 0
    hi=(1<<(width-1)) if r['signed'] else (1<<width)
    for i,(v,h) in enumerate(zip(r['raw'],r['raw_hex'])):
        if i not in valid:
            if v is not None or h is not None:raise ValueError('invalid native slot must be null')
            continue
        if not isinstance(v,int) or isinstance(v,bool) or not lo<=v<hi:raise ValueError('raw outside bit width')
        if h!=f'{v&((1<<width)-1):0{width//4}X}':raise ValueError('raw decimal/hex mismatch')
    return r


def load_trace(path: Path) -> list[dict]:
    records=[];last=0
    with Path(path).open(encoding='utf-8') as stream:
        for number,line in enumerate(stream,1):
            try:
                r=validate_record(json.loads(line))
                if r['sequence']<=last:raise ValueError('event sequence is not increasing')
                last=r['sequence'];r['_line']=number;records.append(r)
            except (ValueError,TypeError,KeyError) as e:raise ValueError(f'{path}:{number}: {e}') from e
    if not records:raise ValueError('empty native trace')
    return records


def reconstruct(r: dict) -> np.ndarray:
    raw=np.asarray(r['raw'],dtype=float)
    fraction=r['fraction_bits'];unit=r['unit'];exp=r['exponent']
    if unit in ('ld64','form_factor_ld'):
        correction=6+r['mdct_scale']/2 if unit=='form_factor_ld' else exp
        value=np.exp2(raw/(1<<fraction)*64+correction)
        value=np.where(raw==ZERO_LD,0,value)
    else:
        correction=6+r['mdct_scale']/2 if unit=='form_factor' else exp
        value=raw/(1<<fraction)*np.exp2(correction)
    mask=np.zeros(r['count'],dtype=bool);mask[r['valid_indices']]=True
    return np.where(mask,value,np.nan)


def group_records(records: list[dict]):
    groups=defaultdict(list)
    for r in records:groups[r['frame'],r['channel']].append(r)
    return dict(sorted(groups.items()))


def find(records,stage,name,last=False,array=False):
    matches=[r for r in records if r['stage']==stage and r['name']==name and (not array or r['count']>1)]
    return matches[-1 if last else 0] if matches else None


def scalar(records,stage,name,last=False):
    r=find(records,stage,name,last)
    return r['raw'][0] if r else None


def validate(records: list[dict]) -> dict:
    groups=group_records(records);frames=[];checks=0
    if not groups:raise ValueError('missing native frame/channel records')
    coverage=Counter()
    for (frame,channel),rs in groups.items():
        source=find(rs,'input','spectrum');offsets=find(rs,'input','offsets')
        q=find(rs,'final','quantized_spectrum');maxima=find(rs,'final','max_in_sfb')
        sf=find(rs,'final','scf_relative');iq=find(rs,'final','reconstructed_spectrum')
        gain=scalar(rs,'final','global_gain')
        if any(r is None for r in (source,offsets,q,maxima,sf,iq)) or gain is None:raise ValueError(f'{frame}/{channel}: missing native interface/final result')
        if source['count']!=1024 or q['count']!=1024 or iq['count']!=1024:raise ValueError('spectrum count must be 1024')
        if iq['exponent']!=source['mdct_scale']+1:raise ValueError('inverse half-scale contract mismatch')
        for r in rs:
            validate_record(r)
            if any(r[k]!=source[k] for k in ('frame','channel','block_type','mdct_scale','sample_rate','sfb_count','sfb_per_group','max_sfb_per_group','stage_mask','iteration_log','line_log')):raise ValueError('inconsistent channel context')
            coverage[r['loop_kind']+'.'+r['phase']]+=1
        for bit,stage in enumerate(STAGES):
            if not source['stage_mask']&(1<<bit) or stage=='iterations' and not source['iteration_log']:continue
            for name in MANDATORY_STAGE_RECORDS[stage]:
                if find(rs,stage,name) is None:raise ValueError(f'{frame}/{channel}: selected {stage} stage missing {name}')
        # Threshold adaptation is conditional, unlike the before/after snapshots.
        if find(rs,'threshold','desired_pe') is not None:
            for name in ('first_guess.pe','reduction_m','first_guess.threshold_ld'):
                if find(rs,'threshold',name) is None:raise ValueError(f'{frame}/{channel}: threshold adaptation missing {name}')
        for b in maxima['valid_indices']:
            start,stop=offsets['raw'][b:b+2]
            if start is None or stop is None or not 0<=start<=stop<=1024:raise ValueError('invalid active SFB offsets')
            values=q['raw'][start:stop]
            if any(v is None or abs(v)>8191 for v in values):raise ValueError('accepted quantized coefficient invalid/out of range')
            if max(map(abs,values),default=0)!=maxima['raw'][b]:raise ValueError('native max/SFB differs from q')
            checks+=1
        initial=scalar(rs,'pe','initial.channel_pe')
        after=scalar(rs,'pe','computed.channel_pe',last=True)
        components=[scalar(rs,'final',name) for name in ('huffman_bits','side_info_bits','scalefactor_bits','noise_bits')]
        if any(v is None for v in components):raise ValueError(f'{frame}/{channel}: missing mandatory final bit component')
        bits=sum(components)
        last_bits=scalar(rs,'iterations','rate.bits',last=True)
        if last_bits is not None and last_bits!=bits:raise ValueError('native final bit breakdown mismatch')
        before=scalar(rs,'bit_allocation','before_commit.reservoir')
        committed=scalar(rs,'bit_allocation','committed.reservoir')
        target=scalar(rs,'bit_allocation','committed.granted_dyn_bits')
        actual=scalar(rs,'bit_allocation','committed.used_dyn_bits')
        fill=scalar(rs,'bit_allocation','committed.fill_bits')
        align=scalar(rs,'bit_allocation','committed.alignment_bits')
        if all(v is not None for v in (before,committed,target,actual,fill,align)) and committed!=before+target-actual-fill-align:raise ValueError('native CBR reservoir update mismatch')
        frames.append(dict(frame=frame,channel=channel,block=BLOCKS[source['block_type']],
            mdct_scale=source['mdct_scale'],active_coefficients=len(q['valid_indices']),
            initial_pe=initial,adjusted_pe=after,global_gain=gain,channel_dynamic_bits=bits,
            target_dynamic_bits=target,element_dynamic_bits=actual,reservoir=committed,
            tns_filters=sum(r['raw'][0] for r in rs if r['stage']=='input' and r['name']=='tns_num_filters'),
            pns_bands=sum(v is not None and v!=ZERO_LD for v in find(rs,'final','noise_nrg')['raw']),
            distortion_trials=sum(r['stage']=='iterations' and r['name']=='trial.distortion_ld' for r in rs),
            rate_passes=len({r['iteration'] for r in rs if r['loop_kind']=='rate' and r['iteration']>=0}),
            threshold_iterations=len({r['iteration'] for r in rs if r['loop_kind']=='threshold' and r['iteration']>=0})))
    return dict(valid=True,schema_version=1,record_count=len(records),native_max_checks=checks,
        frames=frames,coverage=dict(coverage),
        note='Raw values from native FDK. Reconstruction is display only; frame indices include priming/flush.')
