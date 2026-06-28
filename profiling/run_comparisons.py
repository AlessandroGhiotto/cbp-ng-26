#!/usr/bin/env python3
"""Wrapper script to run branch predictor benchmarks and automatically generate comparison plots."""

import argparse
import subprocess
import sys
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run CBP-NG benchmarks and plot the results.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # Forward trace path and options
    parser.add_argument(
        "trace_path",
        nargs="?",
        default="./gcc_test_trace.gz",
        help="Trace file or directory of *_trace.gz files",
    )
    parser.add_argument(
        "--outdir",
        default="comparison_results",
        help="Directory to store benchmark outputs and plots",
    )
    parser.add_argument(
        "--warmup", type=int, default=0, help="Warmup instructions per trace"
    )
    parser.add_argument(
        "--measure", type=int, default=1000, help="Measurement instructions per trace"
    )
    parser.add_argument(
        "--mode",
        choices=["default", "our", "all"],
        default="all",
        help="Which set of predictors to run ('default', 'our' (custom predictors), or 'all' (both))",
    )
    parser.add_argument(
        "--predictors",
        help="Comma-separated list of specific predictor names/labels to run (e.g., gag,gap)",
    )

    args = parser.parse_args()

    current_dir = Path(__file__).resolve().parent

    # Step 1: Run benchmark_predictors.py
    print("=" * 60)
    print(" STEP 1: Running branch predictor benchmarks...")
    print("=" * 60)
    
    benchmark_cmd = [
        sys.executable,
        str(current_dir / "benchmark_predictors.py"),
        args.trace_path,
        "--outdir", args.outdir,
        "--warmup", str(args.warmup),
        "--measure", str(args.measure),
        "--mode", args.mode,
    ]
    if args.predictors:
        benchmark_cmd.extend(["--predictors", args.predictors])

    try:
        subprocess.run(benchmark_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\nError: Benchmarking failed with exit code {e.returncode}", file=sys.stderr)
        return e.returncode

    # Step 2: Generate plots using plot_results.py
    print("\n" + "=" * 60)
    print(" STEP 2: Generating comparison plots...")
    print("=" * 60)
    
    csv_file = Path(args.outdir) / "comparison.csv"
    plot_file = Path(args.outdir) / "comparison_plots.png"
    
    plot_cmd = [
        sys.executable,
        str(current_dir / "plot_results.py"),
        "--csv", str(csv_file),
        "--output", str(plot_file)
    ]
    
    try:
        subprocess.run(plot_cmd, check=True)
        print(f"\nSuccess! Plots saved to {plot_file}")
    except subprocess.CalledProcessError as e:
        print(f"\nError: Plotting failed with exit code {e.returncode}", file=sys.stderr)
        return e.returncode

    print("\n" + "=" * 60)
    print(" Done! All benchmarks run and plots generated.")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
