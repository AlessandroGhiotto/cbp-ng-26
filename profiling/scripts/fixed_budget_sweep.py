#!/usr/bin/env python3
"""
Fixed Budget (32 Kbit / 4 KB) Superscalar Predictor Sweeper & Plotter.
Runs gagL, gapL, pagL, papL, and bimodeL under equivalent 32 Kbit storage constraints.
Generates comparative CSVs and 4-panel plot.
"""

import argparse
import csv
import math
import subprocess
import sys
from pathlib import Path
import matplotlib.pyplot as plt

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "profiling" / "outputs"
DEFAULT_TRACE = REPO_ROOT / "gcc_test_trace.gz"


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
    offset = (1.0 + WPI0 / 2.0)
    LAMBDA = 1.0 / offset - cbp_energy_ratio
    normalizedEPI = ((epi / EPIcbp0) * cbp_energy_ratio + LAMBDA * speedup**GAMMA) * (1.0 + WPI / 2.0)
    
    vfs_arg = 1.0 + BETA / (speedup * normalizedEPI)
    if vfs_arg <= 0:
        return 0.0
    
    vfs = speedup * ALPHA * (1.0 - 2.0 / (1.0 + math.sqrt(vfs_arg)))
    return vfs


def run_predictor(expr: str, trace: Path, warmup: int, measure: int) -> dict:
    comp_proc = subprocess.run(
        ["bash", "-lc", f'./compile cbp -DPREDICTOR="{expr}"'],
        cwd=REPO_ROOT, capture_output=True, text=True
    )
    if comp_proc.returncode != 0:
        raise RuntimeError(f"Compilation failed for {expr}: {comp_proc.stderr}")
        
    sim_proc = subprocess.run(
        ["./cbp", str(trace), "test", str(warmup), str(measure)],
        cwd=REPO_ROOT, capture_output=True, text=True
    )
    if sim_proc.returncode != 0:
        raise RuntimeError(f"Simulation failed for {expr}: {sim_proc.stderr}")

    lines = [l.strip() for l in sim_proc.stdout.splitlines() if l.strip()]
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
    
    return {
        "ipc": IPC,
        "cpi": CPI,
        "epi": epi,
        "mpki": MPKI,
        "vfs": vfs
    }


def main():
    parser = argparse.ArgumentParser(description="Run Fixed Budget Sweeps")
    parser.add_argument("--warmup", type=int, default=100000)
    parser.add_argument("--measure", type=int, default=1000000)
    parser.add_argument("--outdir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--trace", default=str(DEFAULT_TRACE))
    parser.add_argument("--skip-sim", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "fixed_budget_results.csv"

    results = []

    # Defined equivalent 32 Kbit block configurations
    configs = [
        {"name": "gagL", "expr": "gagL<10,2,4>", "storage": "32,768 bits"},
        {"name": "gag2L", "expr": "gag2L<2,10,2,4>", "storage": "32,896 bits"},
        {"name": "gapL", "expr": "gapL<2,8,2,4>", "storage": "32,768 bits"},
        {"name": "gap2L", "expr": "gap2L<2,2,8,2,4>", "storage": "33,280 bits"},
        {"name": "pagL", "expr": "pagL<10,8,2,4>", "storage": "35,328 bits"},
        {"name": "pag2L", "expr": "pag2L<4,10,8,2,4>", "storage": "35,840 bits"},
        {"name": "papL", "expr": "papL<2,8,8,2,4>", "storage": "33,280 bits"},
        {"name": "pap2L", "expr": "pap2L<2,2,2,8,8,2,4>", "storage": "33,792 bits"},
        {"name": "bimodeL", "expr": "bimodeL<9,10,8,2,4>", "storage": "32,768 bits"}
    ]

    if not args.skip_sim:
        trace_path = Path(args.trace).resolve()
        if not trace_path.exists():
            print(f"Error: Trace not found at {trace_path}")
            sys.exit(1)

        print("Simulating 32 Kbit (4 KB) equivalent block predictors...")
        for cfg in configs:
            expr = cfg["expr"]
            print(f"Running: {expr} (Target storage: {cfg['storage']})")
            try:
                metrics = run_predictor(expr, trace_path, args.warmup, args.measure)
                results.append({
                    **cfg,
                    **metrics
                })
            except Exception as e:
                print(f"  Execution failed for {expr}: {e}")

        # Save to CSV
        with open(csv_path, "w", newline="") as f:
            fieldnames = ["name", "expr", "storage", "ipc", "cpi", "epi", "mpki", "vfs"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"Results saved to {csv_path}")

    else:
        if not csv_path.exists():
            print(f"Error: CSV not found at {csv_path}")
            sys.exit(1)
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                results.append({
                    "name": row["name"],
                    "expr": row["expr"],
                    "storage": row["storage"],
                    "ipc": float(row["ipc"]),
                    "cpi": float(row["cpi"]),
                    "epi": float(row["epi"]),
                    "mpki": float(row["mpki"]),
                    "vfs": float(row["vfs"])
                })

    # Combine with Software Reference
    comparison_list = [
        {"name": "Reference\n(CBP2025)", "expr": "reference", "ipc": 0.987, "mpi": 0.491, "epi": 0.0, "vfs": 0.0, "storage": "N/A"},
    ]
    for r in results:
        comparison_list.append({
            "name": f"{r['name']}\n{r['expr']}",
            "expr": r["expr"],
            "ipc": r["ipc"],
            "mpi": r["mpki"] / 10.0,
            "epi": r["epi"],
            "vfs": r["vfs"],
            "storage": r["storage"]
        })

    labels = [r["name"] for r in comparison_list]
    mpi_vals = [r["mpi"] for r in comparison_list]
    ipc_vals = [r["ipc"] for r in comparison_list]
    epi_vals = [r["epi"] for r in comparison_list]
    vfs_vals = [r["vfs"] if r["expr"] != "reference" else 0.0 for r in comparison_list]

    colors = ['#7f7f7f', '#4A90E2', '#1F3A60', '#50E3C2', '#234E52', '#F5A623', '#7B341E', '#E284B3', '#702459', '#A890E2']

    # Generate 2x2 comparison plots
    print("\nGenerating 32 Kbit Budget comparison plots...")
    fig, axs = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("Superscalar Predictors: Equal Storage Budget (32 Kbit) Comparison", fontsize=18, fontweight='bold', y=0.98)
    ax1, ax2, ax3, ax4 = axs.flatten()

    def style_bar_axis(ax, title, ylabel):
        ax.set_title(title, fontsize=12, fontweight='bold', pad=10)
        ax.set_ylabel(ylabel, fontsize=10, fontweight='bold')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#cccccc')
        ax.spines['bottom'].set_color('#cccccc')
        ax.tick_params(colors='#555555', labelsize=8)
        ax.grid(axis='y', linestyle=':', alpha=0.6, color='#bbbbbb')
        ax.set_axisbelow(True)

    # 1. MPI
    bars1 = ax1.bar(labels, mpi_vals, color=colors, edgecolor='#333333', linewidth=0.5, alpha=0.85, width=0.55)
    style_bar_axis(ax1, "Branch Misprediction Rate", "MPI (%)")
    for bar in bars1:
        h = bar.get_height()
        ax1.annotate(f"{h:.3f}%", xy=(bar.get_x() + bar.get_width()/2, h), xytext=(0, 3),
                    textcoords="offset points", ha='center', va='bottom', fontsize=8, fontweight='bold')

    # 2. IPC
    bars2 = ax2.bar(labels, ipc_vals, color=colors, edgecolor='#333333', linewidth=0.5, alpha=0.85, width=0.55)
    style_bar_axis(ax2, "Instructions Per Cycle (Fetch Width = 16)", "IPC")
    for bar in bars2:
        h = bar.get_height()
        ax2.annotate(f"{h:.3f}", xy=(bar.get_x() + bar.get_width()/2, h), xytext=(0, 3),
                    textcoords="offset points", ha='center', va='bottom', fontsize=8, fontweight='bold')

    # 3. EPI
    bars3 = ax3.bar(labels, epi_vals, color=colors, edgecolor='#333333', linewidth=0.5, alpha=0.85, width=0.55)
    style_bar_axis(ax3, "Energy per Instruction", "EPI (fJ)")
    for bar in bars3:
        h = bar.get_height()
        label_text = f"{h:.0f} fJ" if h > 0 else "0 fJ\n(S/W)"
        ax3.annotate(label_text, xy=(bar.get_x() + bar.get_width()/2, h), xytext=(0, 3),
                    textcoords="offset points", ha='center', va='bottom', fontsize=8, fontweight='bold')

    # 4. VFS
    bars4 = ax4.bar(labels, vfs_vals, color=colors, edgecolor='#333333', linewidth=0.5, alpha=0.85, width=0.55)
    style_bar_axis(ax4, "VFS Speedup Score", "VFS Score")
    for bar in bars4:
        h = bar.get_height()
        if h > 0:
            ax4.annotate(f"{h:.4f}", xy=(bar.get_x() + bar.get_width()/2, h), xytext=(0, 3),
                        textcoords="offset points", ha='center', va='bottom', fontsize=8, fontweight='bold')
        else:
            ax4.annotate("N/A", xy=(bar.get_x() + bar.get_width()/2, 0.01), xytext=(0, 3),
                        textcoords="offset points", ha='center', va='bottom', fontsize=8, fontweight='bold')

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plot_path = out_dir / "fixed_budget_comparison.png"
    plt.savefig(plot_path, dpi=150)
    print(f"Saved budget comparison plot: {plot_path}")
    plt.close()


if __name__ == "__main__":
    main()
