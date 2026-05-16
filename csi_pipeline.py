"""
ESP32-S3 CSI Pipeline — no hardcoded thresholds
================================================
Run this AFTER collecting data with csi_logger.py.
It shows you the stats, then you tell it what threshold to use.

USAGE:
  python csi_pipeline.py --file csi_data.csv
  python csi_pipeline.py --file csi_data.csv --threshold 150
  python csi_pipeline.py --file csi_data.csv --threshold 150 --save

INSTALL:
  pip install numpy pandas matplotlib scipy
"""

import argparse
import csv
import re
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.ndimage import gaussian_filter

# ── Pipeline settings ──────────────────────────────────────────────
N_BEST_SUBS  = 12   # NBVI: subcarriers to select
MOVING_WIN   = 10   # smoothing window
HAMPEL_WIN   = 3    # Hampel filter window
HAMPEL_SIGMA = 3.0  # Hampel outlier threshold
# ───────────────────────────────────────────────────────────────────


def load_csv(filepath):
    packets = []
    with open(filepath, "r", errors="ignore") as f:
        first = f.readline().strip()

    # Detect format
    has_header = "variance" in first or "csi_amplitudes" in first

    with open(filepath, "r", errors="ignore") as f:
        reader = csv.DictReader(f) if has_header else csv.reader(f)
        for row in reader:
            try:
                if has_header:
                    amps = list(map(float, row["csi_amplitudes"].split()))
                else:
                    m = re.search(r"\[([^\]]+)\]", ",".join(row))
                    if not m: continue
                    amps = list(map(float, m.group(1).split()))
                if len(amps) >= 4:
                    packets.append(amps[:128])
            except: pass

    max_len = max(len(p) for p in packets)
    mat = np.array([p + [0.0]*(max_len-len(p)) for p in packets])
    print(f"Loaded {len(packets)} packets x {mat.shape[1]} subcarriers")
    return mat


def hampel(s, w=3, sig=3.0):
    out = s.copy()
    for i in range(len(s)):
        lo, hi = max(0, i-w), min(len(s), i+w+1)
        win = s[lo:hi]
        med = np.median(win)
        mad = np.median(np.abs(win - med))
        if np.abs(s[i]-med) > sig*1.4826*mad:
            out[i] = med
    return out


def run_pipeline(mat_raw):
    # Stage 1 — strip null subcarriers
    valid = mat_raw.mean(axis=0) > 0.5
    mat1  = mat_raw[:, valid]

    # Stage 2 — Hampel filter
    mat2 = mat1.copy()
    for c in range(mat1.shape[1]):
        mat2[:, c] = hampel(mat1[:, c], HAMPEL_WIN, HAMPEL_SIGMA)

    # Stage 3 — baseline normalize (first 15 packets)
    baseline = mat2[:15].mean(axis=0)
    mat3 = mat2 - baseline

    # Stage 4 — NBVI subcarrier selection
    var_sub  = mat3.var(axis=0)
    mean_sub = np.abs(mat3.mean(axis=0)) + 1e-9
    nbvi     = var_sub / mean_sub
    sorted_idx = np.argsort(nbvi)[::-1]
    selected = []
    for idx in sorted_idx:
        if len(selected) >= N_BEST_SUBS: break
        if all(abs(idx-s) >= 2 for s in selected):
            selected.append(idx)
    best_idx = np.array(sorted(selected))
    mat4 = mat3[:, best_idx]

    # Stage 5 — moving variance
    spatial_var = mat4.var(axis=1)
    smoothed    = np.convolve(spatial_var, np.ones(MOVING_WIN)/MOVING_WIN, mode="same")

    return mat_raw, mat2, smoothed, best_idx, nbvi[valid]


def print_stats(smoothed):
    print("\n" + "="*50)
    print("  PIPELINE STATS — smoothed variance")
    print("="*50)
    print(f"  Min        : {smoothed.min():.2f}")
    print(f"  Max        : {smoothed.max():.2f}")
    print(f"  Mean       : {smoothed.mean():.2f}")
    print(f"  Std        : {smoothed.std():.2f}")
    print(f"  25th pct   : {np.percentile(smoothed, 25):.2f}")
    print(f"  50th pct   : {np.percentile(smoothed, 50):.2f}")
    print(f"  75th pct   : {np.percentile(smoothed, 75):.2f}")
    print(f"  90th pct   : {np.percentile(smoothed, 90):.2f}")
    print(f"  95th pct   : {np.percentile(smoothed, 95):.2f}")
    print(f"  99th pct   : {np.percentile(smoothed, 99):.2f}")
    print("="*50)
    print("\n  → Look at the distribution above.")
    print("  → Pick a threshold between the two clusters.")
    print("  → Re-run with: --threshold YOUR_VALUE\n")


def plot(mat_raw, mat2, smoothed, best_idx, nbvi, threshold, save, baseline_smoothed=None):
    plt.rcParams.update({"font.size": 9, "figure.dpi": 150})
    fig = plt.figure(figsize=(16, 11))

    title = "ESP32-S3 CSI Pipeline"
    if threshold:
        motion = smoothed > threshold
        n_motion = motion.sum()
        title += f" | Threshold={threshold} | Motion={n_motion}/{len(motion)} packets ({100*n_motion/len(motion):.0f}%)"
    fig.suptitle(title, fontsize=11, fontweight="bold")

    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.50, wspace=0.38,
                           left=0.07, right=0.97, top=0.93, bottom=0.07)

    pkts = np.arange(len(smoothed))

    # (a) Raw waterfall
    ax1 = fig.add_subplot(gs[0, :2])
    im1 = ax1.imshow(mat_raw, aspect="auto", cmap="plasma",
                     origin="lower", interpolation="nearest")
    fig.colorbar(im1, ax=ax1, label="Amplitude")
    ax1.set_title("(a) Raw CSI Waterfall")
    ax1.set_xlabel("Subcarrier"); ax1.set_ylabel("Packet #")

    # (b) NBVI scores
    ax2 = fig.add_subplot(gs[0, 2])
    colors = ["#e63946" if i in best_idx else "#457b9d" for i in range(len(nbvi))]
    ax2.bar(range(len(nbvi)), nbvi, color=colors, width=1.0)
    ax2.set_title(f"(b) NBVI Scores\n(red = top {N_BEST_SUBS})")
    ax2.set_xlabel("Subcarrier"); ax2.set_ylabel("NBVI")
    ax2.grid(True, alpha=0.3)

    # (c) After Hampel
    ax3 = fig.add_subplot(gs[1, :2])
    im3 = ax3.imshow(mat2, aspect="auto", cmap="plasma",
                     origin="lower", interpolation="nearest")
    fig.colorbar(im3, ax=ax3, label="Amplitude")
    ax3.set_title("(c) After Hampel Filter + Null Removal")
    ax3.set_xlabel("Active Subcarrier"); ax3.set_ylabel("Packet #")
    # (d) CDF plot
    ax4 = fig.add_subplot(gs[1, 2])
    if baseline_smoothed is not None:
        s1 = np.sort(baseline_smoothed)
        ax4.plot(s1, np.arange(1, len(s1)+1)/len(s1)*100,
                 color="#2a9d8f", linewidth=2, label="Still room")
        s2 = np.sort(smoothed)
        ax4.plot(s2, np.arange(1, len(s2)+1)/len(s2)*100,
                 color="#e76f51", linewidth=2, label="Motion")
        ax4.set_title("(d) CDF — Still vs Motion")
    else:
        sv = np.sort(smoothed)
        ax4.plot(sv, np.arange(1, len(sv)+1)/len(sv)*100,
                 color="#457b9d", linewidth=2, label="CDF")
        ax4.set_title("(d) CDF — Smoothed Variance")
    if threshold:
        pct = (smoothed <= threshold).mean() * 100
        ax4.axvline(threshold, color="#e63946", linewidth=2,
                    linestyle="--", label=f"Threshold={threshold:.0f} ({pct:.1f}%)")
        ax4.axhline(pct, color="#e63946", linewidth=0.8, linestyle=":", alpha=0.5)
    ax4.set_xlabel("Smoothed Variance")
    ax4.set_ylabel("Cumulative % of packets")
    ax4.set_ylim(0, 105)
    ax4.legend(fontsize=8)
    ax4.grid(True, alpha=0.3)

    # (e) Main motion plot
    ax5 = fig.add_subplot(gs[2, :])
    ax5.plot(pkts, smoothed, color="#1d3557", linewidth=1.2,
             label="Smoothed variance")

    if threshold:
        motion = smoothed > threshold
        ax5.axhline(threshold, color="#e63946", linewidth=1.8,
                    linestyle="--", label=f"Threshold = {threshold}")
        ax5.fill_between(pkts, threshold, smoothed,
                         where=motion, color="#e63946",
                         alpha=0.3, label="Motion")
        ax5.scatter(pkts[motion], smoothed[motion],
                    color="#e63946", s=8, zorder=5)
    else:
        ax5.set_title("(e) Smoothed Variance — set --threshold to classify")

    ax5.set_title("(e) Motion Detection Output")
    ax5.set_xlabel("Packet Index"); ax5.set_ylabel("Variance")
    ax5.legend(fontsize=8); ax5.grid(True, alpha=0.3)

    plt.tight_layout()

    if save:
        plt.savefig("csi_pipeline_output.png", dpi=300, bbox_inches="tight")
        plt.savefig("csi_pipeline_output.pdf", bbox_inches="tight")
        print("[✓] Saved: csi_pipeline_output.png")
        print("[✓] Saved: csi_pipeline_output.pdf")
    else:
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file",      required=True, help="CSV file from csi_logger.py")
    parser.add_argument("--threshold", type=float,    help="Motion threshold (optional)")
    parser.add_argument("--baseline",  type=str,     help="Still room CSV for CDF overlay (optional)")
    parser.add_argument("--save",      action="store_true", help="Save plots as PNG+PDF")
    args = parser.parse_args()

    mat_raw, mat2, smoothed, best_idx, nbvi = run_pipeline(load_csv(args.file))
    print_stats(smoothed)

    baseline_smoothed = None
    if args.baseline:
        print(f"Loading baseline: {args.baseline}")
        bmat, _, bsmoothed, _, _ = run_pipeline(load_csv(args.baseline))
        baseline_smoothed = bsmoothed

    plot(mat_raw, mat2, smoothed, best_idx, nbvi, args.threshold, args.save, baseline_smoothed)
