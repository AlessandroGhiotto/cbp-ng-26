#!/usr/bin/env python3
"""
pagL vs papL Parameter Space Explorer.
Compares block-based pagL and papL predictors under identical index budgets.
Generates CSV reports and visual scaling plots.
"""

import argparse
import csv
import math
import subprocess
import sys
from pathlib import Path
import matplotlib.pyplot as plt

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
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
    parser = argparse.ArgumentParser(description="Sweep pagL vs papL Parameters")
    parser.add_argument("--warmup", type=int, default=100000)
    parser.add_argument("--measure", type=int, default=1000000)
    parser.add_argument("--outdir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--trace", default=str(DEFAULT_TRACE))
    parser.add_argument("--skip-sim", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "pagL_vs_papL_results.csv"

    results = []

    if not args.skip_sim:
        trace_path = Path(args.trace).resolve()
        if not trace_path.exists():
            print(f"Error: Trace not found at {trace_path}")
            sys.exit(1)

        # Sweeping total index bits B from 6 to 12
        configs = []
        for B in [6, 8, 10, 12]:
            # pagL (PC_B2 = 0)
            configs.append({"type": "pagL", "expr": f"pagL<{B},8,2,4>", "B": B, "PC_B2": 0, "BHR_B": B})
            # papL (PC_B2 = 2, 4, 6, ...)
            for pc in range(2, B, 2):
                bhr = B - pc
                configs.append({"type": "papL", "expr": f"papL<{bhr},8,{pc},2,4>", "B": B, "PC_B2": pc, "BHR_B": bhr})

        print(f"Sweeping {len(configs)} pagL vs papL configurations...")
        for cfg in configs:
            expr = cfg["expr"]
            print(f"Running: {expr} (Total bits: {cfg['B']}, PC_B2: {cfg['PC_B2']}, Local History: {cfg['BHR_B']})")
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
            fieldnames = ["type", "expr", "B", "PC_B2", "BHR_B", "ipc", "cpi", "epi", "mpki", "vfs"]
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
                    "type": row["type"],
                    "expr": row["expr"],
                    "B": int(row["B"]),
                    "PC_B2": int(row["PC_B2"]),
                    "BHR_B": int(row["BHR_B"]),
                    "ipc": float(row["ipc"]),
                    "cpi": float(row["cpi"]),
                    "epi": float(row["epi"]),
                    "mpki": float(row["mpki"]),
                    "vfs": float(row["vfs"])
                })

    # Generate 2x2 comparison plots
    print("\nGenerating comparison plots...")
    fig, axs = plt.subplots(2, 2, figsize=(16, 14))
    fig.suptitle("pagL vs papL: Superscalar Local History Indexing Sweep", fontsize=18, fontweight='bold', y=0.98)
    ax1, ax2, ax3, ax4 = axs.flatten()

    pc_splits = [0, 2, 4, 6]
    colors = ['#e6194B', '#3cb44b', '#4363d8', '#f58231']
    
    # 1. MPI vs B
    for idx, pc in enumerate(pc_splits):
        subset = [r for r in results if r["PC_B2"] == pc]
        subset = sorted(subset, key=lambda x: x["B"])
        if subset:
            b_vals = [r["B"] for r in subset]
            mpi_vals = [r["mpki"] / 10.0 for r in subset]
            label = "pagL (PC_B2=0)" if pc == 0 else f"papL (PC_B2={pc})"
            ax1.plot(b_vals, mpi_vals, marker='o', linewidth=2.5, color=colors[idx], label=label)
            
    ax1.set_title("Accuracy vs PHT Index Size", fontsize=13, fontweight='bold', pad=15)
    ax1.set_xlabel("PHT Index Bits (BHR_B + PC_B2)", fontsize=11, fontweight='bold')
    ax1.set_ylabel("MPI (%)", fontsize=11, fontweight='bold')
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.spines['left'].set_color('#cccccc')
    ax1.spines['bottom'].set_color('#cccccc')
    ax1.tick_params(colors='#555555')
    ax1.grid(True, linestyle=':', alpha=0.6, color='#bbbbbb')
    ax1.legend()

    # 2. IPC vs B
    for idx, pc in enumerate(pc_splits):
        subset = [r for r in results if r["PC_B2"] == pc]
        subset = sorted(subset, key=lambda x: x["B"])
        if subset:
            b_vals = [r["B"] for r in subset]
            ipc_vals = [r["ipc"] for r in subset]
            label = "pagL (PC_B2=0)" if pc == 0 else f"papL (PC_B2={pc})"
            ax2.plot(b_vals, ipc_vals, marker='o', linewidth=2.5, color=colors[idx], label=label)

    ax2.set_title("Performance (IPC) vs PHT Index Size", fontsize=13, fontweight='bold', pad=15)
    ax2.set_xlabel("PHT Index Bits (BHR_B + PC_B2)", fontsize=11, fontweight='bold')
    ax2.set_ylabel("IPC", fontsize=11, fontweight='bold')
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.spines['left'].set_color('#cccccc')
    ax2.spines['bottom'].set_color('#cccccc')
    ax2.tick_params(colors='#555555')
    ax2.grid(True, linestyle=':', alpha=0.6, color='#bbbbbb')
    ax2.legend()

    # 3. Energy vs B
    for idx, pc in enumerate(pc_splits):
        subset = [r for r in results if r["PC_B2"] == pc]
        subset = sorted(subset, key=lambda x: x["B"])
        if subset:
            b_vals = [r["B"] for r in subset]
            epi_vals = [r["epi"] for r in subset]
            label = "pagL (PC_B2=0)" if pc == 0 else f"papL (PC_B2={pc})"
            ax3.plot(b_vals, epi_vals, marker='o', linewidth=2.5, color=colors[idx], label=label)

    ax3.set_title("Energy vs PHT Index Size", fontsize=13, fontweight='bold', pad=15)
    ax3.set_xlabel("PHT Index Bits (BHR_B + PC_B2)", fontsize=11, fontweight='bold')
    ax3.set_ylabel("EPI (fJ)", fontsize=11, fontweight='bold')
    ax3.spines['top'].set_visible(False)
    ax3.spines['right'].set_visible(False)
    ax3.spines['left'].set_color('#cccccc')
    ax3.spines['bottom'].set_color('#cccccc')
    ax3.tick_params(colors='#555555')
    ax3.grid(True, linestyle=':', alpha=0.6, color='#bbbbbb')
    ax3.legend()

    # 4. Bar plot for fixed budget (B = 10 bits)
    fixed_b = 10
    subset_b = [r for r in results if r["B"] == fixed_b]
    subset_b = sorted(subset_b, key=lambda x: x["PC_B2"])
    
    if subset_b:
        bar_labels = [f"PC2={r['PC_B2']}\nH={r['BHR_B']}" for r in subset_b]
        bar_mpi = [r["mpki"] / 10.0 for r in subset_b]
        
        bar_colors = ['#e6194B', '#c0392b', '#8e44ad', '#3498db', '#2ecc71'][:len(subset_b)]
        bars = ax4.bar(bar_labels, bar_mpi, color=bar_colors, edgecolor='#333333', linewidth=0.5, alpha=0.85, width=0.6)
        
        ax4.set_title(f"Optimal Split for Fixed Budget (B={fixed_b} bits)", fontsize=13, fontweight='bold', pad=15)
        ax4.set_xlabel("Bit Partitioning Split", fontsize=11, fontweight='bold')
        ax4.set_ylabel("MPI (%)", fontsize=11, fontweight='bold')
        ax4.spines['top'].set_visible(False)
        ax4.spines['right'].set_visible(False)
        ax4.spines['left'].set_color('#cccccc')
        ax4.spines['bottom'].set_color('#cccccc')
        ax4.tick_params(colors='#555555')
        ax4.grid(axis='y', linestyle=':', alpha=0.6, color='#bbbbbb')
        ax4.set_axisbelow(True)
        
        for bar in bars:
            height = bar.get_height()
            ax4.annotate(f"{height:.3f}%",
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=8, fontweight='bold')

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plot_path = out_dir / "pagL_vs_papL_exploration.png"
    plt.savefig(plot_path, dpi=150)
    print(f"Saved exploration plot: {plot_path}")
    plt.close()


if __name__ == "__main__":
    main()
