#!/usr/bin/env python3
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Data
models = ["gagL", "gapL", "pagL", "papL", "lxorL", "bimodeL"]
vfs_8kb = [0.4881, 0.4725, 0.4101, 0.4232, 0.4231, 0.4715]
vfs_16kb = [0.4872, 0.4718, 0.3163, 0.3283, 0.3221, 0.4720]

mpki_8kb = [11.63, 12.99, 15.11, 14.07, 14.48, 11.36]
mpki_16kb = [11.71, 13.00, 14.85, 12.87, 14.47, 11.32]

ipc_8kb = [2.56, 2.52, 2.20, 2.24, 2.27, 2.46]
ipc_16kb = [2.56, 2.52, 1.56, 1.58, 1.59, 2.47]

epi_8kb = [146.0, 149.0, 422.0, 299.0, 407.0, 458.0]
epi_16kb = [181.0, 185.0, 346.0, 321.0, 426.0, 501.0]

# Setup plot
fig, axs = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("Block Predictors Comparison: 8KB vs 16KB Storage Budget", fontsize=16, fontweight='bold', y=0.98)
ax1, ax2, ax3, ax4 = axs.flatten()

x = range(len(models))
width = 0.35

def style_plot(ax, title, ylabel):
    ax.set_title(title, fontsize=12, fontweight='bold', pad=8)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(models, fontsize=9)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#cccccc')
    ax.spines['bottom'].set_color('#cccccc')
    ax.grid(axis='y', linestyle=':', alpha=0.6)
    ax.set_axisbelow(True)

# 1. VFS
ax1.bar([i - width/2 for i in x], vfs_8kb, width, label="8KB Budget", color="#4A90E2", edgecolor="#333333", linewidth=0.5)
ax1.bar([i + width/2 for i in x], vfs_16kb, width, label="16KB Budget", color="#50E3C2", edgecolor="#333333", linewidth=0.5)
style_plot(ax1, "VFS Speedup Score (Higher is Better)", "VFS Score")
ax1.set_ylim(0.2, 0.6)
ax1.legend()

# 2. MPKI
ax2.bar([i - width/2 for i in x], mpki_8kb, width, label="8KB Budget", color="#4A90E2", edgecolor="#333333", linewidth=0.5)
ax2.bar([i + width/2 for i in x], mpki_16kb, width, label="16KB Budget", color="#50E3C2", edgecolor="#333333", linewidth=0.5)
style_plot(ax2, "Branch Mispredictions (Lower is Better)", "MPKI")
ax2.set_ylim(0, 18)

# 3. IPC
ax3.bar([i - width/2 for i in x], ipc_8kb, width, label="8KB Budget", color="#4A90E2", edgecolor="#333333", linewidth=0.5)
ax3.bar([i + width/2 for i in x], ipc_16kb, width, label="16KB Budget", color="#50E3C2", edgecolor="#333333", linewidth=0.5)
style_plot(ax3, "Instructions Per Cycle (Higher is Better)", "IPC")
ax3.set_ylim(0, 3.5)

# 4. EPI
ax4.bar([i - width/2 for i in x], epi_8kb, width, label="8KB Budget", color="#4A90E2", edgecolor="#333333", linewidth=0.5)
ax4.bar([i + width/2 for i in x], epi_16kb, width, label="16KB Budget", color="#50E3C2", edgecolor="#333333", linewidth=0.5)
style_plot(ax4, "Energy per Instruction (Lower is Better)", "EPI (fJ)")
ax4.set_ylim(0, 600)

plt.tight_layout(rect=[0, 0, 1, 0.95])
plt.savefig("report/Images/structured_profiling_8kb_16kb.png", dpi=150)
print("Plot saved successfully.")
