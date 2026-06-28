#!/usr/bin/env python3
"""Unified profiling and performance visualization script for CBP-NG.

This script compiles, simulates, parses, and plots branch predictor performance,
calculating instructions per cycle (IPC), mispredictions per thousand instructions (MPKI),
dynamic energy per instruction (EPI), and the Voltage-Frequency-Scaled Speedup (VFS) score.
All outputs are organized into structured directories.
"""

import argparse
import csv
import math
import os
import shlex
import subprocess
import sys
from pathlib import Path
import matplotlib.pyplot as plt

# Configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "profiling" / "outputs"
TRACE_PATH = REPO_ROOT / "gcc_test_trace.gz"

# Curated list of predictors for comparison
PREDICTORS = {
    # Baselines
    "bimodal": ("Bimodal (base)", "bimodal<>"),
    "gshare": ("GShare (base)", "gshare<>"),
    "tage": ("TAGE (base)", "tage<>"),
    # Our Pipelined Line-Wide Predictors (Optimized)
    "bimodeL": ("Bi-Mode Line (opt)", "bimodeL<7,6,8,2,4>"),
    "tageL": ("TAGE-Lite Line (opt)", "tageL<8,8,8,8,6>"),
    # Other Custom Predictors
    "bimode": ("Bi-Mode (simple)", "bimode<>"),
    "gshare_simple": ("GShare (simple)", "gshare_simple<>"),
    "lxor": ("LXOR (simple)", "lxor<>"),
    "tage_simple": ("TAGE-Lite (simple)", "tage_simple<>"),
    "gag": ("GAG (simple)", "gag<>"),
    "gagL": ("GAG Line", "gagL<>"),
    "gap": ("GAP (simple)", "gap<>"),
    "gapL": ("GAP Line", "gapL<>"),
    "pag": ("PAG (simple)", "pag<>"),
    "pagL": ("PAG Line", "pagL<>"),
    "pap": ("PAP (simple)", "pap<>"),
    "papL": ("PAP Line", "papL<>"),
}

def run_command(command: list[str], stdout=None) -> str:
    printable = " ".join(shlex.quote(part) for part in command)
    print(f"+ {printable}")
    if stdout is not None:
        subprocess.run(command, cwd=REPO_ROOT, check=True, stdout=stdout, text=True)
        return ""
    else:
        result = subprocess.run(command, cwd=REPO_ROOT, check=True, capture_output=True, text=True)
        return result.stdout

def calculate_vfs_score(ipc: float, cpi: float, epi: float) -> float:
    IPCcbp0 = 8.0
    CPIcbp0 = 0.0315
    EPIcbp0 = 1000.0
    ALPHA = 1.625
    BETA = 4.0 * ALPHA / (ALPHA - 1.0)**2
    GAMMA = 2.0 / (ALPHA - 1.0)
    cbp_energy_ratio = 0.05
    WPI0 = IPCcbp0 * CPIcbp0
    WPI = ipc * cpi
    speedup = (ipc / IPCcbp0) * (1.0 + WPI0) / (1.0 + WPI)
    LAMBDA = 1.0 / (1.0 + WPI0 / 2.0) - cbp_energy_ratio
    normalizedEPI = ((epi / EPIcbp0) * cbp_energy_ratio + LAMBDA * speedup**GAMMA) * (1.0 + WPI / 2.0)
    vfs = speedup * ALPHA * (1.0 - 2.0 / (1.0 + math.sqrt(1.0 + BETA / (speedup * normalizedEPI))))
    return vfs

def main() -> int:
    parser = argparse.ArgumentParser(description="Unified CBP-NG profiling command center.")
    parser.add_argument("--warmup", type=int, default=100000, help="Warmup instructions")
    parser.add_argument("--measure", type=int, default=1000000, help="Measurement instructions")
    parser.add_argument("--outdir", default=str(DEFAULT_OUT_DIR), help="Root directory for outputs")
    parser.add_argument("--predictors", help="Comma-separated list of predictors to run (bimodal,gshare,tage,bimodeL,tageL)")
    args = parser.parse_args()

    # Organize directories
    out_root = Path(args.outdir).resolve()
    raw_data_dir = out_root / "raw_data"
    reports_dir = out_root / "reports"
    raw_data_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Filter predictors
    selected_keys = [k.strip() for k in args.predictors.split(",")] if args.predictors else list(PREDICTORS.keys())
    active_predictors = {k: PREDICTORS[k] for k in selected_keys if k in PREDICTORS}

    if not active_predictors:
        print(f"Error: No valid predictors selected. Available: {list(PREDICTORS.keys())}")
        return 1

    summaries = []

    print(f"Benchmarking predictors: {list(active_predictors.keys())}")
    print(f"Warmup: {args.warmup} | Measure: {args.measure}")
    print(f"Outputs will be saved in: {out_root}")

    for key, (label, expr) in active_predictors.items():
        print(f"\n=== Running {label} ({expr}) ===")
        
        # Compile
        print("Compiling...")
        compile_cmd = ["bash", "-lc", f'./compile cbp -DPREDICTOR="{expr}"']
        run_command(compile_cmd)
        
        # Simulate
        print("Simulating...")
        sim_out_file = raw_data_dir / f"{key}.out"
        sim_cmd = ["./cbp", str(TRACE_PATH), "test", str(args.warmup), str(args.measure)]
        
        with open(sim_out_file, "w") as out_stream:
            run_command(sim_cmd, stdout=out_stream)
        
        # Parse simulation metrics
        with open(sim_out_file, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
            csv_line = lines[-1]
            parts = csv_line.split(',')
            
            instr = float(parts[1])
            npred = float(parts[4])
            extra = float(parts[5])
            diverge = float(parts[6])
            diverge_at_end = float(parts[7])
            misp = float(parts[8])
            p1_lat = math.ceil(float(parts[9]))
            p2_lat = math.ceil(float(parts[10]))
            epi = float(parts[11])

            # Calculate derived metrics
            MPI = misp / instr
            MPKI = MPI * 1000.0
            
            if p2_lat <= p1_lat:
                cycles = npred * max(1, p2_lat)
            else:
                cycles = npred * max(1, p1_lat) + diverge * p2_lat - diverge_at_end * max(1, p1_lat)
            cycles += extra
            
            IPC = instr / cycles
            
            p2_to_exec_stages = 9.0
            CPI = MPI * (p2_to_exec_stages + p2_lat - max(1, min(p1_lat, p2_lat)))
            
            vfs = calculate_vfs_score(IPC, CPI, epi)
            
            print(f"Results -> IPC: {IPC:.4f} | MPKI: {MPKI:.2f} | EPI: {epi:.1f} fJ | VFS: {vfs:.4f}")
            
            summaries.append({
                "key": key,
                "label": label,
                "expr": expr,
                "ipc": IPC,
                "cpi_penalty": CPI,
                "epi": epi,
                "mpki": MPKI,
                "vfs": vfs
            })

    # Sort by VFS Score (descending)
    summaries.sort(key=lambda x: x["vfs"], reverse=True)

    # Save to CSV
    csv_file = reports_dir / "comparison.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["key", "label", "expr", "ipc", "cpi_penalty", "epi", "mpki", "vfs"])
        writer.writeheader()
        writer.writerows(summaries)
    print(f"\nSaved CSV report to {csv_file}")

    # Generate visual plot
    plot_file = reports_dir / "comparison_plots.png"
    print(f"Generating visual plots to {plot_file}...")
    fig, axs = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("CBP-NG Predictor Performance & Physical Metrics Dashboard", fontsize=16, fontweight='bold', y=0.96)
    
    labels = [s["label"] for s in summaries]
    ipcs = [s["ipc"] for s in summaries]
    mpkis = [s["mpki"] for s in summaries]
    epis = [s["epi"] for s in summaries]
    vfss = [s["vfs"] for s in summaries]
    
    colors = ['#4A90E2' if 'Line' not in l else '#50E3C2' for l in labels]
    
    # 1. IPC
    axs[0, 0].bar(labels, ipcs, color=colors, edgecolor='grey', alpha=0.85)
    axs[0, 0].set_title("Instructions Per Cycle (IPC) - Higher is Better", fontsize=11, fontweight='bold')
    axs[0, 0].set_ylabel("IPC")
    axs[0, 0].grid(axis='y', linestyle='--', alpha=0.7)
    for i, v in enumerate(ipcs):
        axs[0, 0].text(i, v + 0.05, f"{v:.2f}", ha='center', va='bottom', fontsize=9, fontweight='bold')
        
    # 2. MPKI
    axs[0, 1].bar(labels, mpkis, color=colors, edgecolor='grey', alpha=0.85)
    axs[0, 1].set_title("Branch Mispredictions (MPKI) - Lower is Better", fontsize=11, fontweight='bold')
    axs[0, 1].set_ylabel("MPKI")
    axs[0, 1].grid(axis='y', linestyle='--', alpha=0.7)
    for i, v in enumerate(mpkis):
        axs[0, 1].text(i, v + 0.1, f"{v:.2f}", ha='center', va='bottom', fontsize=9, fontweight='bold')
        
    # 3. EPI
    axs[1, 0].bar(labels, epis, color=colors, edgecolor='grey', alpha=0.85)
    axs[1, 0].set_title("Energy Per Instruction (EPI) - Lower is Better", fontsize=11, fontweight='bold')
    axs[1, 0].set_ylabel("fJ / Instruction")
    axs[1, 0].grid(axis='y', linestyle='--', alpha=0.7)
    for i, v in enumerate(epis):
        axs[1, 0].text(i, v + 50, f"{int(v)}", ha='center', va='bottom', fontsize=9, fontweight='bold')
        
    # 4. VFS Score
    axs[1, 1].bar(labels, vfss, color=colors, edgecolor='grey', alpha=0.85)
    axs[1, 1].set_title("VFS Score - Higher is Better", fontsize=11, fontweight='bold')
    axs[1, 1].set_ylabel("Score")
    axs[1, 1].grid(axis='y', linestyle='--', alpha=0.7)
    for i, v in enumerate(vfss):
        axs[1, 1].text(i, v + 0.01, f"{v:.4f}", ha='center', va='bottom', fontsize=9, fontweight='bold')

    for ax in axs.flat:
        ax.set_xticklabels(labels, rotation=30, ha='right', fontsize=9)
        
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(plot_file, dpi=150)
    plt.close()

    # Generate Markdown report
    md_file = reports_dir / "performance_report.md"
    print(f"Generating Markdown report to {md_file}...")
    with open(md_file, "w") as f:
        f.write("# Performance & Physical Metrics Comparison Report\n\n")
        f.write("This report presents the system-level tradeoffs of the branch predictors evaluated.\n\n")
        f.write("## 1. Metrics Summary Table\n\n")
        f.write("| Predictor Model | Expression | IPC | MPKI | EPI (fJ) | VFS Score |\n")
        f.write("| :--- | :--- | :---: | :---: | :---: | :---: |\n")
        for s in summaries:
            f.write(f"| **{s['label']}** | `{s['expr']}` | {s['ipc']:.4f} | {s['mpki']:.2f} | {s['epi']:.1f} | **{s['vfs']:.4f}** |\n")
        f.write("\n## 2. Visual Representation\n\n")
        f.write("![Performance Comparison plots](./comparison_plots.png)\n")
        
    print("\n" + "=" * 60)
    print(" DONE! Automated profiling completed successfully.")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
