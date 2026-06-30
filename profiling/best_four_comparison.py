#!/usr/bin/env python3
"""
GAG vs GAP vs PAG vs PAP: Best-of-Class Comparison.
Selects the VFS-optimal configurations of GAG, GAP, PAG, and PAP
and compares them head-to-head alongside the Championship Baselines (Reference & TAGE).
Generates a 4-panel visual comparison plot.
"""

import csv
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "profiling" / "outputs"


def main():
    out_dir = DEFAULT_OUT_DIR.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load sweep results
    gag_gap_csv = out_dir / "gag_vs_gap_results.csv"
    pag_pap_csv = out_dir / "pag_vs_pap_results.csv"
    bimode_csv = out_dir / "bimode_sweep_results.csv"
    lxor_csv = out_dir / "lxor_sweep_results.csv"

    results = {}

    # Read GAG and GAP
    if gag_gap_csv.exists():
        with open(gag_gap_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expr = row["expr"]
                if expr in ["gag<12,2>", "gap<6,6,2>"]:
                    results[expr] = {
                        "name": "GAG" if "gag" in expr else "GAP",
                        "expr": expr,
                        "ipc": float(row["ipc"]),
                        "mpi": float(row["mpki"]) / 10.0,
                        "epi": float(row["epi"]),
                        "vfs": float(row["vfs"]),
                    }

    # Read PAG and PAP
    if pag_pap_csv.exists():
        with open(pag_pap_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expr = row["expr"]
                if expr in ["pag<6,8,2>", "pap<2,8,8,2>"]:
                    results[expr] = {
                        "name": "PAG" if "pag" in expr else "PAP",
                        "expr": expr,
                        "ipc": float(row["ipc"]),
                        "mpi": float(row["mpki"]) / 10.0,
                        "epi": float(row["epi"]),
                        "vfs": float(row["vfs"]),
                    }

    # Read Bi-Mode
    if bimode_csv.exists():
        with open(bimode_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expr = row["expr"]
                if expr == "bimode<10,10,8,2>":
                    results[expr] = {
                        "name": "Bi-Mode",
                        "expr": expr,
                        "ipc": float(row["ipc"]),
                        "mpi": float(row["mpki"]) / 10.0,
                        "epi": float(row["epi"]),
                        "vfs": float(row["vfs"]),
                    }

    # Read LXOR
    if lxor_csv.exists():
        with open(lxor_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expr = row["expr"]
                if expr == "lxor<10,4>":
                    results[expr] = {
                        "name": "LXOR",
                        "expr": expr,
                        "ipc": float(row["ipc"]),
                        "mpi": float(row["mpki"]) / 10.0,
                        "epi": float(row["epi"]),
                        "vfs": float(row["vfs"]),
                    }

    # Verify we got the data
    required = [
        "gag<12,2>",
        "gap<6,6,2>",
        "pag<6,8,2>",
        "pap<2,8,8,2>",
        "bimode<10,10,8,2>",
        "lxor<10,4>",
    ]
    missing = [r for r in required if r not in results]
    if missing:
        print(f"Warning: Missing sweep data for {missing}. Using hardcoded fallbacks.")
        fallback = {
            "gag<12,2>": {
                "name": "GAG",
                "expr": "gag<12,2>",
                "ipc": 0.9866,
                "mpi": 0.8294,
                "epi": 132.0,
                "vfs": 0.2297,
            },
            "gap<6,6,2>": {
                "name": "GAP",
                "expr": "gap<6,6,2>",
                "ipc": 0.9874,
                "mpi": 0.7748,
                "epi": 131.0,
                "vfs": 0.2309,
            },
            "pag<6,8,2>": {
                "name": "PAG",
                "expr": "pag<6,8,2>",
                "ipc": 0.9645,
                "mpi": 0.9665,
                "epi": 72.0,
                "vfs": 0.2233,
            },
            "pap<2,8,8,2>": {
                "name": "PAP",
                "expr": "pap<2,8,8,2>",
                "ipc": 0.9763,
                "mpi": 0.8542,
                "epi": 90.0,
                "vfs": 0.2276,
            },
            "bimode<10,10,8,2>": {
                "name": "Bi-Mode",
                "expr": "bimode<10,10,8,2>",
                "ipc": 0.9803,
                "mpi": 0.7042,
                "epi": 127.0,
                "vfs": 0.2308,
            },
            "lxor<10,4>": {
                "name": "LXOR",
                "expr": "lxor<10,4>",
                "ipc": 0.9717,
                "mpi": 0.9312,
                "epi": 161.0,
                "vfs": 0.2245,
            },
        }
        for m in missing:
            results[m] = fallback[m]

    # Combine with baselines
    comparison_list = [
        # Championship Baseline
        {
            "name": "Reference\n(CBP2025)",
            "expr": "reference",
            "ipc": 0.987,
            "mpi": 0.491,
            "epi": 0.0,
            "vfs": 0.0,
            "is_baseline": True,
        },
        # Our Best Predictors
        {
            **results["gag<12,2>"],
            "is_baseline": False,
            "name": f"GAG\n{results['gag<12,2>']['expr']}",
        },
        {
            **results["gap<6,6,2>"],
            "is_baseline": False,
            "name": f"GAP\n{results['gap<6,6,2>']['expr']}",
        },
        {
            **results["pag<6,8,2>"],
            "is_baseline": False,
            "name": f"PAG\n{results['pag<6,8,2>']['expr']}",
        },
        {
            **results["pap<2,8,8,2>"],
            "is_baseline": False,
            "name": f"PAP\n{results['pap<2,8,8,2>']['expr']}",
        },
        {
            **results["bimode<10,10,8,2>"],
            "is_baseline": False,
            "name": f"Bi-Mode\n{results['bimode<10,10,8,2>']['expr']}",
        },
        {
            **results["lxor<10,4>"],
            "is_baseline": False,
            "name": f"LXOR\n{results['lxor<10,4>']['expr']}",
        },
    ]

    labels = [r["name"] for r in comparison_list]
    mpi_vals = [r["mpi"] for r in comparison_list]
    ipc_vals = [r["ipc"] for r in comparison_list]
    epi_vals = [r["epi"] for r in comparison_list]
    vfs_vals = [r["vfs"] if r["expr"] != "reference" else 0.0 for r in comparison_list]

    # Color coding: grey for baselines, distinctive colors for our predictors
    colors = [
        "#7f7f7f",
        "#4A90E2",
        "#50E3C2",
        "#F5A623",
        "#E284B3",
        "#A890E2",
        "#7ED321",
    ]

    # Create 2x2 grid of plots
    fig, axs = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(
        "Best-of-Class Head-to-Head Comparison", fontsize=18, fontweight="bold", y=0.98
    )
    ax1, ax2, ax3, ax4 = axs.flatten()

    def style_bar_axis(ax, title, ylabel):
        ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
        ax.set_ylabel(ylabel, fontsize=10, fontweight="bold")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#cccccc")
        ax.spines["bottom"].set_color("#cccccc")
        ax.tick_params(colors="#555555", labelsize=8)
        ax.grid(axis="y", linestyle=":", alpha=0.6, color="#bbbbbb")
        ax.set_axisbelow(True)

    # 1. MPI
    bars1 = ax1.bar(
        labels,
        mpi_vals,
        color=colors,
        edgecolor="#333333",
        linewidth=0.5,
        alpha=0.85,
        width=0.55,
    )
    style_bar_axis(ax1, "Branch Misprediction Rate", "MPI (%)")
    for bar in bars1:
        h = bar.get_height()
        ax1.annotate(
            f"{h:.3f}%",
            xy=(bar.get_x() + bar.get_width() / 2, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
        )

    # 2. IPC
    bars2 = ax2.bar(
        labels,
        ipc_vals,
        color=colors,
        edgecolor="#333333",
        linewidth=0.5,
        alpha=0.85,
        width=0.55,
    )
    style_bar_axis(ax2, "Instructions Per Cycle", "IPC")
    ax2.set_ylim(0.9, 1.0)  # Zoom in on IPC since it varies in a tight range
    for bar in bars2:
        h = bar.get_height()
        ax2.annotate(
            f"{h:.3f}",
            xy=(bar.get_x() + bar.get_width() / 2, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
        )

    # 3. EPI
    bars3 = ax3.bar(
        labels,
        epi_vals,
        color=colors,
        edgecolor="#333333",
        linewidth=0.5,
        alpha=0.85,
        width=0.55,
    )
    style_bar_axis(ax3, "Energy per Instruction", "EPI (fJ)")
    for bar in bars3:
        h = bar.get_height()
        label_text = f"{h:.0f} fJ" if h > 0 else "0 fJ\n(S/W)"
        ax3.annotate(
            label_text,
            xy=(bar.get_x() + bar.get_width() / 2, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
        )

    # 4. VFS
    bars4 = ax4.bar(
        labels,
        vfs_vals,
        color=colors,
        edgecolor="#333333",
        linewidth=0.5,
        alpha=0.85,
        width=0.55,
    )
    style_bar_axis(ax4, "VFS Speedup Score", "VFS Score")
    for bar in bars4:
        h = bar.get_height()
        if h > 0:
            ax4.annotate(
                f"{h:.4f}",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
            )
        else:
            ax4.annotate(
                "N/A",
                xy=(bar.get_x() + bar.get_width() / 2, 0.01),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
            )

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plot_path = out_dir / "best_four_comparison.png"
    plt.savefig(plot_path, dpi=150)
    print(f"Saved comparison plot: {plot_path}")
    plt.close()


if __name__ == "__main__":
    main()
