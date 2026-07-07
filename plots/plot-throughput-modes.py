#!/usr/bin/env python3
"""Parse replay logs and visualize Scalar, Gather, and SIMD performance."""

from __future__ import annotations

import argparse
import csv
import re
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


MODES = ("scalar", "software-gather", "simd")
LABELS = {"scalar": "Scalar", "software-gather": "Software Gather", "simd": "SIMD"}
COLORS = {"scalar": "#CC6677", "software-gather": "#4477AA", "simd": "#228833"}
MARKERS = {"scalar": "o", "software-gather": "s", "simd": "^"}

SWEEP_RE = re.compile(
    r"Replaying at\s+(?P<line_rate>[\d.]+)% linerate.*?"
    r"Replaing at\s+(?P<offered_mbps>\d+) Mbps.*?"
    r"TX\s+(?P<tx_mpps>[\d.]+) Mpps (?P<tx_gbps>[\d.]+) Gbps.*?"
    r"RX\s+(?P<rx_mpps>[\d.]+) Mpps (?P<rx_gbps>[\d.]+) Gbps.*?"
    r"loss\s+(?P<loss>-?[\d.]+)\s*%",
    re.DOTALL,
)
BEST_RE = re.compile(
    r"Best results:.*?TX:\s+(?P<tx_mpps>[\d.]+) Mpps (?P<tx_gbps>[\d.]+) Gbps.*?"
    r"RX:\s+(?P<rx_mpps>[\d.]+) Mpps (?P<rx_gbps>[\d.]+) Gbps.*?"
    r"loss:\s+(?P<loss>-?[\d.]+)\s*%",
    re.DOTALL,
)
FILE_RE = re.compile(r"(?P<mode>scalar|software-gather|simd)_run_(?P<run>\d+)$")


@dataclass(frozen=True)
class Point:
    mode: str
    run: int
    line_rate_pct: float
    offered_mbps: int
    tx_mpps: float
    tx_gbps: float
    rx_mpps: float
    rx_gbps: float
    loss_pct: float


@dataclass(frozen=True)
class Best:
    mode: str
    run: int
    tx_mpps: float
    tx_gbps: float
    rx_mpps: float
    rx_gbps: float
    loss_pct: float


def parse_results(results_dir: Path) -> tuple[list[Point], list[Best]]:
    points: list[Point] = []
    best: list[Best] = []
    for path in sorted(results_dir.iterdir()):
        file_match = FILE_RE.fullmatch(path.name)
        if not file_match or not path.is_file():
            continue
        mode, run = file_match.group("mode"), int(file_match.group("run"))
        text = path.read_text(errors="replace")
        if not text.strip():
            warnings.warn(f"Skipping empty result file: {path}")
            continue
        for match in SWEEP_RE.finditer(text):
            value = match.groupdict()
            points.append(Point(mode, run, float(value["line_rate"]), int(value["offered_mbps"]),
                                float(value["tx_mpps"]), float(value["tx_gbps"]),
                                float(value["rx_mpps"]), float(value["rx_gbps"]),
                                float(value["loss"])))
        match = BEST_RE.search(text)
        if match:
            value = match.groupdict()
            best.append(Best(mode, run, float(value["tx_mpps"]), float(value["tx_gbps"]),
                             float(value["rx_mpps"]), float(value["rx_gbps"]),
                             float(value["loss"])))
        else:
            warnings.warn(f"No 'Best results' block found in: {path}")
    if not points or not best:
        raise RuntimeError(f"No usable experiment data found in {results_dir}")
    return points, best


def write_csvs(out_dir: Path, points: list[Point], best: list[Best], threshold: float) -> None:
    with (out_dir / "all_measurements.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(Point.__dataclass_fields__)
        writer.writerows(tuple(vars(point).values()) for point in points)

    with (out_dir / "best_results.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(Best.__dataclass_fields__)
        writer.writerows(tuple(vars(point).values()) for point in best)

    with (out_dir / "summary.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("mode", "valid_runs", "mean_rx_gbps", "std_rx_gbps", "ci95_rx_gbps",
                         "mean_loss_pct", "min_loss_pct", "max_observed_rx_gbps_under_threshold"))
        for mode in MODES:
            selected = [row for row in best if row.mode == mode]
            valid_sweep = [row for row in points if row.mode == mode and 0 <= row.loss_pct <= threshold]
            rx = np.array([row.rx_gbps for row in selected])
            loss = np.array([row.loss_pct for row in selected])
            ci95 = 1.96 * rx.std(ddof=1) / np.sqrt(len(rx)) if len(rx) > 1 else 0.0
            writer.writerow((LABELS[mode], len(rx), rx.mean(), rx.std(ddof=1), ci95, loss.mean(),
                             min((row.loss_pct for row in points if row.mode == mode and row.loss_pct >= 0),
                                 default=np.nan),
                             max((row.rx_gbps for row in valid_sweep), default=np.nan)))


def style_axis(ax: plt.Axes) -> None:
    ax.grid(axis="both", linestyle="--", linewidth=0.6, alpha=0.45)
    ax.spines[["top", "right"]].set_visible(False)


def plot_sustainable_throughput(out_dir: Path, best: list[Best]) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    rng = np.random.default_rng(7)
    for index, mode in enumerate(MODES):
        rows = [row for row in best if row.mode == mode]
        values = np.array([row.rx_gbps for row in rows])
        jitter = rng.uniform(-0.08, 0.08, len(values))
        ax.scatter(index + jitter, values, color=COLORS[mode], marker=MARKERS[mode],
                   s=42, alpha=0.75, edgecolor="white", linewidth=0.5, zorder=3)
        ci95 = 1.96 * values.std(ddof=1) / np.sqrt(len(values)) if len(values) > 1 else 0
        ax.errorbar(index, values.mean(), yerr=ci95, fmt="D", color="black", capsize=5,
                    markersize=6, linewidth=1.5, zorder=4)
        ax.annotate(f"{values.mean():.2f}", (index, values.mean()), xytext=(9, 0),
                    textcoords="offset points", va="center", fontsize=9)
    ax.set_xticks(range(len(MODES)), [LABELS[mode] for mode in MODES])
    ax.set_ylabel("Selected RX throughput (Gbps)")
    ax.set_title("Sustainable throughput across experiment runs")
    ax.text(0.01, 0.01, "Dots: runs; diamond/error bar: mean and 95% CI",
            transform=ax.transAxes, fontsize=8, color="#555555")
    style_axis(ax)
    save_figure(fig, out_dir / "01-sustainable-throughput")


def plot_loss_curve(out_dir: Path, points: list[Point], threshold: float) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for mode in MODES:
        rows = [row for row in points if row.mode == mode and row.loss_pct >= 0]
        ax.scatter([row.offered_mbps / 1000 for row in rows], [row.loss_pct for row in rows],
                   color=COLORS[mode], marker=MARKERS[mode], s=18, alpha=0.16)
        grouped: dict[int, list[float]] = defaultdict(list)
        for row in rows:
            grouped[row.offered_mbps].append(row.loss_pct)
        x = np.array(sorted(grouped))
        median = np.array([np.median(grouped[value]) for value in x])
        ax.plot(x / 1000, median, color=COLORS[mode], marker=MARKERS[mode], markersize=4,
                linewidth=1.8, label=LABELS[mode])
    ax.axhline(threshold, color="#AA3377", linestyle="--", linewidth=1.5,
               label=f"Loss threshold ({threshold:g}%)")
    ax.set_xlabel("Configured offered line rate (Gbps)")
    ax.set_ylabel("Packet loss (%)")
    ax.set_yscale("symlog", linthresh=0.1)
    ax.set_ylim(bottom=0)
    ax.set_title("Packet loss versus configured line rate")
    ax.legend(frameon=False)
    style_axis(ax)
    save_figure(fig, out_dir / "02-loss-vs-line-rate")


def plot_tradeoff(out_dir: Path, points: list[Point], threshold: float) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for mode in MODES:
        rows = [row for row in points if row.mode == mode and row.loss_pct >= 0]
        ax.scatter([row.rx_gbps for row in rows], [row.loss_pct for row in rows],
                   color=COLORS[mode], marker=MARKERS[mode], s=28, alpha=0.42,
                   edgecolor="none", label=LABELS[mode])
        passing = [row for row in rows if row.loss_pct <= threshold]
        if passing:
            fastest = max(passing, key=lambda row: row.rx_gbps)
            ax.scatter(fastest.rx_gbps, fastest.loss_pct, facecolor=COLORS[mode],
                       edgecolor="black", marker=MARKERS[mode], s=95, linewidth=1.0, zorder=4)
            ax.annotate(f"{fastest.rx_gbps:.2f} Gbps\n{fastest.loss_pct:.2f}%",
                        (fastest.rx_gbps, fastest.loss_pct), xytext=(7, 7),
                        textcoords="offset points", fontsize=8)
    ax.axhline(threshold, color="#AA3377", linestyle="--", linewidth=1.5,
               label=f"Loss threshold ({threshold:g}%)")
    ax.set_xlabel("Received throughput (Gbps)")
    ax.set_ylabel("Packet loss (%)")
    ax.set_yscale("symlog", linthresh=0.1)
    ax.set_ylim(bottom=0)
    ax.set_title("Throughput–loss trade-off")
    ax.legend(frameon=False)
    style_axis(ax)
    save_figure(fig, out_dir / "03-throughput-loss-tradeoff")


def save_figure(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path.with_suffix(".png"), dpi=200, bbox_inches="tight",
                facecolor="white", transparent=False)
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight",
                facecolor="white", transparent=False)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path(__file__).parents[1] / "results")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).parent / "out" / "throughput-modes")
    parser.add_argument("--loss-threshold", type=float, default=0.4, help="Maximum acceptable loss in percent")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    points, best = parse_results(args.results_dir)
    write_csvs(args.out_dir, points, best, args.loss_threshold)
    plot_sustainable_throughput(args.out_dir, best)
    plot_loss_curve(args.out_dir, points, args.loss_threshold)
    plot_tradeoff(args.out_dir, points, args.loss_threshold)
    print(f"Parsed {len(points)} measurements and {len(best)} valid runs")
    print(f"Wrote plots and CSV data to {args.out_dir}")


if __name__ == "__main__":
    main()
