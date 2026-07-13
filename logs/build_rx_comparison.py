#!/usr/bin/env python3
"""Combine gather/simd mean & median RX rate per memory load into one CSV and plot."""

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


def load_mean_rx_mpps(mode: str) -> dict[str, float]:
    with (HERE / mode / f"{mode}_avg.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    return {row["Size"]: float(row["RX Rate"].split()[0]) for row in rows}


def load_median_rx_mpps(mode: str) -> dict[str, float]:
    medians = {}
    for size in SIZES:
        with (HERE / mode / f"{size}.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        medians[size] = statistics.median(float(row["RX Rate"].split()[0]) for row in rows)
    return medians


def write_combined_csv(
    mean_gather: dict[str, float],
    mean_simd: dict[str, float],
    median_gather: dict[str, float],
    median_simd: dict[str, float],
    out_path: Path,
) -> None:
    with out_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow((
            "Memory Load",
            "Gather Mean RX Rate (Mpps)",
            "SIMD Mean RX Rate (Mpps)",
            "Gather Median RX Rate (Mpps)",
            "SIMD Median RX Rate (Mpps)",
        ))
        for size in SIZES:
            writer.writerow((
                size,
                f"{mean_gather[size]:.4f}",
                f"{mean_simd[size]:.4f}",
                f"{median_gather[size]:.4f}",
                f"{median_simd[size]:.4f}",
            ))


def style_axis(ax: plt.Axes) -> None:
    ax.grid(axis="both", linestyle="--", linewidth=0.6, alpha=0.45)
    ax.spines[["top", "right"]].set_visible(False)


def plot_comparison(
    gather: dict[str, float], simd: dict[str, float], stat: str, out_path: Path
) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    x = range(len(SIZES))
    for mode, data in (("gather", gather), ("simd", simd)):
        y = [data[size] for size in SIZES]
        ax.plot(x, y, color=COLORS[mode], marker=MARKERS[mode], markersize=7,
                linewidth=1.8, label=LABELS[mode])
    ax.set_xticks(list(x), SIZES)
    ax.set_xlabel("Memory load")
    ax.set_ylabel(f"{stat} RX rate (Mpps)")
    ax.set_title(f"SIMD vs. Software Gather: {stat.lower()} RX rate across memory loads")
    ax.legend(frameon=False)
    style_axis(ax)
    fig.tight_layout()
    fig.savefig(out_path.with_suffix(".png"), dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(out_path.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    mean_gather = load_mean_rx_mpps("gather")
    mean_simd = load_mean_rx_mpps("simd")
    median_gather = load_median_rx_mpps("gather")
    median_simd = load_median_rx_mpps("simd")

    write_combined_csv(mean_gather, mean_simd, median_gather, median_simd,
                        HERE / "rx_rate_comparison.csv")
    plot_comparison(mean_gather, mean_simd, "Mean", HERE / "rx_rate_comparison_mean")
    plot_comparison(median_gather, median_simd, "Median", HERE / "rx_rate_comparison_median")

    print(f"Wrote {HERE / 'rx_rate_comparison.csv'}")
    print(f"Wrote {HERE / 'rx_rate_comparison_mean.png'} and .pdf")
    print(f"Wrote {HERE / 'rx_rate_comparison_median.png'} and .pdf")


if __name__ == "__main__":
    main()
