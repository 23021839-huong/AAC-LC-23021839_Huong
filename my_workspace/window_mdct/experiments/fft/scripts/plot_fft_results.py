"""Scientific plots; all values are read from measured CSV, not assumed."""
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

LABELS=["Original FFT\nFused Radix-4 + Radix-2","Radix-2 Only\nBinary butterflies in all stages"]
COLORS=["#3979b5","#db9441"]


def bars(ax,rows,field,unit,title,decimals=3,error=None):
    values=np.array([float(r[field]) for r in rows])
    errors=np.array([float(r[error]) for r in rows]) if error else None
    ax.bar(np.arange(2),values,color=COLORS,width=.56,yerr=errors,capsize=6)
    ax.set_xticks(np.arange(2),LABELS,fontsize=9)
    ax.set_ylabel(unit);ax.set_title(title,loc="left",fontsize=12,fontweight="bold",pad=12)
    ax.spines[["top","right"]].set_visible(False);ax.grid(axis="y",alpha=.2);ax.set_axisbelow(True)
    peak=max(values+errors if errors is not None else values)
    ax.set_ylim(min(0,float(min(values))*1.15),peak*1.22 if peak>0 else 1)
    for i,value in enumerate(values):
        ax.annotate(f"{value:,.{decimals}f}",(i,value+(errors[i] if errors is not None else 0)),
                    xytext=(0,7),textcoords="offset points",ha="center",fontsize=10)


def plot_results(csv_path,folder):
    with Path(csv_path).open() as f:rows=list(csv.DictReader(f))
    rows.sort(key=lambda r:r["experiment_id"])
    if len(rows)!=2 or any(r["status"]!="ok" for r in rows):raise ValueError("Need two successful measured experiments")
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11})
    panels=[("bitrate_comparison.png","actual_bitrate_kbps","ADTS bitrate (kb/s)","Actual bitrate over coded AAC duration",3,None),
            ("encoding_time_comparison.png","encoding_time_mean_ms","Encoding time (ms)","Encoder benchmark: profiling disabled, mean +/- sample SD",3,"encoding_time_std_ms"),
            ("file_size_comparison.png","aac_size_bytes","AAC ADTS file size (bytes)","Measured AAC file size",0,None),
            ("fft_kernel_time_comparison.png","fft_time_mean_ms","Total MDCT FFT time per file (ms)","FFT kernel time: separate profiling passes",3,"fft_time_std_ms")]
    for name,field,unit,title,decimals,error in panels:
        fig,ax=plt.subplots(figsize=(10.8,5.5),layout="constrained")
        bars(ax,rows,field,unit,title,decimals,error)
        if field=="actual_bitrate_kbps":
            ax.axhline(64,color="#bd3434",ls="--",lw=1.2,label="Target encoder bitrate: 64 kb/s");ax.legend(loc="lower right",fontsize=9)
        fig.savefig(folder/name,dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(16,5.2),layout="constrained")
    bars(axes[0],rows,"mse","MSE (full scale squared)","MSE: lower is better",6)
    bars(axes[1],rows,"snr_db","SNR (dB)","SNR: higher is better",3)
    bars(axes[2],rows,"distortion_rate_percent","NRMSE (%)","Distortion rate: lower is better",3)
    fig.suptitle("Full-file aligned waveform distortion; identical native decoder",fontsize=16,fontweight="bold")
    fig.savefig(folder/"distortion_comparison.png",dpi=180);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(17,10),layout="constrained")
    bars(axes[0,0],rows,"actual_bitrate_kbps","ADTS bitrate (kb/s)","Bitrate",3)
    axes[0,0].axhline(64,color="#bd3434",ls="--",label="Target64 kb/s");axes[0,0].legend(loc="lower right",fontsize=9)
    bars(axes[0,1],rows,"encoding_time_mean_ms","Encoding time (ms)","Encoder time: profiling OFF",3,"encoding_time_std_ms")
    bars(axes[0,2],rows,"fft_time_mean_ms","MDCT FFT total per file (ms)","FFT time: separate profile",3,"fft_time_std_ms")
    bars(axes[1,0],rows,"distortion_rate_percent","NRMSE (%)","Distortion rate",3)
    bars(axes[1,1],rows,"aac_size_bytes","AAC size (bytes)","File size",0)
    bars(axes[1,2],rows,"fft_fraction_of_profiled_encoder_percent","FFT / profiled encoder (%)","FFT share within profiling pass",2)
    fig.suptitle("FDK AAC-LC: Original FFT vs pure Radix-2",fontsize=20,fontweight="bold")
    fig.supxlabel(f"Same PCM / Sine Only / 64 kb/s / Release / {rows[0]['runs']} unprofiled benchmark runs per mode\n"
                  "FFT times come from separate profiling runs; they are not mixed into encoder benchmark timings.",fontsize=11)
    fig.savefig(folder/"fft_experiment_overview.png",dpi=180);plt.close(fig)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--csv",type=Path,default=Path('my_workspace/window_mdct/experiments/fft/results/fft_window_comparison.csv'))
    parser.add_argument("--output-dir",type=Path,default=Path('my_workspace/window_mdct/experiments/fft/plots'));args=parser.parse_args()
    plot_results(args.csv,args.output_dir)
