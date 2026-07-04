#!/usr/bin/env python3
"""
Superscalar Predictor Best-of-Class Comparison.
Selects the VFS-optimal block-based configurations of gagL, gapL, pagL, papL, and bimodeL
and compares them head-to-head alongside the software reference baseline.
Generates a 4-panel comparison plot.
"""

import csv
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "profiling" / "outputs"


def main():
    out_dir = DEFAULT_OUT_DIR.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load sweep results
    gagl_gapl_csv = out_dir / "gagL_vs_gapL_results.csv"
    pagl_papl_csv = out_dir / "pagL_vs_papL_results.csv"
    bimodell_csv = out_dir / "bimodeL_sweep_results.csv"

    results = {}

    # Read gagL and gapL
    if gagl_gapl_csv.exists():
        with open(gagl_gapl_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expr = row["expr"]
                if expr in ["gagL<6,2,4>", "gapL<2,4,2,4>"]:
                    results[expr] = {
                        "name": "gagL" if "gagL" in expr else "gapL",
                        "expr": expr,
                        "ipc": float(row["ipc"]),
                        "mpi": float(row["mpki"]) / 10.0,
                        "epi": float(row["epi"]),
                        "vfs": float(row["vfs"]),
                    }

    # Read pagL and papL
    if pagl_papl_csv.exists():
        with open(pagl_papl_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expr = row["expr"]
                if expr in ["pagL<6,8,2,4>", "papL<2,8,6,2,4>"]:
                    results[expr] = {
                        "name": "pagL" if "pagL" in expr else "papL",
                        "expr": expr,
                        "ipc": float(row["ipc"]),
                        "mpi": float(row["mpki"]) / 10.0,
                        "epi": float(row["epi"]),
                        "vfs": float(row["vfs"]),
                    }

    # Read Bi-Mode_L
    if bimodell_csv.exists():
        with open(bimodell_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expr = row["expr"]
                if expr == "bimodeL<8,10,8,2,4>":
                    results[expr] = {
                        "name": "bimodeL",
                        "expr": expr,
                        "ipc": float(row["ipc"]),
                        "mpi": float(row["mpki"]) / 10.0,
                        "epi": float(row["epi"]),
                        "vfs": float(row["vfs"]),
                    }

    # Verify and use fallbacks if missing
    required = [
        "gagL<6,2,4>",
        "gapL<2,4,2,4>",
        "pagL<6,8,2,4>",
        "papL<2,8,6,2,4>",
        "bimodeL<8,10,8,2,4>",
    ]
    missing = [r for r in required if r not in results]
    if missing:
        print(f"Warning: Missing sweep data for {missing}. Using hardcoded fallbacks.")
        fallback = {
            "gagL<6,2,4>": {
                "name": "gagL",
                "expr": "gagL<6,2,4>",
                "ipc": 5.0664,
                "mpi": 0.8602,
                "epi": 87.0,
                "vfs": 0.7765,
            },
            "gapL<2,4,2,4>": {
                "name": "gapL",
                "expr": "gapL<2,4,2,4>",
                "ipc": 5.0864,
                "mpi": 0.7844,
                "epi": 87.0,
                "vfs": 0.7937,
            },
            "pagL<6,8,2,4>": {
                "name": "pagL",
                "expr": "pagL<6,8,2,4>",
                "ipc": 2.4312,
                "mpi": 1.0664,
                "epi": 156.0,
                "vfs": 0.4781,
            },
            "papL<2,8,6,2,4>": {
                "name": "papL",
                "expr": "papL<2,8,6,2,4>",
                "ipc": 2.5489,
                "mpi": 0.7894,
                "epi": 151.0,
                "vfs": 0.5197,
            },
            "bimodeL<8,10,8,2,4>": {
                "name": "bimodeL",
                "expr": "bimodeL<8,10,8,2,4>",
                "ipc": 4.7450,
                "mpi": 0.6882,
                "epi": 267.0,
                "vfs": 0.7828,
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
            **results["gagL<6,2,4>"],
            "is_baseline": False,
            "name": f"gagL\n{results['gagL<6,2,4>']['expr']}",
        },
        {
            **results["gapL<2,4,2,4>"],
            "is_baseline": False,
            "name": f"gapL\n{results['gapL<2,4,2,4>']['expr']}",
        },
        {
            **results["pagL<6,8,2,4>"],
            "is_baseline": False,
            "name": f"pagL\n{results['pagL<6,8,2,4>']['expr']}",
        },
        {
            **results["papL<2,8,6,2,4>"],
            "is_baseline": False,
            "name": f"papL\n{results['papL<2,8,6,2,4>']['expr']}",
        },
        {
            **results["bimodeL<8,10,8,2,4>"],
            "is_baseline": False,
            "name": f"bimodeL\n{results['bimodeL<8,10,8,2,4>']['expr']}",
        },
    ]

    labels = [r["name"] for r in comparison_list]
    mpi_vals = [r["mpi"] for r in comparison_list]
    ipc_vals = [r["ipc"] for r in comparison_list]
    epi_vals = [r["epi"] for r in comparison_list]
    vfs_vals = [r["vfs"] if r["expr"] != "reference" else 0.0 for r in comparison_list]

    # Color coding
    colors = ["#7f7f7f", "#4A90E2", "#50E3C2", "#F5A623", "#E284B3", "#A890E2"]

    # Create 2x2 grid of plots
    fig, axs = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(
        "Best-of-Class Superscalar (Block) Predictors Comparison",
        fontsize=18,
        fontweight="bold",
        y=0.98,
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
    style_bar_axis(ax2, "Instructions Per Cycle (Fetch Width = 16)", "IPC")
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
    plot_path = out_dir / "best_five_comparisonL.png"
    plt.savefig(plot_path, dpi=150)
    print(f"Saved comparison plot: {plot_path}")
    plt.close()


if __name__ == "__main__":
    main()
