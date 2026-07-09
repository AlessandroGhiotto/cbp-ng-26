#!/usr/bin/env python3
import sys
import json
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

BEST_CONFIGS = {
    "8KB": "tage_simple_satL<8,20,64,4,16,64,2,4,0>",
    "16KB": "tage_simple_satL<9,12,64,4,16,64,3,4,0>",
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
    return traces

def main():
    tracedir = REPO_ROOT / "traces"
    traces = resolve_traces(tracedir)
    if not traces:
        print("Traces not found.")
        sys.exit(1)

    print("Running full evaluations for best Saturation-Bypass predictors...")
    print("=" * 80)

    final_results = {}

    for budget, expr in BEST_CONFIGS.items():
        size = get_predictor_size_bits(expr)
        print(f"Running: {expr} (size = {size} bits)")
        try:
            raw_results = run_predictor_on_multiple_traces(
                expr, traces, warmup=1000000, measure=40000000, jobs=16
            )
            
            # Print per-trace breakdown
            print(f"\nBreakdown for {expr}:")
            vfs_list = []
            mpki_list = []
            ipc_list = []
            for t_name in SELECTED_TRACES:
                # Find matching key in raw_results
                matched_key = None
                for k in raw_results.keys():
                    if k.startswith(t_name) or t_name.startswith(k):
                        matched_key = k
                        break
                
                if matched_key and raw_results[matched_key]:
                    m = raw_results[matched_key]
                    vfs_list.append(m["vfs"])
                    mpki_list.append(m["mpki"])
                    ipc_list.append(m["ipc"])
                    print(f"  {t_name:<30} | VFS = {m['vfs']:.4f} | MPKI = {m['mpki']:.4f} | IPC = {m['ipc']:.4f}")
                else:
                    vfs_list.append(0.0)
                    mpki_list.append(0.0)
                    ipc_list.append(0.0)
                    print(f"  {t_name:<30} | MISSING")
            
            avg_vfs = sum(vfs_list) / len(vfs_list)
            avg_mpki = sum(mpki_list) / len(mpki_list)
            avg_ipc = sum(ipc_list) / len(ipc_list)
            print(f"  -> MEAN: VFS = {avg_vfs:.4f} | MPKI = {avg_mpki:.4f} | IPC = {avg_ipc:.4f}")
            
            final_results[budget] = {
                "expr": expr,
                "size": size,
                "mean_vfs": avg_vfs,
                "mean_mpki": avg_mpki,
                "mean_ipc": avg_ipc,
                "traces": {t: v for t, v in zip(SELECTED_TRACES, vfs_list)}
            }
            print("-" * 80)
        except Exception as e:
            print(f"FAILED: {e}")

    # Write out final results
    with open(PROFILING_DIR / "outputs" / "sat_best_results.json", "w") as f:
        json.dump(final_results, f, indent=4)
        
    print("\nEvaluations complete.")

if __name__ == "__main__":
    main()
