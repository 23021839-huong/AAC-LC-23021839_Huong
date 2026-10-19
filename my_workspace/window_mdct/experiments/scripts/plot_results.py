"""Static scientific comparisons of measured window experiments."""
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

COLORS = ["#3979b5", "#db9441", "#7b65ad", "#269382"]
LABELS = ["EXP01\nSine only", "EXP02\nKBD only", "EXP03\nSine long /\nKBD short", "EXP04\nKBD long /\nSine short"]


def bars(ax, rows, field, ylabel, title, decimals=3, errors=None):
    values = np.array([float(row[field]) for row in rows])
    x = np.arange(4)
    ax.bar(x, values, color=COLORS, width=0.61, yerr=errors, capsize=5,
           error_kw={"elinewidth": 1.3, "capthick": 1.3})
    ax.set_xticks(x, LABELS, fontsize=9)
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=15)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=0.18)
    top = max(values + errors if errors is not None else values)
    bottom = min(0, min(values))
    ax.set_ylim(bottom * 1.15 if bottom else 0, top * 1.23 if top > 0 else 1)
    for i, value in enumerate(values):
        offset = errors[i] if errors is not None else 0
        ax.annotate(f"{value:,.{decimals}f}", (i, value + offset), xytext=(0, 6),
                    textcoords="offset points", ha="center", fontsize=10)


def plot_results(csv_path, output_dir):
    csv_path, output_dir = Path(csv_path), Path(output_dir)
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 4 or any(row["status"] != "ok" for row in rows):
        raise ValueError("Plots require all four successful measured results")
    rows.sort(key=lambda row: row["experiment_id"])
    if [r["experiment_id"] for r in rows] != ["EXP01", "EXP02", "EXP03", "EXP04"]:
        raise ValueError("Comparison requires EXP01..EXP04")
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "figure.facecolor": "white"})
    errors = np.array([float(row["encoding_time_std_ms"]) for row in rows])
    panels = [("01_bitrate_comparison.png", "actual_bitrate_kbps", "ADTS bitrate (kb/s)", "Actual bitrate over coded AAC duration", 3, None),
              ("02_encoding_time_comparison.png", "encoding_time_mean_ms", "Encoding time (ms)", "Native encoding time: mean +/- sample SD", 3, errors),
              ("04_aac_file_size_comparison.png", "aac_size_bytes", "AAC ADTS file size (bytes)", "Measured AAC file size", 0, None)]
    for filename, field, unit, title, decimals, err in panels:
        fig, ax = plt.subplots(figsize=(11.5, 5.4), layout="constrained")
        bars(ax, rows, field, unit, title, decimals, err)
        if field == "actual_bitrate_kbps":
            ax.axhline(64, color="#bd3434", linestyle="--", linewidth=1.3, label="Target encoder bitrate: 64 kb/s")
            ax.legend(loc="lower right", fontsize=9)
        fig.savefig(output_dir / filename, dpi=180)
        plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.2), layout="constrained")
    bars(axes[0], rows, "mse", "MSE (full scale squared)", "MSE: lower is better", 6)
    bars(axes[1], rows, "snr_db", "SNR (dB)", "SNR: higher is better", 3)
    bars(axes[2], rows, "nrmse_percent", "NRMSE (%)", "NRMSE: lower is better", 3)
    fig.suptitle("Sample-aligned full-file distortion; no gain correction", fontsize=16, fontweight="bold")
    fig.savefig(output_dir / "03_distortion_comparison.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), layout="constrained")
    bars(axes[0, 0], rows, "actual_bitrate_kbps", "ADTS bitrate (kb/s)", "Bitrate", 3)
    axes[0, 0].axhline(64, color="#bd3434", linestyle="--", linewidth=1.2, label="Target: 64 kb/s")
    axes[0, 0].legend(loc="lower right", fontsize=9)
    bars(axes[0, 1], rows, "encoding_time_mean_ms", "Encoding time (ms)", "Encoding time (mean +/- SD)", 3, errors)
    bars(axes[1, 0], rows, "nrmse_percent", "NRMSE (%)", "Distortion (lower is better)", 3)
    bars(axes[1, 1], rows, "aac_size_bytes", "AAC ADTS file size (bytes)", "File size", 0)
    fig.suptitle("FDK AAC-LC: measured Sine/KBD window comparison", fontsize=19, fontweight="bold")
    runs = int(rows[0]["runs"])
    fig.supxlabel(f"Same input / 64 kb/s / Release build / {runs} measured runs per mode + 1 warm-up\n"
                  "Mixed modes are AAC per-frame shape policies; transition left slopes retain previous shape.", fontsize=11)
    fig.savefig(output_dir / "window_experiment_overview.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=Path('my_workspace/window_mdct/experiments/results/window_comparison.csv'))
    parser.add_argument("--output-dir", type=Path, default=Path('my_workspace/window_mdct/experiments/results'))
    args = parser.parse_args()
    plot_results(args.csv, args.output_dir)
