#!/usr/bin/env python3
"""
compute_correct_vfs.py

This script implements the correct VFS scoring methodology described in docs/vfs.pdf:
1. Average the inputs to the VFS formula across all traces:
   - IPC: Harmonic mean
   - CPI: Arithmetic mean
   - EPI: Arithmetic mean
2. Calculate the VFS score using these averaged inputs.
3. Save the results to profiling/outputs/correct_vfs_comparison.csv.
"""

import sys
import math
import csv
import argparse
from pathlib import Path
from collections import defaultdict

# Constants for the VFS calculation (reference core & technology parameters)
IPCcbp0 = 8.0
CPIcbp0 = 0.0315
EPIcbp0 = 1000.0
ALPHA = 1.625
BETA = 4.0 * ALPHA / (ALPHA - 1.0) ** 2
GAMMA = 2.0 / (ALPHA - 1.0)
cbp_energy_ratio = 0.05
WPI0 = IPCcbp0 * CPIcbp0
LAMBDA = 1.0 / (1.0 + WPI0 / 2.0) - cbp_energy_ratio

def calculate_vfs_score(ipc: float, cpi: float, epi: float) -> float:
    """Computes the VFS score given IPC, CPI, and EPI."""
    if ipc <= 0:
        return 0.0
    WPI = ipc * cpi
    speedup = (ipc / IPCcbp0) * (1.0 + WPI0) / (1.0 + WPI)
    normalizedEPI = ((epi / EPIcbp0) * cbp_energy_ratio + LAMBDA * speedup**GAMMA) * (
        1.0 + WPI / 2.0
    )

    vfs_arg = 1.0 + BETA / (speedup * normalizedEPI)
    if vfs_arg <= 0:
        return 0.0

    vfs = speedup * ALPHA * (1.0 - 2.0 / (1.0 + math.sqrt(vfs_arg)))
    return vfs

def harmonic_mean(values: list[float]) -> float:
    """Computes the harmonic mean of a list of values."""
    if not values:
        return 0.0
    try:
        return len(values) / sum(1.0 / v for v in values if v > 0)
    except ZeroDivisionError:
        return 0.0

def arithmetic_mean(values: list[float]) -> float:
    """Computes the arithmetic mean of a list of values."""
    if not values:
        return 0.0
    return sum(values) / len(values)

def main():
    parser = argparse.ArgumentParser(
        description="Aggregate trace metrics correctly to compute VFS scores as per docs/vfs.pdf"
    )
    parser.add_argument(
        "--input",
        default=str(Path(__file__).resolve().parent.parent / "outputs" / "full_comparison_results.csv"),
        help="Path to the input CSV containing trace-level results",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "outputs" / "correct_vfs_comparison.csv"),
        help="Path to save the averaged and comparison CSV results",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: Input file '{input_path}' does not exist.", file=sys.stderr)
        print("Please run the full comparison simulation first to generate trace-level data:", file=sys.stderr)
        print("  python3 profiling/scripts/full_comparison.py --measure 10000000 --jobs 16", file=sys.stderr)
        sys.exit(1)

    print(f"Reading trace-level data from: {input_path}")

    # Group records by configuration key
    configs = defaultdict(list)
    with open(input_path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Key uniquely identifying the predictor configuration
            key = (
                row["budget"],
                row["pred_name"],
                row["family"],
                row["mode"],
                row["expr"],
                int(row["size_bits"])
            )
            configs[key].append(row)

    aggregated_results = []

    for key, rows in configs.items():
        budget, pred_name, family, mode, expr, size_bits = key
        
        ipc_vals = [float(r["ipc"]) for r in rows if r["ipc"]]
        cpi_vals = [float(r["cpi"]) for r in rows if r["cpi"]]
        epi_vals = [float(r["epi"]) for r in rows if r["epi"]]
        vfs_vals = [float(r["vfs"]) for r in rows if r["vfs"]]
        mpki_vals = [float(r["mpki"]) for r in rows if r["mpki"]]
        
        num_traces = len(rows)

        # 1. Harmonic mean of IPC
        avg_ipc = harmonic_mean(ipc_vals)
        # 2. Arithmetic mean of CPI and EPI
        avg_cpi = arithmetic_mean(cpi_vals)
        avg_epi = arithmetic_mean(epi_vals)
        
        # Other averages for completeness
        avg_mpki = arithmetic_mean(mpki_vals)

        # 3. Correct VFS computed from the averaged inputs
        correct_vfs = calculate_vfs_score(avg_ipc, avg_cpi, avg_epi)

        # 4. Old VFS: arithmetic mean of VFS scores
        old_vfs = arithmetic_mean(vfs_vals)

        vfs_diff = correct_vfs - old_vfs

        aggregated_results.append({
            "budget": budget,
            "pred_name": pred_name,
            "family": family,
            "mode": mode,
            "expr": expr,
            "size_bits": size_bits,
            "num_traces": num_traces,
            "avg_ipc_harmonic": avg_ipc,
            "avg_cpi_arithmetic": avg_cpi,
            "avg_epi_arithmetic": avg_epi,
            "avg_mpki_arithmetic": avg_mpki,
            "correct_vfs": correct_vfs,
            "old_vfs_averaged": old_vfs,
            "vfs_diff": vfs_diff
        })

    # Sort results by budget, then by correct_vfs descending
    aggregated_results.sort(key=lambda r: (r["budget"], -r["correct_vfs"]))

    # Write output to CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "budget", "pred_name", "family", "mode", "expr", "size_bits", "num_traces",
        "avg_ipc_harmonic", "avg_cpi_arithmetic", "avg_epi_arithmetic", "avg_mpki_arithmetic",
        "correct_vfs", "old_vfs_averaged", "vfs_diff"
    ]
    with open(output_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(aggregated_results)

    print(f"Aggregated results saved to: {output_path}")

    # Display comparison markdown-style to console
    for b in ["8KB", "16KB"]:
        b_results = [r for r in aggregated_results if r["budget"] == b]
        if not b_results:
            continue
        
        print(f"\n=== BUDGET: {b} (Ranked by Correct VFS) ===")
        print(f"{'Predictor':<18} | {'Mode':<6} | {'Harmonic IPC':<12} | {'Arithmetic CPI':<14} | {'Correct VFS':<11} | {'Old VFS':<8} | {'Difference':<10}")
        print("-" * 92)
        for r in b_results:
            print(
                f"{r['pred_name']:<18} | "
                f"{r['mode']:<6} | "
                f"{r['avg_ipc_harmonic']:12.6f} | "
                f"{r['avg_cpi_arithmetic']:14.6f} | "
                f"{r['correct_vfs']:11.6f} | "
                f"{r['old_vfs_averaged']:8.6f} | "
                f"{r['vfs_diff']:+10.6f}"
            )

if __name__ == "__main__":
    main()
