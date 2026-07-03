#!/usr/bin/env python3
import sys
import subprocess
import argparse
import csv
from pathlib import Path

PROFILING_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROFILING_DIR.parent
sys.path.append(str(PROFILING_DIR / "lib"))

from profiling_core import run_cmd

def run_script(script_name: str, args_list: list[str]) -> None:
    print(f"\n==================================================")
    print(f"Running {script_name}...")
    print(f"==================================================")
    cmd = f"python3 {PROFILING_DIR}/{script_name} " + " ".join(args_list)
    # Redirect output to console
    subprocess.run(["python3", str(PROFILING_DIR / script_name)] + args_list, cwd=REPO_ROOT)

def main():
    parser = argparse.ArgumentParser(description="Master coordinator for CBP-NG EDA Profiling Suite")
    parser.add_argument("--tracedir", default=str(REPO_ROOT / "traces"), help="Directory containing traces")
    parser.add_argument("--outdir", default=str(PROFILING_DIR / "outputs"), help="Output directory")
    parser.add_argument("--warmup", type=int, default=1000000)
    parser.add_argument("--measure", type=int, default=10000000)
    parser.add_argument("--jobs", type=int, default=8, help="Parallel simulation jobs")
    parser.add_argument("--skip-sim", action="store_true", help="Skip simulation and use cached results")
    args = parser.parse_args()

    # Pass args to sub-scripts
    sub_args = [
        "--tracedir", args.tracedir,
        "--outdir", args.outdir,
        "--warmup", str(args.warmup),
        "--measure", str(args.measure),
        "--jobs", str(args.jobs)
    ]
    if args.skip_sim:
        sub_args.append("--skip-sim")

    # Step 1: Run Trace Analysis / EDA
    print("\n==================================================")
    print("Step 1: Running Trace Workload Analysis (EDA)...")
    print("==================================================")
    subprocess.run(["python3", str(PROFILING_DIR / "analyze_traces.py"), 
                    "--tracedir", args.tracedir, 
                    "--outdir", args.outdir,
                    "--warmup", str(args.warmup),
                    "--measure", str(args.measure),
                    "--jobs", str(args.jobs)], cwd=REPO_ROOT)

    # Step 2: Run TAGE Comparison
    run_script("tage_comparison.py", sub_args)

    # Step 3: Run Perceptron Sweep
    run_script("perceptron_comparison.py", sub_args)

    # Step 4: Run Family Comparison (Scalar vs Block)
    run_script("family_comparison.py", sub_args)

    # Step 5: Generate Report
    print("\nGenerating final summary report...")
    generate_summary_report(Path(args.outdir))

def generate_summary_report(outdir: Path):
    report_path = PROFILING_DIR / "EDA_Profiling_Report.md"
    
    with open(report_path, "w") as f:
        f.write("# CBP-NG Predictor Exploratory Data Analysis & Profiling Report\n\n")
        f.write("This report summarizes trace workload characterization and predictor performance analysis under fixed hardware budgets (8KB and 16KB).\n\n")
        
        # 1. Trace characteristics
        char_csv = outdir / "trace_characteristics.csv"
        if char_csv.exists():
            f.write("## 1. Trace Workload Characteristics\n\n")
            f.write("We characterized the instruction mix and branch behaviors across the traces. Here are the key statistics:\n\n")
            f.write("| Trace Name | Insts | Branches | Cond Br | Br Density | Cond Taken Rate | Loop Backwards Rate | Unique Cond PCs |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
            with open(char_csv, "r") as csv_f:
                reader = csv.DictReader(csv_f)
                for r in reader:
                    f.write(f"| {r['trace']} | {int(r['instructions']):,} | {int(r['branches']):,} | {int(r['cond_branches']):,} | {float(r['br_density']):.2%} | {float(r['cond_taken_rate']):.2%} | {float(r['backward_rate']):.2%} | {r['unique_cond_pcs']} |\n")
            f.write("\n")

        # 2. TAGE comparison
        tage_csv = outdir / "tage_comparison_results.csv"
        if tage_csv.exists():
            f.write("## 2. TAGE Variants Comparison\n\n")
            f.write("Comparison of standard TAGE, TAGE with utility bits (u), and their block-based counterparts (L) under matched budgets:\n\n")
            f.write("| Budget | Predictor Name | Trace Name | MPKI | IPC | VFS Score |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
            with open(tage_csv, "r") as csv_f:
                reader = csv.DictReader(csv_f)
                results = sorted(list(reader), key=lambda x: (x["budget"], x["name"], x["trace"]))
                for r in results:
                    f.write(f"| {r['budget']} | {r['name']} | {r['trace']} | {float(r['mpki']):.4f} | {float(r['ipc']):.4f} | **{float(r['vfs']):.6f}** |\n")
            f.write("\n")

        # 3. Perceptron Sweep
        perc_csv = outdir / "perceptron_comparison_results.csv"
        if perc_csv.exists():
            f.write("## 3. Perceptron Parameter Sweep\n\n")
            f.write("Evaluating Perceptron with different History Lengths (BHR), weights bits (W), and block vs scalar designs:\n\n")
            f.write("| Budget | Configuration | Trace Name | MPKI | IPC | VFS Score |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
            with open(perc_csv, "r") as csv_f:
                reader = csv.DictReader(csv_f)
                results = sorted(list(reader), key=lambda x: (x["budget"], x["name"], x["trace"]))
                for r in results:
                    f.write(f"| {r['budget']} | {r['name']} | {r['trace']} | {float(r['mpki']):.4f} | {float(r['ipc']):.4f} | **{float(r['vfs']):.6f}** |\n")
            f.write("\n")

        # 4. Family comparison
        fam_csv = outdir / "family_comparison_results.csv"
        if fam_csv.exists():
            f.write("## 4. Predictor Families: Scalar vs Block Prediction\n\n")
            f.write("Analyzing the VFS and speedup benefits of block-based (superscalar, LI=16) branch prediction versus scalar designs:\n\n")
            f.write("| Budget | Family | Mode | Trace Name | MPKI | IPC | VFS Score |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
            with open(fam_csv, "r") as csv_f:
                reader = csv.DictReader(csv_f)
                results = sorted(list(reader), key=lambda x: (x["budget"], x["family"], x["mode"], x["trace"]))
                for r in results:
                    f.write(f"| {r['budget']} | {r['family']} | {r['mode']} | {r['trace']} | {float(r['mpki']):.4f} | {float(r['ipc']):.4f} | **{float(r['vfs']):.6f}** |\n")
            f.write("\n")

    print(f"Generated unified EDA profiling report at: {report_path}")

if __name__ == "__main__":
    main()
