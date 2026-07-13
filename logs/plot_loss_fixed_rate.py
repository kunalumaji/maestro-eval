#!/usr/bin/env python3
"""Loss % at a FIXED 25% offered line-rate across memory loads.

Unlike the bisected 'Best results' rate (unstable near its pass/fail threshold)
and RX rate at a fixed rate (capped by the generator, not the DUT), loss % at a
fixed sub-saturation rate reflects how much each mode's memory-access pattern
struggles as the number of loads (M) grows, without the search-noise problem.
"""

from __future__ import annotations

import csv
import re
import statistics
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
MODES = ("gather", "simd")
SIZES = ("M1", "M2", "M4", "M6", "M8", "M10", "M12", "M14", "M16")
COLORS = {"gather": "#4477AA", "simd": "#228833"}
MARKERS = {"gather": "s", "simd": "^"}
LABELS = {"gather": "Software Gather", "simd": "SIMD"}
OFFSET = {"gather": -0.12, "simd": 0.12}

PROBE_RE = re.compile(
    r"Replaying at 25\.0% linerate.*?"
    r"TX\s+(?P<tx_mpps>[\d.]+) Mpps (?P<tx_gbps>[\d.]+) Gbps.*?"
    r"RX\s+(?P<rx_mpps>[\d.]+) Mpps (?P<rx_gbps>[\d.]+) Gbps.*?"
    r"loss\s+(?P<loss>-?[\d.]+)\s*%",
    re.DOTALL,
)


def load_runs(mode: str, size: str) -> list[float]:
    losses = []
    for i in range(1, 11):
        text = (HERE / mode / size / f"{mode}_{size}_H16_run{i}.log").read_text()
        losses.append(float(PROBE_RE.search(text).group("loss")))
    return losses


def write_csv(all_runs: dict[tuple[str, str], list[float]], out_path: Path) -> None:
    with out_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow((
            "Memory Load",
            "Gather Mean Loss % @25%LR",
            "SIMD Mean Loss % @25%LR",
            "Gather Median Loss % @25%LR",
            "SIMD Median Loss % @25%LR",
        ))
        for size in SIZES:
            g = all_runs[("gather", size)]
            s = all_runs[("simd", size)]
            writer.writerow((
                size,
                f"{statistics.mean(g):.4f}",
                f"{statistics.mean(s):.4f}",
                f"{statistics.median(g):.4f}",
                f"{statistics.median(s):.4f}",
            ))


def style_axis(ax: plt.Axes) -> None:
    ax.grid(axis="both", linestyle="--", linewidth=0.6, alpha=0.45)
    ax.spines[["top", "right"]].set_visible(False)


def plot_spread(all_runs: dict[tuple[str, str], list[float]], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    rng = np.random.default_rng(7)
    x = np.arange(len(SIZES))

    for mode in MODES:
        for i, size in enumerate(SIZES):
            values = np.array(all_runs[(mode, size)])
            jitter = rng.uniform(-0.04, 0.04, len(values))
            ax.scatter(x[i] + OFFSET[mode] + jitter, values, color=COLORS[mode],
                       marker=MARKERS[mode], s=26, alpha=0.55, edgecolor="none", zorder=2)
            median = statistics.median(values)
            lo, hi = values.min(), values.max()
            ax.errorbar(x[i] + OFFSET[mode], median, yerr=[[median - lo], [hi - median]],
                       fmt=MARKERS[mode], color=COLORS[mode], markersize=8,
                       markeredgecolor="black", markeredgewidth=0.6, capsize=4,
                       linewidth=1.4, zorder=3)

    for mode in MODES:
        medians = [statistics.median(all_runs[(mode, size)]) for size in SIZES]
        ax.plot(x + OFFSET[mode], medians, color=COLORS[mode], linewidth=1.6, alpha=0.8,
               linestyle="-", zorder=1, label=LABELS[mode])

    ax.set_xticks(list(x), SIZES)
    ax.set_xlabel("Memory load")
    ax.set_ylabel("Loss % at fixed 25% offered line-rate")
    ax.set_title("SIMD vs. Software Gather: loss at a fixed offered rate across memory loads")
    ax.legend(frameon=False)
    ax.text(0.01, 0.99, "Small dots: each of the 10 runs; marker+whisker: median with min-max range",
            transform=ax.transAxes, fontsize=8, color="#555555", va="top")
    style_axis(ax)
    fig.tight_layout()
    fig.savefig(out_path.with_suffix(".png"), dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(out_path.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    all_runs = {(mode, size): load_runs(mode, size) for mode in MODES for size in SIZES}
    write_csv(all_runs, HERE / "loss_fixed25pct_comparison.csv")
    plot_spread(all_runs, HERE / "loss_fixed25pct_spread")
    print(f"Wrote {HERE / 'loss_fixed25pct_comparison.csv'}")
    print(f"Wrote {HERE / 'loss_fixed25pct_spread.png'} and .pdf")


if __name__ == "__main__":
    main()
