#!/usr/bin/env python3
import sys
import csv
import json
import argparse
from pathlib import Path

PROFILING_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PROFILING_DIR.parent
sys.path.append(str(PROFILING_DIR / "lib"))

from profiling_core import run_predictor_on_multiple_traces, get_predictor_size_bits

# Define candidate configurations for the sweeps under fixed budgets
# We only sweep valid configurations that compile and fit the budget.
SWEEP_CANDIDATES = {
    "8KB": {
        "gap": [
            "gap<13,2,2>", "gap<11,4,2>", "gap<9,6,2>", "gap<7,8,2>",
            "gap<5,10,2>", "gap<3,12,2>", "gap<1,14,2>"
        ],
        "gapL": [
            "gapL<9,2,2,4>", "gapL<7,4,2,4>", "gapL<5,6,2,4>", "gapL<3,8,2,4>", "gapL<1,10,2,4>"
        ],
        "pag": [
            "pag<14,11,2>", "pag<15,2,2>"
        ],
        "pagL": [
            "pagL<10,11,2,4>", "pagL<11,2,2,4>"
        ],
        "pap": [
            "pap<8,6,7,2>", "pap<8,4,7,2>", "pap<8,12,6,2>", "pap<8,10,6,2>"
        ],
        "papL": [
            "papL<8,6,3,2,4>", "papL<8,4,3,2,4>", "papL<8,12,2,2,4>", "papL<8,10,2,2,4>"
        ],
        "gshare_simple": [
            "gshare_simple<15,15,2>", "gshare_simple<12,15,2>", "gshare_simple<9,15,2>", "gshare_simple<6,15,2>"
        ],
        "gshare_simpleL": [
            "gshare_simpleL<11,11,2,4>", "gshare_simpleL<8,11,2,4>", "gshare_simpleL<5,11,2,4>"
        ],
        "lxor": [
            "lxor<12,7>", "lxor<10,7>"
        ],
        "lxorL": [
            "lxorL<12,5,4>", "lxorL<10,5,4>", "lxorL<8,5,4>"
        ],
        "perceptron": [
            "perceptron_simple<8,31,8,83>", "perceptron_simple<7,63,8,83>",
            "perceptron_simple<9,15,8,83>", "perceptron_simple<10,7,8,83>"
        ],
        "perceptronL_LI4": [
            "perceptron_simpleL<6,31,8,83,2>", "perceptron_simpleL<7,15,8,83,2>",
            "perceptron_simpleL<8,7,8,83,2>"
        ],
        "perceptronL_LI16": [
            "perceptron_simpleL<5,15,8,83,4>", "perceptron_simpleL<6,7,8,83,4>",
            "perceptron_simpleL<7,3,8,83,4>"
        ],
        "tage_biasL": [
            "tage_biasL<8,8,64,4,16,64,3,4,6,true,0>", "tage_biasL<8,12,64,4,16,64,3,4,6,true,0>", "tage_biasL<8,16,64,4,16,64,3,4,6,true,0>"
        ],
        "tage_bimodeL": [
            "tage_bimodeL<7,8,64,4,16,64,3,4,6,true,8,8,8,false>", "tage_bimodeL<7,12,64,4,16,64,3,4,6,true,8,8,8,false>", "tage_bimodeL<7,16,64,4,16,64,3,4,6,true,8,8,8,false>"
        ]
    },
    "16KB": {
        "gap": [
            "gap<14,2,2>", "gap<12,4,2>", "gap<10,6,2>", "gap<8,8,2>",
            "gap<6,10,2>", "gap<4,12,2>", "gap<2,14,2>"
        ],
        "gapL": [
            "gapL<10,2,2,4>", "gapL<8,4,2,4>", "gapL<6,6,2,4>", "gapL<4,8,2,4>", "gapL<2,10,2,4>"
        ],
        "pag": [
            "pag<15,12,2>", "pag<16,2,2>"
        ],
        "pagL": [
            "pagL<11,12,2,4>", "pagL<12,2,2,4>"
        ],
        "pap": [
            "pap<8,4,8,2>", "pap<8,6,8,2>", "pap<8,12,7,2>", "pap<8,10,7,2>"
        ],
        "papL": [
            "papL<8,4,4,2,4>", "papL<8,6,4,2,4>", "papL<8,12,3,2,4>", "papL<8,10,3,2,4>"
        ],
        "gshare_simple": [
            "gshare_simple<16,16,2>", "gshare_simple<13,16,2>", "gshare_simple<10,16,2>", "gshare_simple<7,16,2>"
        ],
        "gshare_simpleL": [
            "gshare_simpleL<12,12,2,4>", "gshare_simpleL<9,12,2,4>", "gshare_simpleL<6,12,2,4>"
        ],
        "lxor": [
            "lxor<13,7>", "lxor<11,7>"
        ],
        "lxorL": [
            "lxorL<14,5,4>", "lxorL<12,5,4>", "lxorL<10,5,4>"
        ],
        "perceptron": [
            "perceptron_simple<9,31,8,83>", "perceptron_simple<8,63,8,83>",
            "perceptron_simple<10,15,8,83>", "perceptron_simple<11,7,8,83>"
        ],
        "perceptronL_LI4": [
            "perceptron_simpleL<7,31,8,83,2>", "perceptron_simpleL<8,15,8,83,2>",
            "perceptron_simpleL<9,7,8,83,2>"
        ],
        "perceptronL_LI16": [
            "perceptron_simpleL<6,15,8,83,4>", "perceptron_simpleL<7,7,8,83,4>",
            "perceptron_simpleL<8,3,8,83,4>"
        ],
        "tage_biasL": [
            "tage_biasL<9,8,64,4,16,64,3,4,6,true,0>", "tage_biasL<9,12,64,4,16,64,3,4,6,true,0>", "tage_biasL<9,16,64,4,16,64,3,4,6,true,0>"
        ],
        "tage_bimodeL": [
            "tage_bimodeL<8,8,64,4,16,64,3,4,6,true,9,9,8,false>", "tage_bimodeL<8,12,64,4,16,64,3,4,6,true,9,9,8,false>", "tage_bimodeL<8,16,64,4,16,64,3,4,6,true,9,9,8,false>"
        ]
    }
}

def main():
    parser = argparse.ArgumentParser(description="Sweep predictor parameters to find optimal VFS configs")
    parser.add_argument("--trace", default="gcc_test_trace.gz", help="Trace to use for optimization")
    parser.add_argument("--warmup", type=int, default=1000000)
    parser.add_argument("--measure", type=int, default=5000000)
    args = parser.parse_args()

    trace_path = REPO_ROOT / args.trace
    if not trace_path.exists():
        trace_path = REPO_ROOT / "traces" / args.trace
    if not trace_path.exists():
        print(f"Error: Trace {args.trace} not found.")
        sys.exit(1)

    print(f"Optimizing parameters on: {trace_path.name}")
    print("=" * 60)

    optimal_configs = {
        "8KB": {},
        "16KB": {}
    }

    for budget in ["8KB", "16KB"]:
        print(f"\n--- Optimizing {budget} configs ---")
        for pred_type, expr_list in SWEEP_CANDIDATES[budget].items():
            best_expr = None
            best_vfs = -1.0
            best_mpki = 999.0
            best_ipc = 0.0

            print(f"Sweeping {pred_type}...")
            for expr in expr_list:
                size_bits = get_predictor_size_bits(expr)
                try:
                    results = run_predictor_on_multiple_traces(expr, [trace_path], args.warmup, args.measure, jobs=1)
                    metrics = list(results.values())[0]
                    vfs = metrics["vfs"]
                    print(f"  {expr:<35} | size={size_bits:<6} | VFS={vfs:.6f} | MPKI={metrics['mpki']:.4f} | IPC={metrics['ipc']:.4f}")
                    if vfs > best_vfs:
                        best_vfs = vfs
                        best_expr = expr
                        best_mpki = metrics["mpki"]
                        best_ipc = metrics["ipc"]
                except Exception as e:
                    print(f"  {expr:<35} | size={size_bits:<6} | FAILED: {e}")

            if best_expr:
                print(f"🏆 Best {pred_type} for {budget}: {best_expr} (VFS={best_vfs:.6f}, MPKI={best_mpki:.4f}, IPC={best_ipc:.4f})")
                optimal_configs[budget][pred_type] = best_expr
            else:
                print(f"❌ Failed to find optimal config for {pred_type} ({budget})")

    # Save optimal configs to JSON
    json_path = PROFILING_DIR / "outputs" / "optimal_configs.json"
    with open(json_path, "w") as f:
        json.dump(optimal_configs, f, indent=4)
    print(f"\nSaved optimal configurations to: {json_path}")

if __name__ == "__main__":
    main()
