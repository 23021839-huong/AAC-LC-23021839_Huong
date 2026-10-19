#!/usr/bin/env python3
"""Plot validated native QC data; no forward quantizer or synthetic DSP output."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from quant_trace_data import load_trace,validate,group_records,find,reconstruct,scalar,ZERO_LD


def array(rs,stage,name,last=False):
    r=find(rs,stage,name,last,array=True)
    return reconstruct(r) if r else np.array([])


def db(values):
    values=np.asarray(values,dtype=float)
    with np.errstate(divide='ignore',invalid='ignore'):
        return 10*np.log10(np.where(values>0,values,np.nan))


def curve(ax,values,label,**kwargs):
    ax.plot(np.arange(len(values)),values,label=label,**kwargs)
    ax.set_xlabel('SFB index');ax.grid(alpha=.25)
    if not np.isfinite(values).any():
        ax.text(.5,.5,'Not observed / no valid nonzero values',transform=ax.transAxes,ha='center',fontsize=9)


def plot(trace: Path,output_dir: Path,frame: int|None,channel: int) -> dict:
    records=load_trace(trace);report=validate(records);groups=group_records(records)
    available=[r for r in report['frames'] if r['channel']==channel]
    if not available:raise ValueError('Requested plot channel not present')
    if frame is None:
        frame=max(available,key=lambda r:float(np.nansum(array(groups[r['frame'],channel],'input','energy'))))['frame']
    if (frame,channel) not in groups:raise ValueError('Requested plot frame/channel not present')
    rs=groups[frame,channel];summary=next(r for r in available if r['frame']==frame)
    directory=Path(output_dir);directory.mkdir(parents=True,exist_ok=True);paths=[]
    title=f"Native FDK AAC-LC | frame {frame}, channel {channel}, {summary['block']} | MDCT exponent {summary['mdct_scale']}"
    def save(name,fig):
        fig.suptitle(title,fontsize=11);fig.tight_layout(rect=(0,0,1,.95));fig.savefig(directory/name,dpi=160);plt.close(fig);paths.append(name)
    def single(name,y,label,ylabel):
        fig,ax=plt.subplots(figsize=(10,4));curve(ax,y,label);ax.set_ylabel(ylabel);ax.legend();save(name,fig)
    ff=array(rs,'form_factor','ld')
    single('01_form_factor.png',ff,'Native Form Factor (LD restored)','Sum sqrt(|MDCT|), FDK PCM domain')
    pe0=array(rs,'pe','initial.sfb_pe');pe1=array(rs,'pe','computed.sfb_pe',True)
    fig,ax=plt.subplots(figsize=(10,4));curve(ax,pe0,'Before adjustment');curve(ax,pe1,'Last native calculation');ax.set_ylabel('Per-SFB PE (raw / 2^16)');ax.legend();save('02_pe_per_sfb.png',fig)
    times=np.array([r['frame'] for r in available]);before=np.array([r['initial_pe'] for r in available],float);after=np.array([r['adjusted_pe'] for r in available],float)
    fig,ax=plt.subplots(figsize=(10,4));ax.plot(times,before,label='Initial native channel PE');ax.plot(times,after,label='Adjusted native channel PE');ax.set(xlabel='Native frame index (includes priming/flush)',ylabel='Channel PE (integer total)');ax.grid(alpha=.25);ax.legend();save('02_pe_per_frame.png',fig)
    target=np.array([r['target_dynamic_bits'] for r in available],float);actual=np.array([r['element_dynamic_bits'] for r in available],float)
    fig,ax=plt.subplots(figsize=(10,4));ax.plot(times,target,label='Granted element dynamic bits');ax.plot(times,actual,label='Actual element dynamic bits');ax.set(xlabel='Native frame index',ylabel='Bits (shared element budget for stereo)');ax.grid(alpha=.25);ax.legend();save('03_target_vs_actual_bits.png',fig)
    fig,ax=plt.subplots(figsize=(10,4));ax.plot(times,[r['reservoir'] for r in available],label='After native commit');ax.set(xlabel='Native frame index',ylabel='Bit reservoir [bits]');ax.grid(alpha=.25);ax.legend();save('03_bit_reservoir.png',fig)
    threshold0=array(rs,'input','threshold_ld');threshold1=array(rs,'threshold','after.threshold_ld');energy=array(rs,'input','energy')
    fig,ax=plt.subplots(figsize=(10,4));curve(ax,db(energy),'Band energy');curve(ax,db(threshold0),'Original Psy threshold');curve(ax,db(threshold1),'Adjusted threshold (unweighted)');ax.set_ylabel('10 log10(value), ref = 1 normalized PCM²');ax.legend();save('04_threshold_before_after.png',fig)
    fig,ax=plt.subplots(figsize=(7,4));vals=[summary['initial_pe'],summary['adjusted_pe']];ax.bar(['Initial','Adjusted'],np.array(vals,float));ax.set_ylabel('Native channel PE');ax.grid(axis='y',alpha=.25);save('04_pe_before_after.png',fig)
    sf=array(rs,'final','scf_relative');gain=summary['global_gain'];absolute=array(rs,'scalefactor','optimized.absolute')
    absolute=np.where(absolute==ZERO_LD,np.nan,absolute)
    seeds=np.full(len(sf),np.nan)
    for r in rs:
        if r['stage']=='scalefactor' and r['name']=='seed.absolute':seeds[r['index']]=r['raw'][0]
    fig,axes=plt.subplots(2,1,figsize=(10,6));curve(axes[0],seeds,'Initial absolute gain');curve(axes[0],absolute,'Optimized absolute gain');axes[0].set_ylabel('Absolute band scale (integer)');axes[0].legend()
    curve(axes[1],sf,'Final relative scf');curve(axes[1],gain-sf,'Final QSS = G - scf');axes[1].set_ylabel('Integer scale');axes[1].legend();save('05_scalefactor_before_after.png',fig)
    gain_events=[r for r in rs if r['stage']=='global_gain' and r['name'] in ('initial','rate','adjusted')]
    fig,ax=plt.subplots(figsize=(10,4));ax.step([r['sequence'] for r in gain_events],[r['raw'][0] for r in gain_events],where='post',marker='o');ax.set(xlabel='Native event sequence',ylabel='Internal globalGain (integer)');ax.grid(alpha=.25)
    if not gain_events:ax.text(.5,.5,'Global-gain stage not selected',transform=ax.transAxes,ha='center')
    save('06_global_gain_iterations.png',fig)
    rate=[];current=None
    for r in rs:
        if r['stage']=='global_gain' and r['name']=='rate' or r['stage']=='iterations' and r['name']=='rate.global_gain':current=r['raw'][0]
        if r['stage']=='iterations' and r['name']=='rate.bits' and current is not None:rate.append((r['sequence'],current,r['raw'][0]))
    fig,ax=plt.subplots(figsize=(8,4));ax.plot([r[1] for r in rate],[r[2] for r in rate],'-o')
    if not rate:ax.scatter([gain],[summary['channel_dynamic_bits']]);ax.text(.05,.9,'Final result only; no rate iteration log',transform=ax.transAxes)
    ax.set(xlabel='Internal globalGain',ylabel='Actual native channel dynamic bits');ax.grid(alpha=.25);save('06_global_gain_vs_bits.png',fig)
    psy=array(rs,'input','spectrum');x=array(rs,'final','spectrum_before_quant');iq=array(rs,'final','reconstructed_spectrum');q=array(rs,'final','quantized_spectrum')
    fig,ax=plt.subplots(figsize=(11,4));ax.plot(psy,label='Psy input');ax.plot(x,label='After QC zeroing',alpha=.8);ax.plot(iq,label='Native inverse quantizer, exponent +1',alpha=.7);ax.set(xlabel='Grouped MDCT coefficient index',ylabel='FDK normalized PCM/MDCT domain');ax.grid(alpha=.25);ax.legend();save('07_before_after_quantization.png',fig)
    fig,ax=plt.subplots(figsize=(11,4));ax.plot(q,'.',markersize=3);ax.set(xlabel='Grouped coefficient index',ylabel='Quantized integer q (no Q31 scale)');ax.grid(alpha=.25);save('07_quantized_coefficients.png',fig)
    error=x-iq;original_error=psy-iq
    fig,axes=plt.subplots(2,1,figsize=(11,6));axes[0].plot(error,label='Post-QC input minus IQ');axes[0].plot(original_error,label='Psy input minus IQ (includes zeroing)',alpha=.6);axes[0].set_ylabel('Signed error, common FDK PCM scale');axes[0].legend();axes[1].plot(error**2);axes[1].set(xlabel='Grouped coefficient index',ylabel='Squared display error [normalized PCM²]');save('07_quantization_error.png',fig)
    fig,axes=plt.subplots(3,1,figsize=(11,8));thr=[r for r in rs if r['stage']=='threshold' and r['name'] in ('first_guess.pe','second_guess.pe')]
    axes[0].plot([r['sequence'] for r in thr],[r['raw'][0] for r in thr],'-o');axes[0].set_ylabel('Threshold-loop element PE')
    trials=[r for r in rs if r['stage']=='iterations' and r['name']=='trial.distortion_ld'];invalid={r['candidate'] for r in rs if r['name']=='trial.range_violation'}
    trials=[r for r in trials if r['candidate'] not in invalid]
    axes[1].plot([r['candidate'] for r in trials],[db(reconstruct(r))[0] for r in trials],'.',markersize=3);axes[1].set(xlabel='Native scalefactor candidate ID',ylabel='Native SFB distortion [dB, ref=1]')
    axes[2].plot([r[0] for r in rate],[r[2] for r in rate],'-o');axes[2].set(xlabel='Native event sequence',ylabel='Rate-loop channel bits')
    for ax,values in zip(axes,(thr,trials,rate)):
        ax.grid(alpha=.25)
        if not values:ax.text(.5,.5,'No native iteration observed / logging disabled',transform=ax.transAxes,ha='center',fontsize=9)
    save('08_iteration_trace.png',fig)
    fig,axes=plt.subplots(3,2,figsize=(13,11));axes=axes.ravel()
    axes[0].plot(psy,label='Psy spectrum');axes[0].plot(iq,label='Native IQ',alpha=.7);axes[0].set(xlabel='Coefficient',ylabel='Common PCM scale');axes[0].legend()
    curve(axes[1],db(energy),'Energy');curve(axes[1],db(threshold0),'Threshold before');curve(axes[1],db(threshold1),'Threshold after');axes[1].set_ylabel('dB, ref=1 normalized PCM²');axes[1].legend()
    curve(axes[2],pe0,'PE before');curve(axes[2],pe1,'PE last');axes[2].set_ylabel('Per-SFB PE');axes[2].legend()
    curve(axes[3],sf,'Relative scf');curve(axes[3],gain-sf,'QSS');axes[3].set_ylabel('Integer scale');axes[3].legend()
    axes[4].plot(times,target,label='Element grant');axes[4].plot(times,actual,label='Element actual');axes[4].set(xlabel='Frame',ylabel='Dynamic bits');axes[4].legend();axes[4].grid(alpha=.25)
    axes[5].plot(error);axes[5].set(xlabel='Coefficient',ylabel='Post-QC minus IQ');axes[5].grid(alpha=.25)
    save('quantization_overview.png',fig)
    result=dict(frame=frame,channel=channel,plots=paths,note='Native vectors; display-derived reconstruction/error. IQ is spectral reconstruction, not decoded audio including PNS/TNS.')
    (directory/'plot_manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trace',type=Path,default=Path('my_workspace/quantization_coding/output/quant/native_trace.jsonl'))
    p.add_argument('--output-dir',type=Path,default=Path('my_workspace/quantization_coding/plots/quant'));p.add_argument('--frame',type=int);p.add_argument('--channel',type=int,default=0)
    a=p.parse_args();result=plot(a.trace,a.output_dir,a.frame,a.channel);print(f"Created {len(result['plots'])} PNGs for frame {result['frame']}, channel {result['channel']}")


if __name__=='__main__':main()
