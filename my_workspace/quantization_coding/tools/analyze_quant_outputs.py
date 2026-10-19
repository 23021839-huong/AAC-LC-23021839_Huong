#!/usr/bin/env python3
"""Validate native FDK QC events, export TXT and raw hardware vectors."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from quant_trace_data import load_trace,validate,reconstruct,group_records,find,scalar,ZERO_LD


def text_table(path,header,rows):
    with path.open('w',encoding='utf-8') as stream:
        stream.write('# Native FDK raw; reconstructed columns are display only. NA = unobserved/invalid.\n')
        stream.write(header+'\n')
        for row in rows:
            stream.write(' '.join('NA' if v is None or isinstance(v,float) and not np.isfinite(v) else str(v) for v in row)+'\n')


def event_rows(records):
    for r in records:
        display=reconstruct(r)
        for i in range(r['count']):
            yield [r['sequence'],r['loop_kind'],r['phase'],r['iteration'],r['candidate'],r['sfb'],r['name'],r['index']+i,
                   r['raw'][i],r['raw_hex'][i],r['bit_width'],r['fraction_bits'],r['exponent'],
                   display[i],r['unit'],int(i in r['valid_indices']),r['function'],r['source_line'],r.get('_line',0)]


EVENT_HEADER='sequence loop_kind phase iteration candidate sfb name index raw raw_hex bit_width fraction_bits exponent reconstructed unit native_valid source_function cpp_line trace_line'


def export_vectors(directory,records,frame,channel):
    directory.mkdir(parents=True,exist_ok=True)
    keys=[('input','spectrum','psy_spectrum'),('final','spectrum_before_quant','input_mdct_q31'),
          ('input','offsets','sfb_offsets'),('final','scf_relative','scalefactors'),
          ('final','quantized_spectrum','quantized_spectrum'),('final','max_in_sfb','max_value_in_sfb'),
          ('final','reconstructed_spectrum','inverse_spectrum'),('form_factor','ld','form_factor_ld'),
          ('pe','initial.sfb_pe','pe_initial'),('threshold','after.threshold_ld','threshold_adjusted'),
          ('input','threshold_ld','threshold_initial'),('build','pow34_rom','pow34_rom'),
          ('build','inverse_rom','inverse_rom'),('build','quant_table_q','quant_table_q'),
          ('build','quant_table_e','quant_table_e'),('build','inverse_exponent_mantissa','inverse_exponent_mantissa'),
          ('build','inverse_exponent_shift','inverse_exponent_shift')]
    fields={}
    for stage,name,file in keys:
        r=find(records,stage,name,array=True)
        if not r:continue
        target=directory/(file+'.txt')
        text_table(target,'index raw raw_hex native_valid',((i,v,r['raw_hex'][i],int(i in r['valid_indices'])) for i,v in enumerate(r['raw'])))
        fields[file]={k:r[k] for k in ('sequence','count','bit_width','signed','fraction_bits','exponent','unit','valid_indices','source','function','source_line')}
        fields[file]['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    gain=scalar(records,'final','global_gain')
    text_table(directory/'global_gain.txt','raw',[[gain]])
    metadata=dict(provenance='native FDK-AAC QUANT_DEBUG',frame=frame,channel=channel,
        coefficient_count=1024,global_gain=gain,mdct_scale=find(records,'input','spectrum')['mdct_scale'],
        quant_table_bits=scalar(records,'build','quant_table_bits'),
        fields=fields,byte_order='numeric text; pack little-endian explicitly when building DMA payloads',
        note='Input kernel vector uses spectrum AFTER native QC zeroing. Psy input is a different epoch. This is not a full-state QC checkpoint.')
    (directory/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')


def export(trace: Path,output_dir: Path) -> dict:
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    records=load_trace(trace);report=validate(records)
    summary_by_key={(r['frame'],r['channel']):r for r in report['frames']}
    paths=[]
    for (frame,channel),rs in group_records(records).items():
        folder=output_dir/f'frame_{frame:06d}'/f'channel_{channel}';folder.mkdir(parents=True,exist_ok=True)
        source=find(rs,'input','spectrum');offsets=find(rs,'input','offsets')
        sf=find(rs,'final','scf_relative');optimized=find(rs,'scalefactor','optimized.absolute')
        gain=scalar(rs,'final','global_gain');summary=summary_by_key[frame,channel]
        stage_files={
          '01_form_factor.txt':lambda r:r['stage']=='form_factor',
          '02_pe_per_sfb.txt':lambda r:r['stage']=='pe' and 'channel_pe' not in r['name'] and 'element_pe' not in r['name'],
          '02_pe_total.txt':lambda r:r['stage']=='pe' and ('channel_pe' in r['name'] or 'element_pe' in r['name'] or r['name']=='offset'),
          '03_bit_allocation.txt':lambda r:r['stage']=='bit_allocation',
          '03_bit_reservoir.txt':lambda r:r['stage']=='bit_allocation' and 'reservoir' in r['name'],
          '04_threshold_before.txt':lambda r:r['stage']=='input' and r['name']=='threshold_ld',
          '04_threshold_after.txt':lambda r:r['stage']=='threshold' and r['name']=='after.threshold_ld',
          '04_threshold_iterations.txt':lambda r:r['stage']=='threshold',
          '05_scalefactor_initial.txt':lambda r:r['stage']=='scalefactor' and (r['name'].startswith('seed.') or r['name']=='initialized.absolute'),
          '05_scalefactor_final.txt':lambda r:r['stage']=='scalefactor' and r['name'] in ('optimized.absolute','normalized.relative') or r['stage']=='final' and r['name']=='scf_relative',
          '06_global_gain.txt':lambda r:r['stage']=='global_gain' or r['stage']=='final' and r['name']=='global_gain',
          '06_global_gain_iterations.txt':lambda r:r['stage']=='global_gain' or r['stage']=='iterations' and ('global_gain' in r['name'] or r['name']=='rate.bits'),
          '08_iteration_trace.txt':lambda r:r['stage']=='iterations' or r['stage'] in ('threshold','scalefactor') and r['candidate']>=0,
        }
        for name,predicate in stage_files.items():
            path=folder/name;text_table(path,EVENT_HEADER,event_rows([r for r in rs if predicate(r)]));paths.append(str(path))
        pre=find(rs,'final','spectrum_before_quant');q=find(rs,'final','quantized_spectrum');iq=find(rs,'final','reconstructed_spectrum')
        line_to_band={line:b for b in sf['valid_indices'] for line in range(offsets['raw'][b],offsets['raw'][b+1])}
        for name,r in [('07_spectrum_before.txt',pre),('07_spectrum_quantized.txt',q),('07_spectrum_reconstructed.txt',iq)]:
            path=folder/name;display=reconstruct(r)
            text_table(path,'coefficient_index sfb_index raw raw_hex fraction_bits exponent reconstructed native_valid',
                ((i,line_to_band.get(i),v,r['raw_hex'][i],r['fraction_bits'],r['exponent'],display[i],int(i in r['valid_indices'])) for i,v in enumerate(r['raw'])))
            paths.append(str(path))
        x=reconstruct(pre);original=reconstruct(source);y=reconstruct(iq)
        error=x-y;psy_error=original-y
        text_table(folder/'07_quantization_error.txt',
          'coefficient_index sfb_index mdct_raw mdct_exponent qss quantized_integer inverse_raw inverse_exponent post_qc_error psy_input_error squared_error native_valid',
          ((i,line_to_band.get(i),pre['raw'][i],pre['exponent'],None if i not in line_to_band else gain-sf['raw'][line_to_band[i]],
            q['raw'][i],iq['raw'][i],iq['exponent'],error[i],psy_error[i],error[i]**2,int(i in q['valid_indices'])) for i in range(1024)))
        export_vectors(folder/'vectors',rs,frame,channel)
        # Detailed native trials retain raw values and input epoch in event provenance.
        trial=[r for r in rs if r['candidate']>=0]
        with (folder/'vectors/native_trials.jsonl').open('w',encoding='utf-8') as stream:
            for r in trial:stream.write(json.dumps({k:v for k,v in r.items() if k!='_line'},separators=(',',':'))+'\n')
        (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        if optimized:
            seeds={r['index']:r['raw'][0] for r in rs if r['stage']=='scalefactor' and r['name']=='seed.absolute'}
            text_table(folder/'05_scalefactor_comparison.txt','sfb initial_absolute optimized_absolute final_relative final_qss',
                ((b,seeds.get(b),optimized['raw'][b],sf['raw'][b],gain-sf['raw'][b]) for b in sf['valid_indices']))
    text_table(output_dir/'02_pe_total.txt','frame channel initial_pe adjusted_pe',
        ((r['frame'],r['channel'],r['initial_pe'],r['adjusted_pe']) for r in report['frames']))
    text_table(output_dir/'03_bit_allocation.txt','frame channel target_element_dynamic_bits actual_element_dynamic_bits channel_dynamic_bits',
        ((r['frame'],r['channel'],r['target_dynamic_bits'],r['element_dynamic_bits'],r['channel_dynamic_bits']) for r in report['frames']))
    text_table(output_dir/'03_bit_reservoir.txt','frame channel reservoir_bits',
        ((r['frame'],r['channel'],r['reservoir']) for r in report['frames']))
    text_table(output_dir/'06_global_gain.txt','frame channel global_gain distortion_trials rate_passes',
        ((r['frame'],r['channel'],r['global_gain'],r['distortion_trials'],r['rate_passes']) for r in report['frames']))
    report['txt_paths']=paths
    (output_dir/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace',type=Path,default=Path('my_workspace/quantization_coding/output/quant/native_trace.jsonl'))
    parser.add_argument('--output-dir',type=Path,default=Path('my_workspace/quantization_coding/output/quant'))
    args=parser.parse_args()
    report=export(args.trace,args.output_dir)
    print(f"Validated {len(report['frames'])} frame/channel pairs; {report['native_max_checks']} native max/SFB checks")


if __name__=='__main__':main()
