#!/usr/bin/env python3
"""Combine gather/simd mean & median RX rate per memory load into one CSV and plot.

Mean plot: error bars show +/- 1 standard deviation across the 10 runs.
Median plot: error bars show the 25th-75th percentile (IQR) across the 10 runs.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).parent
SIZES = ("M1", "M2", "M4", "M6", "M8", "M10", "M12", "M14", "M16")
COLORS = {"gather": "#4477AA", "simd": "#228833"}
MARKERS = {"gather": "s", "simd": "^"}
LABELS = {"gather": "Software Gather", "simd": "SIMD"}
OFFSET = {"gather": -0.08, "simd": 0.08}


def load_rx_runs(mode: str) -> dict[str, list[float]]:
    runs = {}
    for size in SIZES:
        with (HERE / mode / f"{size}.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        runs[size] = [float(row["RX Rate"].split()[0]) for row in rows]
    return runs


def summarize(runs: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    stats = {}
    for size, values in runs.items():
        q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
        stats[size] = {
            "mean": statistics.mean(values),
            "std": statistics.stdev(values),
            "median": statistics.median(values),
            "q1": q1,
            "q3": q3,
        }
    return stats


def write_combined_csv(
    gather: dict[str, dict[str, float]], simd: dict[str, dict[str, float]], out_path: Path
) -> None:
    with out_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow((
            "Memory Load",
            "Gather Mean RX Rate (Mpps)", "Gather Std Dev (Mpps)",
            "SIMD Mean RX Rate (Mpps)", "SIMD Std Dev (Mpps)",
            "Gather Median RX Rate (Mpps)", "Gather Q1 (Mpps)", "Gather Q3 (Mpps)",
            "SIMD Median RX Rate (Mpps)", "SIMD Q1 (Mpps)", "SIMD Q3 (Mpps)",
        ))
        for size in SIZES:
            g, s = gather[size], simd[size]
            writer.writerow((
                size,
                f"{g['mean']:.4f}", f"{g['std']:.4f}",
                f"{s['mean']:.4f}", f"{s['std']:.4f}",
                f"{g['median']:.4f}", f"{g['q1']:.4f}", f"{g['q3']:.4f}",
                f"{s['median']:.4f}", f"{s['q1']:.4f}", f"{s['q3']:.4f}",
            ))


def style_axis(ax: plt.Axes) -> None:
    ax.grid(axis="both", linestyle="--", linewidth=0.6, alpha=0.45)
    ax.spines[["top", "right"]].set_visible(False)


def plot_mean_with_std(gather: dict, simd: dict, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    x = range(len(SIZES))
    for mode, data in (("gather", gather), ("simd", simd)):
        xs = [i + OFFSET[mode] for i in x]
        means = [data[size]["mean"] for size in SIZES]
        stds = [data[size]["std"] for size in SIZES]
        ax.errorbar(xs, means, yerr=stds, color=COLORS[mode], marker=MARKERS[mode],
                    markersize=7, linewidth=1.8, capsize=4, elinewidth=1.2, label=LABELS[mode])
    ax.set_xticks(list(x), SIZES)
    ax.set_xlabel("Memory load")
    ax.set_ylabel("Mean RX rate (Mpps)")
    ax.set_title("SIMD vs. Software Gather: mean RX rate across memory loads")
    ax.text(0.01, 0.01, "Error bars: +/- 1 standard deviation across 10 runs",
            transform=ax.transAxes, fontsize=8, color="#555555", va="bottom")
    ax.legend(frameon=False)
    style_axis(ax)
    fig.tight_layout()
    fig.savefig(out_path.with_suffix(".png"), dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(out_path.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_median_with_iqr(gather: dict, simd: dict, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    x = range(len(SIZES))
    for mode, data in (("gather", gather), ("simd", simd)):
        xs = [i + OFFSET[mode] for i in x]
        medians = [data[size]["median"] for size in SIZES]
        lo = [data[size]["median"] - data[size]["q1"] for size in SIZES]
        hi = [data[size]["q3"] - data[size]["median"] for size in SIZES]
        ax.errorbar(xs, medians, yerr=[lo, hi], color=COLORS[mode], marker=MARKERS[mode],
                    markersize=7, linewidth=1.8, capsize=4, elinewidth=1.2, label=LABELS[mode])
    ax.set_xticks(list(x), SIZES)
    ax.set_xlabel("Memory load")
    ax.set_ylabel("Median RX rate (Mpps)")
    ax.set_title("SIMD vs. Software Gather: median RX rate across memory loads")
    ax.text(0.01, 0.01, "Error bars: 25th-75th percentile (IQR) across 10 runs",
            transform=ax.transAxes, fontsize=8, color="#555555", va="bottom")
    ax.legend(frameon=False)
    style_axis(ax)
    fig.tight_layout()
    fig.savefig(out_path.with_suffix(".png"), dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(out_path.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    gather = summarize(load_rx_runs("gather"))
    simd = summarize(load_rx_runs("simd"))

    write_combined_csv(gather, simd, HERE / "rx_rate_comparison.csv")
    plot_mean_with_std(gather, simd, HERE / "rx_rate_comparison_mean")
    plot_median_with_iqr(gather, simd, HERE / "rx_rate_comparison_median")

    print(f"Wrote {HERE / 'rx_rate_comparison.csv'}")
    print(f"Wrote {HERE / 'rx_rate_comparison_mean.png'} and .pdf")
    print(f"Wrote {HERE / 'rx_rate_comparison_median.png'} and .pdf")


if __name__ == "__main__":
    main()
