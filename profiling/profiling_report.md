# Structured Performance Profiling Report

This folder now has a single reproducible entry point for the full profiling workflow:

```bash
./profiling/run_profiling_suite.py --warmup 1000000 --measure 2005000
```

That command runs the family sweeps for similar predictors, the block-based counterparts, the fixed-budget 8KB and 16KB study, and the summary plot generation. The cached outputs are written under [profiling/outputs](profiling/outputs), including [profiling_suite_summary.md](profiling/outputs/profiling_suite_summary.md) and [structured_profiling_results.csv](profiling/outputs/structured_profiling_results.csv).

The predictor implementations used in the study live in [predictors/our_predictors](predictors/our_predictors). The fixed-budget comparison in this report evaluates those designs against two championship baselines:

1. **Software Reference (CBP2025)**: The official non-HARCOM TAGE-based simulation baseline.
2. **Championship TAGE**: The default hardware-modeled TAGE baseline included in the repository (budget about 35KB).

The structured 8KB vs 16KB study uses [structured_profiling.py](profiling/structured_profiling.py) on [gcc_test_trace.gz](../gcc_test_trace.gz) with a 1M instruction warmup and a 2.005M instruction measurement window.

---

## 📊 Summary of Results

Below is the complete profiling data ordered by budget size and predictor class:

| Budget   | Predictor            | Configuration / Template       | Class    | MPKI   | IPC   | EPI (fJ) | VFS Score  | Size (Bits) |
| :------- | :------------------- | :----------------------------- | :------- | :----- | :---- | :------- | :--------- | :---------- |
| **S/W**  | **Reference**        | `reference`                    | Baseline | 4.910  | 0.987 | 0.0      | 0.0000     | 0           |
| **35KB** | **Default TAGE**     | `tage<>`                       | Baseline | 6.198  | 4.644 | 1542.0   | **0.7653** | 286,720     |
| **8KB**  | **gagL**             | `gagL<11,2,4>`                 | Block    | 11.630 | 2.556 | 146.0    | **0.4881** | 65,536      |
| **8KB**  | **gapL**             | `gapL<6,5,2,4>`                | Block    | 12.992 | 2.521 | 149.0    | 0.4725     | 65,536      |
| **8KB**  | **bimodeL**          | `bimodeL<10,10,9,2,4>`         | Block    | 11.355 | 2.462 | 458.0    | 0.4715     | 65,536      |
| **8KB**  | **papL**             | `papL<8,12,2,2,4>`             | Block    | 14.074 | 2.236 | 299.0    | 0.4232     | 65,536      |
| **8KB**  | **pagL**             | `pagL<10,11,2,4>`              | Block    | 15.114 | 2.201 | 422.0    | 0.4101     | 53,248      |
| **8KB**  | **lxor**             | `lxor<12,7>`                   | Scalar   | 13.845 | 0.873 | 616.0    | **0.1919** | 61,440      |
| **8KB**  | **lxor_vibe**        | `lxor_vibe<12,7>`              | Scalar   | 13.845 | 0.797 | 670.0    | 0.1769     | 61,440      |
| **8KB**  | **gap**              | `gap<9,6,2>`                   | Scalar   | 11.741 | 0.495 | 223.0    | 0.1180     | 65,536      |
| **8KB**  | **gshare**           | `gshare_simple<15,15,2>`       | Scalar   | 11.626 | 0.495 | 228.0    | 0.1180     | 65,536      |
| **8KB**  | **gag**              | `gag<15,2>`                    | Scalar   | 11.816 | 0.495 | 223.0    | 0.1180     | 65,536      |
| **8KB**  | **bimode_singleram** | `bimode_singleram<14,12,13,2>` | Scalar   | 11.344 | 0.492 | 582.0    | 0.1164     | 65,536      |
| **8KB**  | **bimode**           | `bimode<14,12,13,2>`           | Scalar   | 11.344 | 0.492 | 601.0    | 0.1164     | 65,536      |
| **8KB**  | **tage_simple**      | `tage_simple<10,16,...>`       | Scalar   | 9.982  | 0.494 | 1594.0   | 0.1159     | 61,440      |
| **8KB**  | **pap**              | `pap<8,12,6,2>`                | Scalar   | 11.286 | 0.485 | 535.0    | 0.1151     | 65,536      |
| **8KB**  | **pag**              | `pag<12,12,2>`                 | Scalar   | 12.169 | 0.483 | 485.0    | 0.1142     | 57,344      |
| **16KB** | **gagL**             | `gagL<12,2,4>`                 | Block    | 11.711 | 2.559 | 181.0    | **0.4872** | 131,072     |
| **16KB** | **bimodeL**          | `bimodeL<11,12,10,2,4>`        | Block    | 11.323 | 2.469 | 501.0    | 0.4720     | 131,072     |
| **16KB** | **gapL**             | `gapL<6,6,2,4>`                | Block    | 12.996 | 2.521 | 185.0    | 0.4718     | 131,072     |
| **16KB** | **papL**             | `papL<8,13,3,2,4>`             | Block    | 12.866 | 1.581 | 321.0    | 0.3283     | 131,072     |
| **16KB** | **pagL**             | `pagL<11,12,2,4>`              | Block    | 14.851 | 1.555 | 346.0    | 0.3163     | 110,592     |
| **16KB** | **lxor**             | `lxor<13,7>`                   | Scalar   | 13.858 | 0.873 | 649.0    | **0.1918** | 90,112      |
| **16KB** | **gap**              | `gap<10,6,2>`                  | Scalar   | 11.467 | 0.495 | 261.0    | 0.1180     | 131,072     |
| **16KB** | **lxor_vibe**        | `lxor_vibe<13,7>`              | Scalar   | 13.858 | 0.797 | 708.0    | 0.1767     | 90,112      |
| **16KB** | **gshare**           | `gshare_simple<16,16,2>`       | Scalar   | 11.978 | 0.495 | 268.0    | 0.1177     | 131,072     |
| **16KB** | **gag**              | `gag<16,2>`                    | Scalar   | 12.082 | 0.495 | 262.0    | 0.1177     | 131,072     |
| **16KB** | **bimode_singleram** | `bimode_singleram<15,12,14,2>` | Scalar   | 11.508 | 0.492 | 569.0    | 0.1164     | 131,072     |
| **16KB** | **bimode**           | `bimode<15,14,14,2>`           | Scalar   | 11.033 | 0.492 | 700.0    | 0.1163     | 131,072     |
| **16KB** | **tage_simple**      | `tage_simple<11,16,...>`       | Scalar   | 9.505  | 0.495 | 2310.0   | 0.1153     | 122,880     |
| **16KB** | **pap**              | `pap<8,13,7,2>`                | Scalar   | 11.555 | 0.485 | 564.0    | 0.1149     | 131,072     |
| **16KB** | **pag**              | `pag<15,12,2>`                 | Scalar   | 12.695 | 0.481 | 649.0    | 0.1133     | 126,976     |

---

## 📈 Visual Scaling Comparison

Below is the plotted visualization of the four primary design space metrics:

![Structured Profiling Plot](structured_profiling.png)

---

## 🔍 Key Insights & Analysis

### 1. 🚀 Scalar vs. Block-Based (Superscalar) Predictors

- **Throughput Dominance**: Block-based (or "Line-wide") predictors (suffix `L`) predict up to 16 instructions per cycle in a single lookup. This allows them to achieve an IPC between **1.55 and 2.56**, whereas standard scalar predictors are strictly limited to an IPC of **~0.49** due to fetch stalls.
- **VFS Score Impact**: Because the VFS score heavily penalizes throughput loss, block-based predictors outscore scalar predictors by up to **4x** (e.g., `gagL` gets a VFS score of **0.4881** vs. `gag`'s **0.1180**).
- **The LXOR Exception**: Among scalar models, `lxor` stands out with an IPC of **0.873** and VFS score of **0.1919** at 8KB. This is because `lxor` is designed to run its first-level prediction at zero latency (predicting not-taken) and performs the table lookup at Level 2, saving pipeline stall cycles.

### 2. ⏳ Hardware Latency Threshold Effects

A highly counter-intuitive finding is that doubling the hardware budget from 8KB to 16KB **degrades** performance for certain models:

- **pagL**: VFS drops from **0.4101** (8KB) to **0.3163** (16KB), and IPC drops from **2.20** to **1.55**.
- **papL**: VFS drops from **0.4232** (8KB) to **0.3283** (16KB), and IPC drops from **2.24** to **1.58**.

**Explanation**:
In HARCOM, the read latency of a RAM is determined by its size. In `pagL` and `papL`, the lookup requires two sequentially dependent RAM reads (the Global History Table read followed by the Pattern History Table read).

- At **8KB** (`pagL<10,11,2,4>`), the lookups take 1.95 and 1.96 cycles, which HARCOM rounds up (`math.ceil`) to **2 cycles** prediction latency.
- At **16KB** (`pagL<11,12,2,4>`), the larger RAM dimensions push the lookup latency to 2.18 and 2.2 cycles, which rounds up to **3 cycles** prediction latency.
  This extra cycle penalty on every branch prediction block introduces pipeline bubbles, reducing throughput and degrading both IPC and VFS. This showcases how **HARCOM models realistic hardware access times, where larger tables are not always better**.

### 3. 🔋 Energy-Accuracy Trade-off

- **bimode_singleram vs. bimode**: By mapping both direction tables into a single RAM block (saving decoders and peripheral area), `bimode_singleram` reduces energy per instruction (EPI) from **601 fJ** to **582 fJ** at 8KB while preserving identical accuracy (11.34 MPKI). This results in a higher VFS score.
- **tage_simple**: While `tage_simple` achieves the best accuracy among our custom scalar models (**9.51 MPKI** at 16KB), its multi-table structure consumes massive energy (**2310 fJ**), which heavily penalizes its VFS score (**0.1153**).

---

## 🛠️ Reproducibility

Use the suite runner for a full refresh:

```bash
./profiling/run_profiling_suite.py --warmup 1000000 --measure 2005000
```

If the CSV outputs already exist and you only want to rebuild the markdown summary and the plots from cached data, run:

```bash
./profiling/run_profiling_suite.py --skip-sim --skip-summary-plots
```

The raw outputs are stored in [profiling/outputs](profiling/outputs), and the fixed-budget structured results are in [structured_profiling_results.csv](profiling/outputs/structured_profiling_results.csv).
