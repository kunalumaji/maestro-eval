#!/usr/bin/env python3
"""Show per-run RX rate scatter (not just mean/median) to separate signal from noise."""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
SIZES = ("M1", "M2", "M4", "M6", "M8", "M10", "M12", "M14", "M16")
COLORS = {"gather": "#4477AA", "simd": "#228833"}
MARKERS = {"gather": "s", "simd": "^"}
LABELS = {"gather": "Software Gather", "simd": "SIMD"}
OFFSET = {"gather": -0.12, "simd": 0.12}


def load_runs(mode: str) -> dict[str, list[float]]:
    runs = {}
    for size in SIZES:
        with (HERE / mode / f"{size}.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        runs[size] = [float(row["RX Rate"].split()[0]) for row in rows]
    return runs


def style_axis(ax: plt.Axes) -> None:
    ax.grid(axis="both", linestyle="--", linewidth=0.6, alpha=0.45)
    ax.spines[["top", "right"]].set_visible(False)


def plot_spread(gather: dict[str, list[float]], simd: dict[str, list[float]], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    rng = np.random.default_rng(7)
    x = np.arange(len(SIZES))

    for mode, data in (("gather", gather), ("simd", simd)):
        for i, size in enumerate(SIZES):
            values = np.array(data[size])
            jitter = rng.uniform(-0.04, 0.04, len(values))
            ax.scatter(x[i] + OFFSET[mode] + jitter, values, color=COLORS[mode],
                       marker=MARKERS[mode], s=26, alpha=0.55, edgecolor="none", zorder=2)
            median = statistics.median(values)
            lo, hi = values.min(), values.max()
            ax.errorbar(x[i] + OFFSET[mode], median, yerr=[[median - lo], [hi - median]],
                       fmt=MARKERS[mode], color=COLORS[mode], markersize=8,
                       markeredgecolor="black", markeredgewidth=0.6, capsize=4,
                       linewidth=1.4, zorder=3)

    for mode, data in (("gather", gather), ("simd", simd)):
        medians = [statistics.median(data[size]) for size in SIZES]
        ax.plot(x + OFFSET[mode], medians, color=COLORS[mode], linewidth=1.2, alpha=0.5,
               linestyle="--", zorder=1, label=LABELS[mode])

    ax.set_xticks(list(x), SIZES)
    ax.set_xlabel("Memory load")
    ax.set_ylabel("RX rate (Mpps)")
    ax.set_title("SIMD vs. Software Gather: per-run spread of RX rate across memory loads")
    ax.legend(frameon=False)
    ax.text(0.01, 0.99, "Small dots: each of the 10 runs; marker+whisker: median with min-max range",
            transform=ax.transAxes, fontsize=8, color="#555555", va="top")
    style_axis(ax)
    fig.tight_layout()
    fig.savefig(out_path.with_suffix(".png"), dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(out_path.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def print_outlier_report(gather: dict[str, list[float]], simd: dict[str, list[float]]) -> None:
    print(f"{'Size':<5} {'Mode':<8} {'Mean':>8} {'Median':>8} {'Min':>8} {'Max':>8} {'Spread(Max-Min)':>16}")
    for mode, data in (("gather", gather), ("simd", simd)):
        for size in SIZES:
            values = data[size]
            mean = statistics.mean(values)
            median = statistics.median(values)
            print(f"{size:<5} {mode:<8} {mean:>8.4f} {median:>8.4f} {min(values):>8.4f} "
                  f"{max(values):>8.4f} {max(values) - min(values):>16.4f}")


def main() -> None:
    gather = load_runs("gather")
    simd = load_runs("simd")
    plot_spread(gather, simd, HERE / "rx_rate_spread")
    print(f"Wrote {HERE / 'rx_rate_spread.png'} and .pdf\n")
    print_outlier_report(gather, simd)


if __name__ == "__main__":
    main()
