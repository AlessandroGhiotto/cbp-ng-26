#!/usr/bin/env python3
"""
CBP-NG Multi-Trace Predictor Comparison under Fixed Hardware Budgets.

This script runs ALL predictor families (scalar and block-based) on a diverse
set of traces at 8KB and 16KB budgets, using VERIFIED optimal configurations
from hardware cost analysis.

Usage:
  python3 profiling/scripts/full_comparison.py [--jobs 16] [--measure 40000000]
"""
import sys
import argparse
import csv
import json
import time
from pathlib import Path
from collections import defaultdict

PROFILING_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PROFILING_DIR.parent
sys.path.append(str(PROFILING_DIR / "lib"))

from profiling_core import (
    run_predictor_on_multiple_traces,
    get_predictor_size_bits,
    compile_predictor,
)

# ─────────────────────────────────────────────────────────────────────────────
# TRACE SELECTION
# Selected traces based on EDA extremes + representative middle-ground traces.
# Together they cover: low/high branch density, low/high taken rate,
# small/large PC footprint, loop-heavy, indirect-heavy, SPEC, web, Java, FP.
# ─────────────────────────────────────────────────────────────────────────────

SELECTED_TRACES = [
    # Extreme: lowest branch density, smallest PC footprint, loop-heavy
    "fp_28",
    # Extreme: highest branch density
    "nodejs-misc-util_7039",
    # Extreme: highest taken rate (~99%)
    "compress_44",
    # Extreme: lowest taken rate (~6%)
    "web_99",
    # Extreme: largest unique cond PCs (66k branches, high aliasing pressure)
    "web_13",
    # Extreme: lowest backward branch rate
    "infra_32",
    # Extreme: highest indirect branch rate
    "tomcat-wrk2-panel.3289_0",
    # Extreme: no indirect branches
    "int_48",
    # Representative: median branch density, SPEC-like workload
    "505-mcf-1_14364",
    # Representative: median unique PCs, data compression
    "compress_47",
    # Representative: integer workload with moderate characteristics
    "int_210",
    # Representative: Java / GC heavy
    "java16-specjbb-4k.23837_0",
]

# ─────────────────────────────────────────────────────────────────────────────
# PREDICTOR CONFIGURATIONS
# Verified hardware cost formulas from source code analysis.
# For each predictor: config uses ~100% of the budget (or as close as possible).
# For predictors with parameter trade-offs (gap, pap, etc.) we test the
# primary sweet-spot config. For TAGE/perceptron we also test alternatives.
#
# BHR_B in bimode is a "free" parameter (doesn't affect RAM); set to a
# reasonable value (12 for 8KB, 14 for 16KB).
#
# NOTE: perceptron_simpleL default LINE_B=2 (LI=4), not LINE_B=4 (LI=16).
# We test both LINE_B=2 and LINE_B=4 for perceptron block predictors.
# ─────────────────────────────────────────────────────────────────────────────

CONFIGS = {
    "8KB": {
        # ── Scalar predictors ──
        "gag":            "gag<15,2>",                           # 65536 exact
        "gap":            "gap<5,10,2>",                          # 65536 exact
        "gshare":         "gshare_simple<15,15,2>",              # 65536 exact
        "pag":            "pag<14,11,2>",                        # 61440 (93.8%)
        "pap":            "pap<8,10,6,2>",                        # 40960 (62.5%)
        "bimode":         "bimode<14,12,13,2>",                  # 65536 exact
        "lxor":           "lxor<10,7>",                          # 39936 (61%)
        "tage_simple":    "tage_simple<10,17,64,4,16,64,3>",     # 64512 (98.4%)
        "tage_simple_u":  "tage_simple_u<10,16,64,4,16,64,3>",  # 64512 (98.4%)
        "perceptron":     "perceptron_simple<9,15,8,83>",        # 65536 exact
        # ── Block predictors ──
        "gagL":           "gagL<11,2,4>",                        # 65536 exact
        "gapL":           "gapL<9,2,2,4>",                       # 65536 exact
        "gshareL":        "gshare_simpleL<11,11,2,4>",           # 65536 exact
        "pagL":           "pagL<10,11,2,4>",                     # 53248 (81%) - tradeoff
        "papL":           "papL<8,12,2,2,4>",                    # 65536 exact
        "bimodeL":        "bimodeL<10,10,9,2,4>",                # 65536 exact
        "lxorL":          "lxorL<12,5,4>",                       # 53248
        "tage_simpleL":   "tage_simpleL<8,16,64,4,16,64,3,4>",  # 61440 (93.8%)
        "tage_simple_uL": "tage_simple_uL<8,15,64,4,16,64,3,4>",# 61440 (93.8%)
        "perceptronL_LI4":  "perceptron_simpleL<8,7,8,83,2>",  # 65536 exact (LI=4)
        "perceptronL_LI16": "perceptron_simpleL<7,3,8,83,4>",   # 65536 exact (LI=16)
    },
    "16KB": {
        # ── Scalar predictors ──
        "gag":            "gag<16,2>",                           # 131072 exact
        "gap":            "gap<10,6,2>",                          # 131072 exact
        "gshare":         "gshare_simple<16,16,2>",              # 131072 exact
        "pag":            "pag<15,12,2>",                        # 126976 (96.9%)
        "pap":            "pap<8,10,7,2>",                        # 73728 (56.2%)
        "bimode":         "bimode<15,14,14,2>",                  # 131072 exact
        "lxor":           "lxor<11,7>",                          # 47104 (35%)
        "tage_simple":    "tage_simple<11,17,64,4,16,64,3>",     # 129024 (98.4%)
        "tage_simple_u":  "tage_simple_u<11,16,64,4,16,64,3>",  # 129024 (98.4%)
        "perceptron":     "perceptron_simple<10,15,8,83>",        # 131072 exact
        # ── Block predictors ──
        "gagL":           "gagL<12,2,4>",                        # 131072 exact
        "gapL":           "gapL<10,2,2,4>",                      # 131072 exact
        "gshareL":        "gshare_simpleL<12,12,2,4>",           # 131072 exact
        "pagL":           "pagL<12,2,2,4>",                      # 131120 (~100%)
        "papL":           "papL<8,10,3,2,4>",                    # 73728
        "bimodeL":        "bimodeL<11,12,10,2,4>",               # 131072 exact
        "lxorL":          "lxorL<12,5,4>",                       # 53248
        "tage_simpleL":   "tage_simpleL<9,16,64,4,16,64,3,4>",  # 122880 (93.7%)
        "tage_simple_uL": "tage_simple_uL<9,16,64,4,16,64,3,4>",# 124416 (94.9%)
        "perceptronL_LI4":  "perceptron_simpleL<9,7,8,83,2>",  # 131072 exact (LI=4)
        "perceptronL_LI16": "perceptron_simpleL<8,3,8,83,4>",   # 131072 exact (LI=16)
    },
}

# Classify predictors for easier analysis
PREDICTOR_TYPE = {}
for name in list(CONFIGS["8KB"].keys()):
    if name.endswith("L") or name.endswith("L_LI4") or name.endswith("L_LI16"):
        PREDICTOR_TYPE[name] = "Block"
    else:
        PREDICTOR_TYPE[name] = "Scalar"

# Map predictor to its "family" for paired scalar/block analysis
FAMILY_MAP = {
    "gag": "GAg", "gagL": "GAg",
    "gap": "GAp", "gapL": "GAp",
    "gshare": "GShare", "gshareL": "GShare",
    "pag": "PAg", "pagL": "PAg",
    "pap": "PAp", "papL": "PAp",
    "bimode": "BiMode", "bimodeL": "BiMode",
    "lxor": "LXOR", "lxorL": "LXOR",
    "tage_simple": "TAGE", "tage_simpleL": "TAGE",
    "tage_simple_u": "TAGE_U", "tage_simple_uL": "TAGE_U",
    "perceptron": "Perceptron",
    "perceptronL_LI4": "Perceptron",
    "perceptronL_LI16": "Perceptron",
}


def resolve_traces(tracedir: Path) -> list[Path]:
    """Find trace files for the selected traces."""
    traces = []
    for name in SELECTED_TRACES:
        # Try multiple filename patterns
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
            # Also check root for test trace
            root_trace = REPO_ROOT / f"{name}_trace.gz"
            if root_trace.exists():
                traces.append(root_trace)
            else:
                print(f"  WARNING: Trace '{name}' not found, skipping.")
    return traces


def main():
    parser = argparse.ArgumentParser(
        description="CBP-NG Full Predictor Comparison on Diverse Traces"
    )
    parser.add_argument(
        "--tracedir",
        default=str(REPO_ROOT / "traces"),
        help="Directory containing traces",
    )
    parser.add_argument(
        "--outdir",
        default=str(PROFILING_DIR / "outputs"),
        help="Output directory",
    )
    parser.add_argument("--warmup", type=int, default=1000000)
    parser.add_argument("--measure", type=int, default=40000000)
    parser.add_argument(
        "--jobs", type=int, default=8, help="Parallel simulation jobs per predictor"
    )
    parser.add_argument(
        "--budget",
        choices=["8KB", "16KB", "both"],
        default="both",
        help="Which budget to run",
    )
    parser.add_argument(
        "--skip-sim",
        action="store_true",
        help="Skip simulation and use existing results",
    )
    args = parser.parse_args()

    tracedir = Path(args.tracedir).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / "full_comparison_results.csv"

    # Resolve traces
    traces = resolve_traces(tracedir)
    if not traces:
        print("ERROR: No traces found.")
        sys.exit(1)
    print(f"Running comparison on {len(traces)} traces:")
    for t in traces:
        print(f"  - {t.name}")

    budgets = ["8KB", "16KB"] if args.budget == "both" else [args.budget]
    results = []

    if not args.skip_sim:
        existing_results = {}
        if csv_path.exists():
            try:
                with open(csv_path, "r") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        metrics = {}
                        for k, v in row.items():
                            if k in ["budget", "pred_name", "family", "mode", "expr", "trace"]:
                                metrics[k] = v
                            else:
                                try:
                                    metrics[k] = float(v) if "." in v or "e" in v.lower() else int(v)
                                except ValueError:
                                    metrics[k] = v
                        existing_results[(row["budget"], row["pred_name"], row["trace"], row["expr"])] = metrics
            except Exception as e:
                print(f"Warning: Could not read existing results from {csv_path}: {e}")

        total_configs = sum(len(CONFIGS[b]) for b in budgets)
        done = 0
        start_time = time.time()

        for budget in budgets:
            print(f"\n{'='*70}")
            print(f"  BUDGET: {budget}")
            print(f"{'='*70}")

            for pred_name, expr in CONFIGS[budget].items():
                done += 1
                elapsed = time.time() - start_time
                eta = (elapsed / done) * (total_configs - done) if done > 0 else 0

                size_bits = get_predictor_size_bits(expr)
                ptype = PREDICTOR_TYPE.get(pred_name, "?")
                family = FAMILY_MAP.get(pred_name, pred_name)

                # Check if all traces for this config are already cached
                all_cached = True
                cached_metrics = {}
                for t in traces:
                    trace_name = t.stem
                    if trace_name.endswith(".gz"):
                        trace_name = Path(trace_name).stem
                    if trace_name.endswith("_trace"):
                        trace_name = trace_name[:-6]
                    
                    key = (budget, pred_name, trace_name, expr)
                    if key in existing_results:
                        cached_metrics[trace_name] = existing_results[key]
                    else:
                        all_cached = False
                        break

                if all_cached:
                    print(f"\n[{done}/{total_configs}] {pred_name} ({ptype}) -> {expr} [Size: {size_bits} bits] - LOADED FROM CACHE")
                    for trace_name, metrics in cached_metrics.items():
                        results.append(metrics)
                    continue

                print(
                    f"\n[{done}/{total_configs}] {pred_name} ({ptype}) "
                    f"-> {expr} [{size_bits} bits] "
                    f"(ETA: {eta/60:.0f}m)"
                )

                try:
                    run_results = run_predictor_on_multiple_traces(
                        expr, traces, args.warmup, args.measure, args.jobs
                    )
                    for trace_name, metrics in run_results.items():
                        results.append(
                            {
                                "budget": budget,
                                "pred_name": pred_name,
                                "family": family,
                                "mode": ptype,
                                "expr": expr,
                                "size_bits": size_bits,
                                "trace": trace_name,
                                **metrics,
                            }
                        )
                        print(
                            f"    {trace_name:<40s} MPKI={metrics['mpki']:7.3f}  "
                            f"IPC={metrics['ipc']:7.4f}  VFS={metrics['vfs']:.6f}"
                        )
                except Exception as e:
                    print(f"    FAILED: {e}")

        # Save results
        if results:
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)
            print(f"\nResults saved to {csv_path}")

        total_time = time.time() - start_time
        print(f"Total time: {total_time/60:.1f} minutes")

    else:
        if not csv_path.exists():
            print(f"ERROR: CSV not found: {csv_path}")
            sys.exit(1)
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            results = [dict(row) for row in reader]
        print(f"Loaded {len(results)} results from {csv_path}")

    # ── Generate analysis report ──
    generate_report(results, outdir)


def generate_report(results: list[dict], outdir: Path):
    """Generate a comprehensive markdown report with insights."""
    report_path = PROFILING_DIR / "Full_Comparison_Report.md"

    # Group results for analysis
    by_budget_pred_trace = defaultdict(dict)
    for r in results:
        key = (r["budget"], r["pred_name"])
        by_budget_pred_trace[key][r["trace"]] = r

    # Get sorted trace list
    traces = sorted(set(r["trace"] for r in results))

    with open(report_path, "w") as f:
        f.write("# CBP-NG Full Predictor Comparison Report\n\n")
        f.write(
            "Multi-trace comparison of all predictor families under "
            "fixed 8KB and 16KB hardware budgets.\n\n"
        )
        f.write(f"**Traces analyzed:** {len(traces)}\n\n")
        for t in traces:
            f.write(f"- `{t}`\n")
        f.write("\n")

        for budget in ["8KB", "16KB"]:
            f.write(f"## {budget} Budget Results\n\n")

            # ── VFS Score Table ──
            f.write("### VFS Scores\n\n")
            # Header
            f.write(f"| Predictor | Mode |")
            for t in traces:
                short = t[:18]
                f.write(f" {short} |")
            f.write(" **Mean** |\n")
            f.write(f"| :--- | :--- |")
            for _ in traces:
                f.write(" :---: |")
            f.write(" :---: |\n")

            pred_names = [k[1] for k in by_budget_pred_trace.keys() if k[0] == budget]
            # Sort: scalar first, then block
            pred_names = sorted(set(pred_names), key=lambda x: (PREDICTOR_TYPE.get(x, "Z"), x))

            for pname in pred_names:
                key = (budget, pname)
                if key not in by_budget_pred_trace:
                    continue
                trace_data = by_budget_pred_trace[key]
                mode = PREDICTOR_TYPE.get(pname, "?")
                f.write(f"| {pname} | {mode} |")
                vfs_values = []
                for t in traces:
                    if t in trace_data:
                        vfs = float(trace_data[t]["vfs"])
                        vfs_values.append(vfs)
                        f.write(f" {vfs:.4f} |")
                    else:
                        f.write(" - |")
                mean_vfs = sum(vfs_values) / len(vfs_values) if vfs_values else 0
                f.write(f" **{mean_vfs:.4f}** |\n")
            f.write("\n")

            # ── MPKI Table ──
            f.write("### MPKI (Mispredictions Per Kilo-Instruction)\n\n")
            f.write(f"| Predictor | Mode |")
            for t in traces:
                short = t[:18]
                f.write(f" {short} |")
            f.write(" **Mean** |\n")
            f.write(f"| :--- | :--- |")
            for _ in traces:
                f.write(" :---: |")
            f.write(" :---: |\n")

            for pname in pred_names:
                key = (budget, pname)
                if key not in by_budget_pred_trace:
                    continue
                trace_data = by_budget_pred_trace[key]
                mode = PREDICTOR_TYPE.get(pname, "?")
                f.write(f"| {pname} | {mode} |")
                mpki_values = []
                for t in traces:
                    if t in trace_data:
                        mpki = float(trace_data[t]["mpki"])
                        mpki_values.append(mpki)
                        f.write(f" {mpki:.2f} |")
                    else:
                        f.write(" - |")
                mean_mpki = sum(mpki_values) / len(mpki_values) if mpki_values else 0
                f.write(f" **{mean_mpki:.2f}** |\n")
            f.write("\n")

        # ── Cross-trace analysis: best predictor per trace ──
        f.write("## Analysis: Best Predictor per Trace\n\n")
        for budget in ["8KB", "16KB"]:
            f.write(f"### {budget}\n\n")
            f.write("| Trace | Best Scalar (VFS) | Best Block (VFS) | Block Speedup |\n")
            f.write("| :--- | :--- | :--- | :---: |\n")

            for t in traces:
                best_scalar_name, best_scalar_vfs = "", 0
                best_block_name, best_block_vfs = "", 0
                for pname in pred_names:
                    key = (budget, pname)
                    if key not in by_budget_pred_trace:
                        continue
                    td = by_budget_pred_trace[key]
                    if t not in td:
                        continue
                    vfs = float(td[t]["vfs"])
                    mode = PREDICTOR_TYPE.get(pname, "?")
                    if mode == "Scalar" and vfs > best_scalar_vfs:
                        best_scalar_vfs = vfs
                        best_scalar_name = pname
                    elif mode == "Block" and vfs > best_block_vfs:
                        best_block_vfs = vfs
                        best_block_name = pname

                speedup = (
                    f"{best_block_vfs / best_scalar_vfs:.2f}x"
                    if best_scalar_vfs > 0
                    else "N/A"
                )
                f.write(
                    f"| {t} | {best_scalar_name} ({best_scalar_vfs:.4f}) "
                    f"| {best_block_name} ({best_block_vfs:.4f}) "
                    f"| {speedup} |\n"
                )
            f.write("\n")

        # ── Family comparison: Scalar vs Block ──
        f.write("## Analysis: Scalar vs Block per Family\n\n")
        f.write(
            "For each family that has both scalar and block variants, compare their "
            "mean VFS across traces.\n\n"
        )
        f.write("| Budget | Family | Scalar VFS (mean) | Block VFS (mean) | Block/Scalar Ratio |\n")
        f.write("| :--- | :--- | :---: | :---: | :---: |\n")
        for budget in ["8KB", "16KB"]:
            family_scalar = defaultdict(list)
            family_block = defaultdict(list)
            for pname in pred_names:
                key = (budget, pname)
                if key not in by_budget_pred_trace:
                    continue
                fam = FAMILY_MAP.get(pname, pname)
                mode = PREDICTOR_TYPE.get(pname, "?")
                for t, td in by_budget_pred_trace[key].items():
                    vfs = float(td["vfs"])
                    if mode == "Scalar":
                        family_scalar[(budget, fam)].append(vfs)
                    else:
                        family_block[(budget, fam)].append(vfs)

            for fam in sorted(
                set(f for _, f in list(family_scalar.keys()) + list(family_block.keys()))
            ):
                s_vals = family_scalar.get((budget, fam), [])
                b_vals = family_block.get((budget, fam), [])
                s_mean = sum(s_vals) / len(s_vals) if s_vals else 0
                b_mean = sum(b_vals) / len(b_vals) if b_vals else 0
                ratio = f"{b_mean / s_mean:.2f}x" if s_mean > 0 else "N/A"
                f.write(
                    f"| {budget} | {fam} | {s_mean:.4f} | {b_mean:.4f} | {ratio} |\n"
                )
        f.write("\n")

    print(f"Report generated: {report_path}")


if __name__ == "__main__":
    main()
