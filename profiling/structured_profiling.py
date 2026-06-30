#!/usr/bin/env python3
"""
Structured Profiling and Comparison of CBP-NG Branch Predictor Designs.
Evaluates 15 custom predictors under 8KB and 16KB hardware budgets,
alongside championship baselines (reference and default TAGE).
"""

import argparse
import csv
import math
import subprocess
import sys
import shutil
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "profiling" / "outputs"
DEFAULT_TRACE = REPO_ROOT / "gcc_test_trace.gz"
APPTAINER_SIF = Path("/home/ghi/Documents/HPC-PoliMi/1-AMSC/amsc_mk_2025.sif")

# List of all configurations to profile
CONFIGS = {
    "8KB": [
        # Scalar
        {
            "name": "gag",
            "expr": "gag<15,2>",
            "type": "Scalar",
            "size_desc": "2^15 * 2b",
            "size_bits": 65536,
        },
        {
            "name": "gap",
            "expr": "gap<9,6,2>",
            "type": "Scalar",
            "size_desc": "2^15 * 2b",
            "size_bits": 65536,
        },
        {
            "name": "gshare",
            "expr": "gshare_simple<15,15,2>",
            "type": "Scalar",
            "size_desc": "2^15 * 2b",
            "size_bits": 65536,
        },
        {
            "name": "pag",
            "expr": "pag<12,12,2>",
            "type": "Scalar",
            "size_desc": "2^12 * 2b + 2^12 * 12b",
            "size_bits": 57344,
        },
        {
            "name": "pap",
            "expr": "pap<8,12,6,2>",
            "type": "Scalar",
            "size_desc": "2^14 * 2b + 2^12 * 8b",
            "size_bits": 65536,
        },
        {
            "name": "lxor",
            "expr": "lxor<12,7>",
            "type": "Scalar",
            "size_desc": "2^12 * 7b + 2^14 * 2b",
            "size_bits": 61440,
        },
        {
            "name": "lxor_vibe",
            "expr": "lxor_vibe<12,7>",
            "type": "Scalar",
            "size_desc": "2^12 * 7b + 2^14 * 2b",
            "size_bits": 61440,
        },
        {
            "name": "bimode",
            "expr": "bimode<14,12,13,2>",
            "type": "Scalar",
            "size_desc": "(2^14 + 2*2^13) * 2b",
            "size_bits": 65536,
        },
        {
            "name": "bimode_singleram",
            "expr": "bimode_singleram<14,12,13,2>",
            "type": "Scalar",
            "size_desc": "(2^14 + 2^14) * 2b",
            "size_bits": 65536,
        },
        {
            "name": "tage_simple",
            "expr": "tage_simple<10,16,64,4,16,64,3>",
            "type": "Scalar",
            "size_desc": "2^10 * (12 + 3*16)b",
            "size_bits": 61440,
        },
        # Block (Fetch width = 16)
        {
            "name": "gagL",
            "expr": "gagL<11,2,4>",
            "type": "Block",
            "size_desc": "2^11 * 16 * 2b",
            "size_bits": 65536,
        },
        {
            "name": "gapL",
            "expr": "gapL<6,5,2,4>",
            "type": "Block",
            "size_desc": "2^11 * 16 * 2b",
            "size_bits": 65536,
        },
        {
            "name": "pagL",
            "expr": "pagL<10,11,2,4>",
            "type": "Block",
            "size_desc": "2^10 * 16 * 2b + 2^11 * 10b",
            "size_bits": 53248,
        },
        {
            "name": "papL",
            "expr": "papL<8,12,2,2,4>",
            "type": "Block",
            "size_desc": "2^10 * 16 * 2b + 2^12 * 8b",
            "size_bits": 65536,
        },
        {
            "name": "bimodeL",
            "expr": "bimodeL<10,10,9,2,4>",
            "type": "Block",
            "size_desc": "(2^10 + 2*2^9) * 16 * 2b",
            "size_bits": 65536,
        },
    ],
    "16KB": [
        # Scalar
        {
            "name": "gag",
            "expr": "gag<16,2>",
            "type": "Scalar",
            "size_desc": "2^16 * 2b",
            "size_bits": 131072,
        },
        {
            "name": "gap",
            "expr": "gap<10,6,2>",
            "type": "Scalar",
            "size_desc": "2^16 * 2b",
            "size_bits": 131072,
        },
        {
            "name": "gshare",
            "expr": "gshare_simple<16,16,2>",
            "type": "Scalar",
            "size_desc": "2^16 * 2b",
            "size_bits": 131072,
        },
        {
            "name": "pag",
            "expr": "pag<15,12,2>",
            "type": "Scalar",
            "size_desc": "2^15 * 2b + 2^12 * 15b",
            "size_bits": 126976,
        },
        {
            "name": "pap",
            "expr": "pap<8,13,7,2>",
            "type": "Scalar",
            "size_desc": "2^15 * 2b + 2^13 * 8b",
            "size_bits": 131072,
        },
        {
            "name": "lxor",
            "expr": "lxor<13,7>",
            "type": "Scalar",
            "size_desc": "2^13 * 7b + 2^14 * 2b",
            "size_bits": 90112,
        },
        {
            "name": "lxor_vibe",
            "expr": "lxor_vibe<13,7>",
            "type": "Scalar",
            "size_desc": "2^13 * 7b + 2^14 * 2b",
            "size_bits": 90112,
        },
        {
            "name": "bimode",
            "expr": "bimode<15,14,14,2>",
            "type": "Scalar",
            "size_desc": "(2^15 + 2*2^14) * 2b",
            "size_bits": 131072,
        },
        {
            "name": "bimode_singleram",
            "expr": "bimode_singleram<15,12,14,2>",
            "type": "Scalar",
            "size_desc": "(2^15 + 2^15) * 2b",
            "size_bits": 131072,
        },
        {
            "name": "tage_simple",
            "expr": "tage_simple<11,16,64,4,16,64,3>",
            "type": "Scalar",
            "size_desc": "2^11 * (12 + 3*16)b",
            "size_bits": 122880,
        },
        # Block (Fetch width = 16)
        {
            "name": "gagL",
            "expr": "gagL<12,2,4>",
            "type": "Block",
            "size_desc": "2^12 * 16 * 2b",
            "size_bits": 131072,
        },
        {
            "name": "gapL",
            "expr": "gapL<6,6,2,4>",
            "type": "Block",
            "size_desc": "2^12 * 16 * 2b",
            "size_bits": 131072,
        },
        {
            "name": "pagL",
            "expr": "pagL<11,12,2,4>",
            "type": "Block",
            "size_desc": "2^11 * 16 * 2b + 2^12 * 11b",
            "size_bits": 110592,
        },
        {
            "name": "papL",
            "expr": "papL<8,13,3,2,4>",
            "type": "Block",
            "size_desc": "2^11 * 16 * 2b + 2^13 * 8b",
            "size_bits": 131072,
        },
        {
            "name": "bimodeL",
            "expr": "bimodeL<11,12,10,2,4>",
            "type": "Block",
            "size_desc": "(2^11 + 2*2^10) * 16 * 2b",
            "size_bits": 131072,
        },
    ],
}


def calculate_vfs_score(ipc: float, cpi: float, epi: float) -> float:
    IPCcbp0 = 8.0
    CPIcbp0 = 0.0315
    EPIcbp0 = 1000.0
    ALPHA = 1.625
    BETA = 4.0 * ALPHA / (ALPHA - 1.0) ** 2
    GAMMA = 2.0 / (ALPHA - 1.0)
    cbp_energy_ratio = 0.05
    WPI0 = IPCcbp0 * CPIcbp0
    WPI = ipc * cpi
    speedup = (ipc / IPCcbp0) * (1.0 + WPI0) / (1.0 + WPI)
    LAMBDA = 1.0 / (1.0 + WPI0 / 2.0) - cbp_energy_ratio
    normalizedEPI = ((epi / EPIcbp0) * cbp_energy_ratio + LAMBDA * speedup**GAMMA) * (
        1.0 + WPI / 2.0
    )

    vfs_arg = 1.0 + BETA / (speedup * normalizedEPI)
    if vfs_arg <= 0:
        return 0.0

    vfs = speedup * ALPHA * (1.0 - 2.0 / (1.0 + math.sqrt(vfs_arg)))
    return vfs


def run_command(cmd: str) -> str:
    if shutil.which("apptainer"):
        full_cmd = [
            "apptainer",
            "exec",
            str(APPTAINER_SIF),
            "bash",
            "-lc",
            f"source /u/sw/etc/bash.bashrc && {cmd}",
        ]
    else:
        full_cmd = ["bash", "-lc", cmd]

    proc = subprocess.run(full_cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed: {cmd}\nStderr: {proc.stderr}\nStdout: {proc.stdout}"
        )
    return proc.stdout


def run_predictor(expr: str, trace: Path, warmup: int, measure: int) -> dict:
    print(f"  Compiling {expr}...")
    run_command(f'./compile cbp -DPREDICTOR="{expr}"')

    print(f"  Simulating {expr}...")
    stdout = run_command(f"./cbp {trace} test {warmup} {measure}")

    lines = [l.strip() for l in stdout.splitlines() if l.strip()]
    csv_line = lines[-1]
    parts = csv_line.split(",")

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
        cycles = (
            npred * max(1, p1_lat) + diverge * p2_lat - diverge_at_end * max(1, p1_lat)
        )
    cycles += extra

    IPC = instr / cycles
    p2_to_exec_stages = 9.0
    CPI = MPI * (p2_to_exec_stages + p2_lat - max(1, min(p1_lat, p2_lat)))
    vfs = calculate_vfs_score(IPC, CPI, epi)

    return {"ipc": IPC, "cpi": CPI, "epi": epi, "mpki": MPKI, "vfs": vfs}


def main():
    parser = argparse.ArgumentParser(
        description="Structured Branch Predictor Profiling"
    )
    parser.add_argument("--warmup", type=int, default=1000000)
    parser.add_argument("--measure", type=int, default=10000000)
    parser.add_argument("--outdir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--trace", default=str(DEFAULT_TRACE))
    parser.add_argument("--skip-sim", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "structured_profiling_results.csv"

    results = []

    if not args.skip_sim:
        trace_path = Path(args.trace).resolve()
        if not trace_path.exists():
            print(f"Error: Trace not found at {trace_path}")
            sys.exit(1)

        # 1. Run baselines
        # TAGE Baseline
        print("Running Baseline TAGE...")
        try:
            metrics_tage = run_predictor(
                "tage<>", trace_path, args.warmup, args.measure
            )
            results.append(
                {
                    "budget": "35KB",
                    "name": "championship_tage",
                    "expr": "tage<>",
                    "type": "Block",
                    "size_desc": "~35 KB (Default TAGE)",
                    "size_bits": 286720,
                    **metrics_tage,
                }
            )
        except Exception as e:
            print(f"Failed running championship TAGE baseline: {e}")

        # Software Reference (CBP2025)
        print("Running Software Reference (CBP2025)...")
        try:
            print("  Compiling reference.cpp...")
            run_command("g++ -std=c++20 -o reference reference.cpp -lz -O3")
            print("  Simulating reference...")
            stdout_ref = run_command(
                f"./reference {trace_path} test {args.warmup} {args.measure}"
            )
            lines = [l.strip() for l in stdout_ref.splitlines() if l.strip()]
            csv_line = lines[-1]
            parts = csv_line.split(",")
            instr = float(parts[1])
            misp = float(parts[8])
            ref_mpki = (misp / instr) * 1000.0

            # Reference core fixed stats
            results.append(
                {
                    "budget": "Software",
                    "name": "reference_cbp2025",
                    "expr": "reference",
                    "type": "Scalar",
                    "size_desc": "N/A (S/W Only)",
                    "size_bits": 0,
                    "ipc": 0.987,
                    "cpi": 0.0315,
                    "epi": 0.0,
                    "mpki": ref_mpki,
                    "vfs": 0.0,
                }
            )
        except Exception as e:
            print(f"Failed running software reference baseline: {e}")

        # 2. Run our predictors
        for budget in ["8KB", "16KB"]:
            print(f"\n--- Profiling {budget} Configurations ---")
            for cfg in CONFIGS[budget]:
                expr = cfg["expr"]
                print(f"Predictor: {cfg['name']} ({expr})")
                try:
                    metrics = run_predictor(expr, trace_path, args.warmup, args.measure)
                    results.append(
                        {
                            "budget": budget,
                            "name": cfg["name"],
                            "expr": expr,
                            "type": cfg["type"],
                            "size_desc": cfg["size_desc"],
                            "size_bits": cfg["size_bits"],
                            **metrics,
                        }
                    )
                except Exception as e:
                    print(f"Execution failed for {expr}: {e}")

        # Save to CSV
        with open(csv_path, "w", newline="") as f:
            fieldnames = [
                "budget",
                "name",
                "expr",
                "type",
                "size_desc",
                "size_bits",
                "ipc",
                "cpi",
                "epi",
                "mpki",
                "vfs",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"\nResults saved to {csv_path}")

    else:
        if not csv_path.exists():
            print(f"Error: CSV not found at {csv_path}")
            sys.exit(1)
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                results.append(
                    {
                        "budget": row["budget"],
                        "name": row["name"],
                        "expr": row["expr"],
                        "type": row["type"],
                        "size_desc": row["size_desc"],
                        "size_bits": int(row["size_bits"]),
                        "ipc": float(row["ipc"]),
                        "cpi": float(row["cpi"]),
                        "epi": float(row["epi"]),
                        "mpki": float(row["mpki"]),
                        "vfs": float(row["vfs"]),
                    }
                )

    # Generate structured profiling plots
    print("\nGenerating structured profiling comparison plots...")

    # Separate our predictors from baselines for clean plotting
    baselines = [r for r in results if r["budget"] in ["35KB", "Software"]]
    our_results = [r for r in results if r["budget"] in ["8KB", "16KB"]]

    # Get lists of models
    model_names = sorted(list(set(r["name"] for r in our_results)))

    # Group by budget
    r_8kb = {r["name"]: r for r in our_results if r["budget"] == "8KB"}
    r_16kb = {r["name"]: r for r in our_results if r["budget"] == "16KB"}

    # Extract baseline values
    ref_baseline = next(
        (r for r in baselines if r["name"] == "reference_cbp2025"), None
    )
    tage_baseline = next(
        (r for r in baselines if r["name"] == "championship_tage"), None
    )

    fig, axs = plt.subplots(2, 2, figsize=(18, 14))
    fig.suptitle(
        "Structured Branch Predictor Profiling: 8KB vs 16KB Budget",
        fontsize=18,
        fontweight="bold",
        y=0.98,
    )
    ax1, ax2, ax3, ax4 = axs.flatten()

    x = range(len(model_names))
    width = 0.35

    def plot_metric(ax, metric_key, title, ylabel, ylim=None):
        vals_8kb = [r_8kb[m][metric_key] if m in r_8kb else 0.0 for m in model_names]
        vals_16kb = [r_16kb[m][metric_key] if m in r_16kb else 0.0 for m in model_names]

        # Plot bars
        rects1 = ax.bar(
            [i - width / 2 for i in x],
            vals_8kb,
            width,
            label="8KB Budget",
            color="#4A90E2",
            edgecolor="#333333",
            linewidth=0.5,
            alpha=0.9,
        )
        rects2 = ax.bar(
            [i + width / 2 for i in x],
            vals_16kb,
            width,
            label="16KB Budget",
            color="#50E3C2",
            edgecolor="#333333",
            linewidth=0.5,
            alpha=0.9,
        )

        # Add baseline horizontal lines
        if ref_baseline and ref_baseline[metric_key] > 0:
            ax.axhline(
                y=ref_baseline[metric_key],
                color="#e6194B",
                linestyle="--",
                linewidth=1.5,
                label="Reference (CBP2025)",
            )
        if tage_baseline and tage_baseline[metric_key] > 0:
            ax.axhline(
                y=tage_baseline[metric_key],
                color="#f5a623",
                linestyle="-.",
                linewidth=1.5,
                label="Championship TAGE (35KB)",
            )

        ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
        ax.set_ylabel(ylabel, fontsize=11, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(model_names, rotation=45, ha="right", fontsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#cccccc")
        ax.spines["bottom"].set_color("#cccccc")
        ax.tick_params(colors="#555555")
        ax.grid(axis="y", linestyle=":", alpha=0.6, color="#bbbbbb")
        ax.set_axisbelow(True)
        ax.legend()
        if ylim:
            ax.set_ylim(ylim)

    # 1. VFS Score (Primary)
    plot_metric(
        ax1,
        "vfs",
        "VFS Speedup Score (Higher is Better)",
        "VFS Score",
        ylim=(0.20, 0.85),
    )

    # 2. Accuracy (MPKI)
    plot_metric(
        ax2,
        "mpki",
        "Branch Mispredictions Per Kilo-Instruction (Lower is Better)",
        "MPKI",
        ylim=(0.0, 10.0),
    )

    # 3. Throughput (IPC)
    plot_metric(
        ax3,
        "ipc",
        "Instructions Per Cycle (IPC - Higher is Better)",
        "IPC",
        ylim=(0.8, 5.5),
    )

    # 4. Energy per Instruction (EPI)
    plot_metric(
        ax4,
        "epi",
        "Energy per Instruction (EPI - Lower is Better)",
        "EPI (fJ)",
        ylim=(0.0, 300.0),
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plot_path = out_dir / "structured_profiling.png"
    plt.savefig(plot_path, dpi=150)
    print(f"Saved profiling plot: {plot_path}")
    plt.close()


if __name__ == "__main__":
    main()
