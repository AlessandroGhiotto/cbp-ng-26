#!/usr/bin/env python3
import sys
import argparse
import csv
from pathlib import Path

PROFILING_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PROFILING_DIR.parent
sys.path.append(str(PROFILING_DIR / "lib"))

from profiling_core import run_predictor_on_multiple_traces, get_predictor_size_bits

# Matched budget configs for Scalar vs Block comparison
CONFIGS = {
    "8KB": [
        # GAg
        {"family": "GAg", "mode": "Scalar", "name": "gag", "expr": "gag<15,2>"},
        {"family": "GAg", "mode": "Block", "name": "gagL", "expr": "gagL<11,2,4>"},
        # GAp
        {"family": "GAp", "mode": "Scalar", "name": "gap", "expr": "gap<9,6,2>"},
        {"family": "GAp", "mode": "Block", "name": "gapL", "expr": "gapL<6,5,2,4>"},
        # PAg
        {"family": "PAg", "mode": "Scalar", "name": "pag", "expr": "pag<12,12,2>"},
        {"family": "PAg", "mode": "Block", "name": "pagL", "expr": "pagL<10,11,2,4>"},
        # PAp
        {"family": "PAp", "mode": "Scalar", "name": "pap", "expr": "pap<8,12,6,2>"},
        {"family": "PAp", "mode": "Block", "name": "papL", "expr": "papL<8,12,2,2,4>"},
        # BiMode
        {"family": "BiMode", "mode": "Scalar", "name": "bimode", "expr": "bimode<14,12,13,2>"},
        {"family": "BiMode", "mode": "Block", "name": "bimodeL", "expr": "bimodeL<10,10,9,2,4>"},
    ],
    "16KB": [
        # GAg
        {"family": "GAg", "mode": "Scalar", "name": "gag", "expr": "gag<16,2>"},
        {"family": "GAg", "mode": "Block", "name": "gagL", "expr": "gagL<12,2,4>"},
        # GAp
        {"family": "GAp", "mode": "Scalar", "name": "gap", "expr": "gap<10,6,2>"},
        {"family": "GAp", "mode": "Block", "name": "gapL", "expr": "gapL<6,6,2,4>"},
        # PAg
        {"family": "PAg", "mode": "Scalar", "name": "pag", "expr": "pag<15,12,2>"},
        {"family": "PAg", "mode": "Block", "name": "pagL", "expr": "pagL<11,12,2,4>"},
        # PAp
        {"family": "PAp", "mode": "Scalar", "name": "pap", "expr": "pap<8,13,7,2>"},
        {"family": "PAp", "mode": "Block", "name": "papL", "expr": "papL<8,13,3,2,4>"},
        # BiMode
        {"family": "BiMode", "mode": "Scalar", "name": "bimode", "expr": "bimode<15,14,14,2>"},
        {"family": "BiMode", "mode": "Block", "name": "bimodeL", "expr": "bimodeL<11,12,10,2,4>"},
    ]
}

def main():
    parser = argparse.ArgumentParser(description="Compare Scalar vs Block predictors per family")
    parser.add_argument("--tracedir", default=str(REPO_ROOT / "traces"), help="Directory containing traces")
    parser.add_argument("--outdir", default=str(PROFILING_DIR / "outputs"), help="Output directory")
    parser.add_argument("--warmup", type=int, default=1000000)
    parser.add_argument("--measure", type=int, default=10000000)
    parser.add_argument("--jobs", type=int, default=8, help="Parallel simulation jobs")
    parser.add_argument("--skip-sim", action="store_true", help="Skip simulation and use existing results")
    args = parser.parse_args()

    tracedir = Path(args.tracedir).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / "family_comparison_results.csv"

    # Select traces
    extremes_file = outdir / "selected_extreme_traces.txt"
    traces = []
    if extremes_file.exists():
        with open(extremes_file, "r") as f:
            extreme_names = [line.strip() for line in f if line.strip()]
        for name in extreme_names:
            gz_path = tracedir / f"{name}_trace.gz"
            if gz_path.exists():
                traces.append(gz_path)
    
    if not traces:
        traces = sorted(list(tracedir.glob("*_trace.gz")))

    if not traces:
        test_trace = REPO_ROOT / "gcc_test_trace.gz"
        if test_trace.exists():
            traces = [test_trace]
        else:
            print("Error: No traces found for simulation.")
            sys.exit(1)

    print(f"Running Family comparison on traces: {[t.name for t in traces]}")
    results = []

    if not args.skip_sim:
        for budget in ["8KB", "16KB"]:
            print(f"\n--- Family {budget} Comparisons ---")
            for cfg in CONFIGS[budget]:
                expr = cfg["expr"]
                size_bits = get_predictor_size_bits(expr)
                print(f"Running {cfg['family']} ({cfg['mode']}) -> {expr}...")
                try:
                    run_results = run_predictor_on_multiple_traces(expr, traces, args.warmup, args.measure, args.jobs)
                    for trace_name, metrics in run_results.items():
                        results.append({
                            "budget": budget,
                            "family": cfg["family"],
                            "mode": cfg["mode"],
                            "expr": expr,
                            "size_bits": size_bits,
                            "trace": trace_name,
                            **metrics
                        })
                except Exception as e:
                    print(f"Failed running {expr}: {e}")

        # Save to CSV
        with open(csv_path, "w", newline="") as f:
            if results:
                writer = csv.DictWriter(f, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)
        print(f"\nResults saved to {csv_path}")
    else:
        if not csv_path.exists():
            print(f"Error: CSV file not found: {csv_path}")
            sys.exit(1)
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            results = [dict(row) for row in reader]
        print(f"\nLoaded cached results from {csv_path}")

    # Print family summary
    print("\n" + "="*90)
    print(f"{'Budget':<8} | {'Family':<8} | {'Mode':<8} | {'Trace':<16} | {'MPKI':<8} | {'IPC':<8} | {'VFS Score':<10}")
    print("="*90)
    results.sort(key=lambda x: (x["budget"], x["family"], x["mode"], x["trace"]))
    for r in results:
        print(f"{r['budget']:<8} | {r['family']:<8} | {r['mode']:<8} | {r['trace']:<16} | {float(r['mpki']):.4f} | {float(r['ipc']):.4f} | {float(r['vfs']):.6f}")
    print("="*90)

if __name__ == "__main__":
    main()
