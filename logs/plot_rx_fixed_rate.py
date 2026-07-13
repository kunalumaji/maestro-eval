#!/usr/bin/env python3
"""RX rate at a FIXED 25% offered line-rate (not the bisected 'best' rate),
to avoid the threshold-search noise seen in the 'Best results' metric."""

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

FIRST_PROBE_RE = re.compile(
    r"Replaying at 25\.0% linerate.*?"
    r"TX\s+(?P<tx_mpps>[\d.]+) Mpps (?P<tx_gbps>[\d.]+) Gbps.*?"
    r"RX\s+(?P<rx_mpps>[\d.]+) Mpps (?P<rx_gbps>[\d.]+) Gbps.*?"
    r"loss\s+(?P<loss>-?[\d.]+)\s*%",
    re.DOTALL,
)


def load_fixed_rate_runs(mode: str, size: str) -> list[dict]:
    runs = []
    for i in range(1, 11):
        path = HERE / mode / size / f"{mode}_{size}_H16_run{i}.log"
        text = path.read_text()
        match = FIRST_PROBE_RE.search(text)
        runs.append({k: float(v) for k, v in match.groupdict().items()})
    return runs


def write_csv(all_runs: dict[tuple[str, str], list[dict]], out_path: Path) -> None:
    with out_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Mode", "Memory Load", "Run", "TX Rate (Mpps)", "TX Gbps",
                         "RX Rate (Mpps)", "RX Gbps", "Loss %"))
        for mode in MODES:
            for size in SIZES:
                for i, run in enumerate(all_runs[(mode, size)], start=1):
                    writer.writerow((mode, size, i, f"{run['tx_mpps']:.4f}", f"{run['tx_gbps']:.4f}",
                                     f"{run['rx_mpps']:.4f}", f"{run['rx_gbps']:.4f}", f"{run['loss']:.4f}"))


def write_summary_csv(all_runs: dict[tuple[str, str], list[dict]], out_path: Path) -> None:
    with out_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Memory Load", "Gather Mean RX Rate (Mpps)", "SIMD Mean RX Rate (Mpps)",
                         "Gather Median RX Rate (Mpps)", "SIMD Median RX Rate (Mpps)"))
        for size in SIZES:
            g = [r["rx_mpps"] for r in all_runs[("gather", size)]]
            s = [r["rx_mpps"] for r in all_runs[("simd", size)]]
            writer.writerow((size, f"{statistics.mean(g):.4f}", f"{statistics.mean(s):.4f}",
                             f"{statistics.median(g):.4f}", f"{statistics.median(s):.4f}"))


def style_axis(ax: plt.Axes) -> None:
    ax.grid(axis="both", linestyle="--", linewidth=0.6, alpha=0.45)
    ax.spines[["top", "right"]].set_visible(False)


def plot_spread(all_runs: dict[tuple[str, str], list[dict]], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    rng = np.random.default_rng(7)
    x = np.arange(len(SIZES))

    for mode in MODES:
        for i, size in enumerate(SIZES):
            values = np.array([r["rx_mpps"] for r in all_runs[(mode, size)]])
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
        medians = [statistics.median([r["rx_mpps"] for r in all_runs[(mode, size)]]) for size in SIZES]
        ax.plot(x + OFFSET[mode], medians, color=COLORS[mode], linewidth=1.2, alpha=0.5,
               linestyle="--", zorder=1, label=LABELS[mode])

    ax.set_xticks(list(x), SIZES)
    ax.set_xlabel("Memory load")
    ax.set_ylabel("RX rate at fixed 25% offered line-rate (Mpps)")
    ax.set_title("SIMD vs. Software Gather: RX rate at a fixed offered rate across memory loads")
    ax.legend(frameon=False)
    ax.text(0.01, 0.99, "Small dots: each of the 10 runs; marker+whisker: median with min-max range",
            transform=ax.transAxes, fontsize=8, color="#555555", va="top")
    style_axis(ax)
    fig.tight_layout()
    fig.savefig(out_path.with_suffix(".png"), dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(out_path.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    all_runs = {(mode, size): load_fixed_rate_runs(mode, size) for mode in MODES for size in SIZES}

    write_csv(all_runs, HERE / "rx_rate_fixed25pct_all_runs.csv")
    write_summary_csv(all_runs, HERE / "rx_rate_fixed25pct_summary.csv")
    plot_spread(all_runs, HERE / "rx_rate_fixed25pct_spread")

    print(f"Wrote {HERE / 'rx_rate_fixed25pct_all_runs.csv'}")
    print(f"Wrote {HERE / 'rx_rate_fixed25pct_summary.csv'}")
    print(f"Wrote {HERE / 'rx_rate_fixed25pct_spread.png'} and .pdf\n")

    print(f"{'Size':<5} {'Mode':<8} {'Mean':>8} {'Median':>8} {'Min':>8} {'Max':>8} {'Spread':>8}")
    for mode in MODES:
        for size in SIZES:
            values = [r["rx_mpps"] for r in all_runs[(mode, size)]]
            print(f"{size:<5} {mode:<8} {statistics.mean(values):>8.4f} {statistics.median(values):>8.4f} "
                  f"{min(values):>8.4f} {max(values):>8.4f} {max(values) - min(values):>8.4f}")


if __name__ == "__main__":
    main()
