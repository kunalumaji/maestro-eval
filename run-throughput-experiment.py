#!/usr/bin/env python3
"""Run the stable-throughput replay experiment repeatedly."""

import argparse
import re
import subprocess
from pathlib import Path


RUNS = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the DPDK replay stable-throughput experiment 10 times."
    )
    parser.add_argument(
        "mode",
        help="Mode used in result filenames (for example, baseline or optimized)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.mode):
        raise SystemExit(
            "mode may contain only letters, numbers, underscores, periods, and hyphens"
        )

    repo_root = Path(__file__).resolve().parent
    python = repo_root / "build/env/bin/python"
    replay_script = repo_root / "util/replay-pcap-dpdk-replay.py"
    pcap = Path.home() / "trace-generator/uniform_udp_university_trace.pcap"
    results_dir = repo_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    command = [
        str(python),
        str(replay_script),
        "0000:03:00.1",
        "0000:03:00.1",
        str(pcap),
        "--find-stable-throughput",
        "--duration",
        "10",
        "--iterations",
        "10",
        "--start-rate",
        "25",
    ]

    for run_id in range(1, RUNS + 1):
        output_path = results_dir / f"{args.mode}_run_{run_id}"
        print(f"Run {run_id}/{RUNS}: writing output to {output_path}", flush=True)
        with output_path.open("w") as output:
            subprocess.run(command, cwd=repo_root, stdout=output, check=True)


if __name__ == "__main__":
    main()
