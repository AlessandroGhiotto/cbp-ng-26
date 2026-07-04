#!/usr/bin/env python3
import sys
import os
import argparse
import csv
import concurrent.futures
import shutil
from pathlib import Path

# Setup paths
PROFILING_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PROFILING_DIR.parent
sys.path.append(str(PROFILING_DIR / "lib"))

from profiling_core import run_cmd

TRACE_ANALYZER_BIN = Path(__file__).resolve().parent / "trace_analyzer"

def analyze_single_trace(trace_path: Path, warmup: int, measure: int) -> dict:
    trace_name = trace_path.stem
    if trace_name.endswith(".gz"):
        trace_name = Path(trace_name).stem
    if trace_name.endswith("_trace"):
        trace_name = trace_name[:-6]

    cmd = f"{TRACE_ANALYZER_BIN} {trace_path} {trace_name} {warmup} {measure}"
    stdout = run_cmd(cmd)
    
    parts = stdout.strip().split(",")
    if len(parts) < 13:
        raise ValueError(f"Unexpected output from trace_analyzer: {stdout}")
        
    return {
        "trace": parts[0],
        "instructions": int(parts[1]),
        "branches": int(parts[2]),
        "cond_branches": int(parts[3]),
        "cond_taken": int(parts[4]),
        "cond_backwards": int(parts[5]),
        "cond_backwards_taken": int(parts[6]),
        "uncond_direct": int(parts[7]),
        "uncond_indirect": int(parts[8]),
        "calls": int(parts[9]),
        "returns": int(parts[10]),
        "unique_cond_pcs": int(parts[11]),
        "unique_all_branch_pcs": int(parts[12])
    }

def main():
    parser = argparse.ArgumentParser(description="Analyze CBP-NG trace characteristics (EDA)")
    parser.add_argument("--tracedir", default=str(REPO_ROOT / "traces"), help="Directory containing traces")
    parser.add_argument("--outdir", default=str(PROFILING_DIR / "outputs"), help="Output directory")
    parser.add_argument("--warmup", type=int, default=1000000)
    parser.add_argument("--measure", type=int, default=40000000)
    parser.add_argument("--jobs", type=int, default=8, help="Number of parallel analyzer jobs")
    args = parser.parse_args()

    tracedir = Path(args.tracedir).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    # Compile trace analyzer if not exists
    if not TRACE_ANALYZER_BIN.exists():
        print("Compiling trace analyzer C++ tool...")
        try:
            run_cmd(f"apptainer exec /home/ghi/Documents/HPC-PoliMi/1-AMSC/amsc_mk_2025.sif g++ -std=c++20 -O3 -I. {PROFILING_DIR}/trace_analyzer.cpp -lz -o {TRACE_ANALYZER_BIN}")
        except Exception as e:
            # Fallback if SIF file not at that exact path
            print("Fallback compilation...")
            run_cmd(f"g++ -std=c++20 -O3 -I. {PROFILING_DIR}/trace_analyzer.cpp -lz -o {TRACE_ANALYZER_BIN}")

    # Find traces
    traces = sorted(list(tracedir.glob("*_trace.gz")))
    if not traces:
        # Check current dir or check if gcc_test_trace.gz exists in root
        test_trace = REPO_ROOT / "gcc_test_trace.gz"
        if test_trace.exists():
            print(f"No traces found in {tracedir}. Using test trace {test_trace} for sanity check.")
            traces = [test_trace]
        else:
            print(f"Error: No traces found in {tracedir} and gcc_test_trace.gz not found.")
            sys.exit(1)

    print(f"Analyzing {len(traces)} traces...")
    raw_results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {executor.submit(analyze_single_trace, t, args.warmup, args.measure): t for t in traces}
        for future in concurrent.futures.as_completed(futures):
            t = futures[future]
            try:
                metrics = future.result()
                raw_results.append(metrics)
                print(f"  Analyzed {metrics['trace']}")
            except Exception as e:
                print(f"  Failed analyzing {t.name}: {e}")

    if not raw_results:
        print("No traces successfully analyzed.")
        sys.exit(1)

    # Sort results by name
    raw_results.sort(key=lambda x: x["trace"])

    # Compute features for each trace
    features = []
    for r in raw_results:
        inst = r["instructions"]
        br = r["branches"]
        cond = r["cond_branches"]
        
        # Avoid division by zero
        br_density = br / inst if inst > 0 else 0
        cond_density = cond / inst if inst > 0 else 0
        cond_taken_rate = r["cond_taken"] / cond if cond > 0 else 0
        backward_rate = r["cond_backwards"] / cond if cond > 0 else 0
        backward_taken_rate = r["cond_backwards_taken"] / r["cond_backwards"] if r["cond_backwards"] > 0 else 0
        uncond_rate = (br - cond) / br if br > 0 else 0
        indirect_rate = r["uncond_indirect"] / br if br > 0 else 0
        calls_rate = r["calls"] / br if br > 0 else 0
        returns_rate = r["returns"] / br if br > 0 else 0
        unique_cond_pcs = r["unique_cond_pcs"]
        
        features.append({
            "trace": r["trace"],
            "instructions": inst,
            "branches": br,
            "cond_branches": cond,
            "br_density": br_density,
            "cond_density": cond_density,
            "cond_taken_rate": cond_taken_rate,
            "backward_rate": backward_rate,
            "backward_taken_rate": backward_taken_rate,
            "uncond_rate": uncond_rate,
            "indirect_rate": indirect_rate,
            "calls_rate": calls_rate,
            "returns_rate": returns_rate,
            "unique_cond_pcs": unique_cond_pcs
        })

    # Save to CSV
    csv_path = outdir / "trace_characteristics.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=features[0].keys())
        writer.writeheader()
        writer.writerows(features)
    print(f"Saved trace characteristics to {csv_path}")

    # EDA Selection of extreme traces
    if len(features) > 1:
        extreme_traces = set()
        
        # Helper to add trace name and reason
        extremes_log = []
        def add_extreme(trace_name, val, reason):
            extreme_traces.add(trace_name)
            extremes_log.append((trace_name, reason, f"{val:.4f}" if isinstance(val, float) else str(val)))

        # Find extremes for different dimensions
        # 1. Branch Density
        features.sort(key=lambda x: x["br_density"])
        add_extreme(features[0]["trace"], features[0]["br_density"], "Min Branch Density")
        add_extreme(features[-1]["trace"], features[-1]["br_density"], "Max Branch Density")

        # 2. Conditional Taken Rate
        features.sort(key=lambda x: x["cond_taken_rate"])
        add_extreme(features[0]["trace"], features[0]["cond_taken_rate"], "Min Cond Taken Rate")
        add_extreme(features[-1]["trace"], features[-1]["cond_taken_rate"], "Max Cond Taken Rate")

        # 3. Unique Conditional PCs (Entropy/Footprint)
        features.sort(key=lambda x: x["unique_cond_pcs"])
        add_extreme(features[0]["trace"], features[0]["unique_cond_pcs"], "Min Unique Cond PCs (Small footprint)")
        add_extreme(features[-1]["trace"], features[-1]["unique_cond_pcs"], "Max Unique Cond PCs (Large footprint)")

        # 4. Backward Conditional Branch Rate
        features.sort(key=lambda x: x["backward_rate"])
        add_extreme(features[0]["trace"], features[0]["backward_rate"], "Min Backward Cond Branch Rate")
        add_extreme(features[-1]["trace"], features[-1]["backward_rate"], "Max Backward Cond Branch Rate")

        # 5. Indirect Unconditional Branch Rate
        features.sort(key=lambda x: x["indirect_rate"])
        add_extreme(features[0]["trace"], features[0]["indirect_rate"], "Min Indirect Branch Rate")
        add_extreme(features[-1]["trace"], features[-1]["indirect_rate"], "Max Indirect Branch Rate")

        print("\n=== SELECTED EXTREME TRACES (EDA) ===")
        for name, reason, val in sorted(extremes_log, key=lambda x: x[1]):
            print(f"  - {name:<20} | Reason: {reason:<45} | Value: {val}")

        # Save selected list to text file
        extremes_path = outdir / "selected_extreme_traces.txt"
        with open(extremes_path, "w") as f:
            for name in sorted(list(extreme_traces)):
                f.write(f"{name}\n")
        print(f"\nSaved list of {len(extreme_traces)} extreme traces to {extremes_path}")
    else:
        print("\nSingle trace evaluated; cannot identify extremes.")

if __name__ == "__main__":
    main()
