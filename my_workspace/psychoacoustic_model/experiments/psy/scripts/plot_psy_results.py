"""Scientific figures from measured Psy CSV. Missing/unsupported cases stay missing."""
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def plot_results(csv_path,output):
    data=pd.read_csv(csv_path).set_index('experiment_id').reindex(['EXP01','EXP02','EXP03','EXP04'])
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    labels=['EXP01\nTone ON, TNS ON','EXP02\nTone ON, TNS OFF','EXP03\nTone OFF, TNS ON','EXP04\nTone OFF, TNS OFF']
    colors=['#2775ad','#e19b36','#7560a5','#288866']
    plt.rcParams.update({'font.size':10,'figure.facecolor':'white'})
    def draw(ax,field,title,unit,errors=False):
        values=pd.to_numeric(data[field],errors='coerce').to_numpy(dtype=float)
        valid=(data['status'].to_numpy()=='PASS') & np.isfinite(values)
        x=np.arange(4);err=pd.to_numeric(data['encoding_time_std_ms'],errors='coerce').to_numpy(dtype=float) if errors else None
        ax.bar(x[valid],values[valid],color=np.asarray(colors)[valid],width=.6,yerr=err[valid] if errors else None,capsize=5)
        ax.set(xticks=x,xticklabels=labels,ylabel=unit,title=title)
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.spines[['top','right']].set_visible(False)
        top=np.max(values[valid]+(err[valid] if errors else 0)) if valid.any() else 1
        ax.set_ylim(0,top*1.25 if top>0 else 1)
        for i in range(4):
            if valid[i]:ax.annotate(f'{values[i]:.3f}' if field!='aac_size_bytes' else f'{values[i]:.0f}',(i,values[i]+(err[i] if errors else 0)),xytext=(0,5),textcoords='offset points',ha='center')
            else:ax.text(i,top*.1,str(data.iloc[i]['status']),ha='center',rotation=90)
    specs=[('bitrate_comparison.png','actual_bitrate_kbps','Actual ADTS bitrate over coded duration','kb/s',False),
           ('encoding_time_comparison.png','encoding_time_mean_ms','Encoding only: mean and sample SD','ms',True),
           ('distortion_comparison.png','distortion_rate_percent','Aligned full-file NRMSE','%',False),
           ('filesize_comparison.png','aac_size_bytes','Measured AAC ADTS file size','bytes',False)]
    for name,field,title,unit,err in specs:
        fig,ax=plt.subplots(figsize=(11,5),layout='constrained');draw(ax,field,title,unit,err)
        if field=='actual_bitrate_kbps':ax.axhline(64,color='#ae3434',linestyle='--',label='Target64kb/s');ax.legend()
        fig.savefig(output/name,dpi=180);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(15,10),layout='constrained')
    for ax,(_,field,title,unit,err) in zip(axes.flat,specs):draw(ax,field,title,unit,err)
    fig.suptitle('FDK AAC-LC: native Tonality/TNS controlled experiment',fontsize=18)
    fig.supxlabel('Same WAV /64kb/s /original FFT and native window policy /PNS native configuration\nTonality ON executes the original estimator even if PNS disabled; quality effect requires a consumer.',fontsize=10)
    fig.savefig(output/'psy_overview.png',dpi=180);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--csv',type=Path,default=Path('my_workspace/psychoacoustic_model/experiments/psy/results/psy_comparison.csv'));p.add_argument('--output-dir',type=Path,default=Path('my_workspace/psychoacoustic_model/experiments/psy/plots'));a=p.parse_args();plot_results(a.csv,a.output_dir)
