#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

PROFILING_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PROFILING_DIR.parent
sys.path.append(str(PROFILING_DIR / "lib"))

from profiling_core import run_predictor_on_multiple_traces, get_predictor_size_bits

def main():
    parser = argparse.ArgumentParser(description="Sweep GAP predictor parameter trade-off (BHR vs PC bits)")
    parser.add_argument("--trace", default="gcc_test_trace.gz", help="Trace name in root or path")
    parser.add_argument("--warmup", type=int, default=1000000)
    parser.add_argument("--measure", type=int, default=10000000)
    args = parser.parse_args()

    # Find the trace path
    trace_path = REPO_ROOT / args.trace
    if not trace_path.exists():
        trace_path = REPO_ROOT / "traces" / args.trace
    if not trace_path.exists():
        print(f"Error: Trace {args.trace} not found.")
        sys.exit(1)

    print(f"Running GAP trade-off sweep on: {trace_path.name}")
    print(f"Budget: 8KB (15 index bits total)")
    print("=" * 60)
    print(f"{'GAP Configuration':<25} | {'BHR bits':<8} | {'PC bits':<7} | {'MPKI':<8} | {'IPC':<8} | {'VFS Score':<10}")
    print("=" * 60)

    # We sweep BHR_B from 15 (pure global history) to 0 (pure PC index)
    # keeping BHR_B + PC_B = 15.
    configs = [
        {"bhr": 15, "pc": 0, "expr": "gap<15,0,2>"},
        {"bhr": 13, "pc": 2, "expr": "gap<13,2,2>"},
        {"bhr": 11, "pc": 4, "expr": "gap<11,4,2>"},
        {"bhr": 9,  "pc": 6, "expr": "gap<9,6,2>"},
        {"bhr": 7,  "pc": 8, "expr": "gap<7,8,2>"},
        {"bhr": 5,  "pc": 10, "expr": "gap<5,10,2>"},
        {"bhr": 3,  "pc": 12, "expr": "gap<3,12,2>"},
        {"bhr": 1,  "pc": 14, "expr": "gap<1,14,2>"},
        {"bhr": 0,  "pc": 15, "expr": "gap<0,15,2>"},
    ]

    for cfg in configs:
        expr = cfg["expr"]
        try:
            results = run_predictor_on_multiple_traces(expr, [trace_path], args.warmup, args.measure, jobs=1)
            for t_name, metrics in results.items():
                print(f"{expr:<25} | {cfg['bhr']:<8} | {cfg['pc']:<7} | {metrics['mpki']:8.4f} | {metrics['ipc']:8.4f} | {metrics['vfs']:.6f}")
        except Exception as e:
            print(f"{expr:<25} | {cfg['bhr']:<8} | {cfg['pc']:<7} | FAILED: {e}")

if __name__ == "__main__":
    main()
