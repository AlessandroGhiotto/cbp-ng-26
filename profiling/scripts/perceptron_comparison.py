#!/usr/bin/env python3
import sys
import argparse
import csv
from pathlib import Path

PROFILING_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PROFILING_DIR.parent
sys.path.append(str(PROFILING_DIR / "lib"))

from profiling_core import run_predictor_on_multiple_traces, get_predictor_size_bits

CONFIGS = {
    "8KB": [
        {"name": "perceptron_PC8_BHR31_W8", "expr": "perceptron_simple<8,31,8,73>"},
        {"name": "perceptron_PC7_BHR63_W8", "expr": "perceptron_simple<7,63,8,135>"},
        {"name": "perceptron_PC9_BHR15_W8", "expr": "perceptron_simple<9,15,8,42>"},
        {"name": "perceptron_PC8_BHR41_W6", "expr": "perceptron_simple<8,41,6,93>"},
        {"name": "perceptronL_PC6_BHR31_W8", "expr": "perceptron_simpleL<6,31,8,73,2>"},
        {"name": "perceptronL_PC7_BHR15_W8", "expr": "perceptron_simpleL<7,15,8,42,2>"}
    ],
    "16KB": [
        {"name": "perceptron_PC9_BHR31_W8", "expr": "perceptron_simple<9,31,8,73>"},
        {"name": "perceptron_PC8_BHR63_W8", "expr": "perceptron_simple<8,63,8,135>"},
        {"name": "perceptron_PC9_BHR47_W5", "expr": "perceptron_simple<9,47,5,105>"},
        {"name": "perceptron_PC9_BHR41_W6", "expr": "perceptron_simple<9,41,6,93>"},
        {"name": "perceptronL_PC7_BHR31_W8", "expr": "perceptron_simpleL<7,31,8,73,2>"},
        {"name": "perceptronL_PC8_BHR15_W8", "expr": "perceptron_simpleL<8,15,8,42,2>"}
    ]
}

def main():
    parser = argparse.ArgumentParser(description="Sweep Perceptron parameters under fixed budget")
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
    csv_path = outdir / "perceptron_comparison_results.csv"

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

    print(f"Running Perceptron sweep on traces: {[t.name for t in traces]}")
    results = []

    if not args.skip_sim:
        for budget in ["8KB", "16KB"]:
            print(f"\n--- Perceptron {budget} Sweeps ---")
            for cfg in CONFIGS[budget]:
                expr = cfg["expr"]
                size_bits = get_predictor_size_bits(expr)
                print(f"Running {cfg['name']} ({expr}) [Size: {size_bits} bits]...")
                try:
                    run_results = run_predictor_on_multiple_traces(expr, traces, args.warmup, args.measure, args.jobs)
                    for trace_name, metrics in run_results.items():
                        results.append({
                            "budget": budget,
                            "name": cfg["name"],
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

    # Print summary table
    print("\n" + "="*80)
    print(f"{'Budget':<8} | {'Predictor Name':<28} | {'Trace':<16} | {'MPKI':<8} | {'VFS Score':<10}")
    print("="*80)
    results.sort(key=lambda x: (x["budget"], x["name"], x["trace"]))
    for r in results:
        print(f"{r['budget']:<8} | {r['name']:<28} | {r['trace']:<16} | {float(r['mpki']):.4f} | {float(r['vfs']):.6f}")
    print("="*80)

if __name__ == "__main__":
    main()
