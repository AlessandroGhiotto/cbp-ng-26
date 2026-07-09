#!/usr/bin/env python3
import csv
import json
from pathlib import Path
from collections import defaultdict

PROFILING_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PROFILING_DIR.parent
CSV_PATH = PROFILING_DIR / "outputs" / "full_comparison_results.csv"
SAT_SWEEP_PATH = PROFILING_DIR / "outputs" / "sat_sweep_results.json"

def main():
    if not CSV_PATH.exists():
        print(f"Error: CSV file {CSV_PATH} not found.")
        return

    # budget -> expr -> list of epi
    epi_data = defaultdict(lambda: defaultdict(list))
    
    with open(CSV_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = row["budget"]
            expr = row["expr"]
            epi_val = float(row["epi"])
            epi_data[b][expr].append(epi_val)
            
    # Calculate means
    means = defaultdict(dict)
    for b, expr_dict in epi_data.items():
        for expr, val_list in expr_dict.items():
            means[b][expr] = sum(val_list) / len(val_list)

    # Let's read sat_sweep_results.json to compute its mean EPI as well
    if SAT_SWEEP_PATH.exists():
        with open(SAT_SWEEP_PATH, "r") as f:
            sat_data = json.load(f)
            for b in ["8KB", "16KB"]:
                if b in sat_data:
                    for entry in sat_data[b]:
                        expr = entry["expr"]
                        raw = entry["raw"]
                        epi_vals = [m["epi"] for m in raw.values() if m]
                        if epi_vals:
                            means[b][expr] = sum(epi_vals) / len(epi_vals)

    print("Calculated Mean EPI values:")
    print("=" * 80)
    for b in sorted(means.keys()):
        print(f"--- {b} ---")
        for expr in sorted(means[b].keys()):
            print(f"  {expr:<60} : {means[b][expr]:.1f} fJ")

if __name__ == "__main__":
    main()
