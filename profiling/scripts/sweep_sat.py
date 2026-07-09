#!/usr/bin/env python3
import sys
import json
import csv
import argparse
from pathlib import Path

PROFILING_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PROFILING_DIR.parent
sys.path.append(str(PROFILING_DIR / "lib"))

from profiling_core import run_predictor_on_multiple_traces, get_predictor_size_bits

SELECTED_TRACES = [
    "fp_28",
    "nodejs-misc-util_7039",
    "compress_44",
    "web_99",
    "web_13",
    "infra_32",
    "tomcat-wrk2-panel.3289_0",
    "int_48",
    "505-mcf-1_14364",
    "compress_47",
    "int_210",
    "java16-specjbb-4k.23837_0",
]

SWEEP_CANDIDATES = {
    "8KB": [
        "tage_simple_satL<8,12,64,4,16,64,3,4,0>",
        "tage_simple_satL<8,12,64,4,16,64,3,4,8>",
        "tage_simple_satL<8,16,64,4,16,64,3,4,0>",
        "tage_simple_satL<8,16,64,4,16,64,3,4,8>",
        "tage_simple_satL<8,20,64,4,16,64,2,4,0>",
        "tage_simple_satL<8,20,64,4,16,64,2,4,8>",
        "tage_simple_satL<8,30,64,4,16,64,2,4,0>",
        "tage_simple_satL<8,30,64,4,16,64,2,4,8>",
    ],
    "16KB": [
        "tage_simple_satL<9,12,64,4,16,64,3,4,0>",
        "tage_simple_satL<9,12,64,4,16,64,3,4,8>",
        "tage_simple_satL<9,16,64,4,16,64,3,4,0>",
        "tage_simple_satL<9,16,64,4,16,64,3,4,8>",
        "tage_simple_satL<9,20,64,4,16,64,2,4,0>",
        "tage_simple_satL<9,20,64,4,16,64,2,4,8>",
        "tage_simple_satL<9,30,64,4,16,64,2,4,0>",
        "tage_simple_satL<9,30,64,4,16,64,2,4,8>",
    ]
}

def resolve_traces(tracedir: Path) -> list[Path]:
    traces = []
    for name in SELECTED_TRACES:
        candidates = [
            tracedir / f"{name}_trace.gz",
        ]
        found = False
        for c in candidates:
            if c.exists():
                traces.append(c)
                found = True
                break
        if not found:
            root_trace = REPO_ROOT / f"{name}_trace.gz"
            if root_trace.exists():
                traces.append(root_trace)
            else:
                print(f"  WARNING: Trace '{name}' not found.")
    return traces

def main():
    parser = argparse.ArgumentParser(description="Sweep Saturation Bypass Predictor")
    parser.add_argument("--tracedir", default=str(REPO_ROOT / "traces"))
    parser.add_argument("--warmup", type=int, default=1000000)
    parser.add_argument("--measure", type=int, default=40000000)
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()

    tracedir = Path(args.tracedir).resolve()
    traces = resolve_traces(tracedir)

    if not traces:
        print("No traces found. Exiting.")
        sys.exit(1)

    print(f"Loaded {len(traces)} traces.")
    print("=" * 80)

    sweep_results = {"8KB": [], "16KB": []}

    for budget in ["8KB", "16KB"]:
        print(f"\n--- Sweeping {budget} Candidates ---")
        for expr in SWEEP_CANDIDATES[budget]:
            size = get_predictor_size_bits(expr)
            print(f"Running sweep for {expr} (size = {size} bits)...")
            try:
                raw_results = run_predictor_on_multiple_traces(
                    expr, traces, warmup=args.warmup, measure=args.measure, jobs=args.jobs
                )
                
                # Compute average metrics
                vfs_sum = 0.0
                mpki_sum = 0.0
                ipc_sum = 0.0
                count = 0
                for t_name, metrics in raw_results.items():
                    if metrics:
                        vfs_sum += metrics["vfs"]
                        mpki_sum += metrics["mpki"]
                        ipc_sum += metrics["ipc"]
                        count += 1
                
                if count > 0:
                    avg_vfs = vfs_sum / count
                    avg_mpki = mpki_sum / count
                    avg_ipc = ipc_sum / count
                    print(f"  -> Mean VFS = {avg_vfs:.4f} | MPKI = {avg_mpki:.4f} | IPC = {avg_ipc:.4f}")
                    sweep_results[budget].append({
                        "expr": expr,
                        "size": size,
                        "vfs": avg_vfs,
                        "mpki": avg_mpki,
                        "ipc": avg_ipc,
                        "raw": raw_results
                    })
            except Exception as e:
                print(f"  -> FAILED: {e}")

    # Write out sweep results
    out_path = PROFILING_DIR / "outputs" / "sat_sweep_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(sweep_results, f, indent=4)
    
    print("\n" + "=" * 80)
    print("Sweep Completed!")
    print(f"Results saved to {out_path}")
    print("=" * 80)

if __name__ == "__main__":
    main()
