# Design and Optimization of a High-Performance and Energy-Efficient Branch Predictor in HARCOM

### Politecnico di Milano — MSc in HPC Engineering

- **Authors:** Roberto Di Lauro, Alessandro Ghiotto
- **Advisors:** Marco Ronzani (PHD), Prof. Cristina Silvano
- **Course:** High-Performance Computing Engineering

---

## Project Overview

This repository contains the work done for the advanced computer architecture project on branch prediction. We evaluate the performance, energy, and latency trade-offs of various branch prediction algorithms under strict hardware budget constraints (**8 KB** and **16 KB**) using the **HARCOM** (Hardware Complexity) library.

The project covers a comparative analysis of classic branch predictors alongside block-based (line-wide) extensions, culminating in the proposal of three custom **TAGE** variants designed to optimize branch prediction for both latency and energy efficiency.

### Key Contributions & Insights

1. **Comparative Study:** Implemented and evaluated classic global-history-based models (Gshare, GAG, GAP), local-history-based models (PAG, PAP), and advanced models (Bi-Mode, TAGE, Perceptron).
2. **Block-level vs. Scalar Predictors:** Moving from scalar prediction (one instruction/cycle) to block-level prediction (line-wide prediction up to 16 instructions/cycle using `predict1/2` and `reuse_predict1/2` interfaces) achieves a massive IPC improvement (up to 3.0x–4.85x speedup) and nearly halves the energy consumption (EPI) by fetching subsequent predictions from low-power registers rather than executing sequential SRAM reads.
3. **TAGE Optimization Proposals:**
   - **TAGE bimode:** Replaces the bimodal base predictor with a Bi-Mode predictor to increase accuracy. However, under tight 8KB/16KB budgets, the tables consumed too much storage, degrading TAGE tagged table capacity and increasing mispredictions.
   - **TAGE bias:** Introduces a small, dedicated sequential bias table as a first-level filter. Strongly biased branches skip the bimodal/tagged updates, reducing EPI but introducing a Stage 1 latency bottleneck (increasing Stage 1 from 1 to 2 cycles under HARCOM timing rules).
   - **TAGE sat (Our Best Design):** Introduces a saturation-based bypass scheme using the existing bimodal base table counters. Fully saturated counters bypass the Stage 2 TAGE tagged RAM lookups. This eliminates Stage 2 read latency, achieves the highest average IPC (4.85), and reduces EPI by **14.6%** (16KB) and **21.3%** (8KB) compared to baseline TAGE.

---

## Repository Guide

Below is a map of the key directories and custom components developed for this project.

### 1. Implemented Predictors

All custom-implemented predictors are located in the [predictors/our_predictors](predictors/our_predictors) folder. Everything outside this subdirectory was part of the original simulator workspace.

- **Scalar Predictors:**
  - [bimode.hpp](predictors/our_predictors/bimode.hpp) — Classic Bi-Mode branch predictor.
  - [bimode_singleram.hpp](predictors/our_predictors/bimode_singleram.hpp) — Bi-Mode optimized to share a single RAM.
  - [gag.hpp](predictors/our_predictors/gag.hpp) — Global history, Global PHT.
  - [gap.hpp](predictors/our_predictors/gap.hpp) — Global history, Per-address PHT.
  - [gshare.hpp](predictors/our_predictors/gshare.hpp) — Baseline Gshare.
  - [lxor.hpp](predictors/our_predictors/lxor.hpp) — Local history XORed with PC.
  - [pag.hpp](predictors/our_predictors/pag.hpp) — Local history, Global PHT.
  - [pap.hpp](predictors/our_predictors/pap.hpp) — Local history, Per-address PHT.
  - [perceptron_simple.hpp](predictors/our_predictors/perceptron_simple.hpp) — A simple perceptron-based model.
  - [tage_simple.hpp](predictors/our_predictors/tage_simple.hpp) — Simplified TAGE implementation.
  - [tage_simple_u.hpp](predictors/our_predictors/tage_simple_u.hpp) — Simplified TAGE with usefulness (`u`) tracking bits.
- **Block/Line-based Predictors (`*L.hpp`):**
  - Line-wide counterparts to the above, designed to predict entire instruction cache lines using the HARCOM block reuse interface:
  - [bimodeL.hpp](predictors/our_predictors/bimodeL.hpp), [gagL.hpp](predictors/our_predictors/gagL.hpp), [gapL.hpp](predictors/our_predictors/gapL.hpp), [gshareL.hpp](predictors/our_predictors/gshareL.hpp), [lxorL.hpp](predictors/our_predictors/lxorL.hpp), [pagL.hpp](predictors/our_predictors/pagL.hpp), [papL.hpp](predictors/our_predictors/papL.hpp), [perceptron_simpleL.hpp](predictors/our_predictors/perceptron_simpleL.hpp), [perceptron_simpleL_banks.hpp](predictors/our_predictors/perceptron_simpleL_banks.hpp), [tage_simpleL.hpp](predictors/our_predictors/tage_simpleL.hpp), [tage_simple_uL.hpp](predictors/our_predictors/tage_simple_uL.hpp).
- **Our Proposed TAGE Optimizations:**
  - [tage_bimodeL.hpp](predictors/our_predictors/tage_bimodeL.hpp) — TAGE with a Bi-Mode base predictor.
  - [tage_biasL.hpp](predictors/our_predictors/tage_biasL.hpp) — TAGE with a first-level sequential bias filtering table.
  - [tage_simple_satL.hpp](predictors/our_predictors/tage_simple_satL.hpp) — TAGE with saturation-based tagged table bypassing (Best design).

All of these are registered and included inside [our_predictors.hpp](predictors/our_predictors/our_predictors.hpp) and linked into the simulator flow through [branch_predictor.hpp](branch_predictor.hpp).

### 2. Data Profiling & Simulation Analysis

The [profiling](profiling) directory contains scripts, outputs, and notebooks used to run parameter sweeps, analyze trace statistics, and generate comparison reports:

- **Analysis Notebook:** [CBP_Predictor_Analysis.ipynb](profiling/CBP_Predictor_Analysis.ipynb) analyzes performance and energy metrics across runs.
- **Comparison Report:** [Full_Comparison_Report.md](profiling/Full_Comparison_Report.md) aggregates VFS, MPKI, and EPI results for all configurations across a representative suite of 12 traces under fixed 8KB and 16KB hardware budgets.
- **Sweeps & Analysis Scripts:** Located in [profiling/scripts/](profiling/scripts).
- **Plotting & CSV Outputs:** Located in [profiling/outputs/](profiling/outputs).

### 3. Reports & Presentation Slides

- **Project Report:** Located in [report/](report). The PDF version is available at [executive_summary.pdf](report/executive_summary.pdf) (LaTeX sources in [executive_summary.tex](report/executive_summary.tex)).
- **Project Presentation:** Located in [presentation/](presentation). The PDF slide deck is available at [presentation.pdf](presentation/presentation.pdf) (LaTeX sources in [presentation.tex](presentation/presentation.tex)).

---

## Compiling & Running Our Predictors

To compile any of our custom predictors:

```bash
./compile cbp -DPREDICTOR="<predictor_class_name><<template parameters>>"
```

### Examples:

- Compile our best block-based proposal (TAGE with saturation bypassing):
  ```bash
  ./compile cbp -DPREDICTOR="tage_simple_satL<>"
  ```
- Compile a simple block-based Gshare:
  ```bash
  ./compile cbp -DPREDICTOR="gshare_simpleL<8>"
  ```
- Compile a scalar Bi-Mode predictor:
  ```bash
  ./compile cbp -DPREDICTOR="bimode_simple<8,6>"
  ```

Once compiled, you can run the simulator on a trace (e.g., using the training traces):

```bash
./run ./cbp ./gcc_test_trace.gz
```

Or run all traces and pipe the output to `predictor_metrics.py` and `vfs.py` to evaluate the VFS score:

```bash
./predictor_metrics.py OUTDIR | ./vfs.py
```

---

---

## CBP-NG Championship Documentation (Original Simulator README)

Welcome to the repository for the Next-Generation Championship in Branch
Prediction! This championship aims to foster innovation in branch prediction by
encouraging the development of branch prediction algorithms achieving high
prediction accuracy while minimizing power consumption.

Below, you will find information designed to help you get started developing
your winning predictor design. Please see [the competition
website](https://cbp-ng.bpchamp.com) for additional information about the
championship, including how to join the mailing list for announcements and
conversation with the organizers and other participants.

### Writing a Predictor

#### HARCOM Language

Predictors in the CBP-NG simulator are written using the HARCOM (HARdware
COMplexity) C++ library. Using this library allows CBP-NG to model the energy,
latency, and area costs of predictor designs.

HARCOM tracks these costs using special C++ types representing `reg`isters,
SRAM `arr`ays, and transient intermediate `val`ues. These types use operator
overloading and additional methods to allow you to implement array accesses and
needed hardware logic. These types are opaque, meaning your predictor cannot
(directly) read or write their values. For example, instead of being able to
use typical C++ 'if-else' statements, your predictor will instead need to
`select` (i.e. mux) between several opaque `val`'s based on another opaque
`val`.

Please review the full HARCOM manual, [available in the CBP-NG
repository](https://github.com/AmpereComputing/cbp-ng/raw/refs/heads/main/docs/harcom.pdf),
for a more details about how this library works and how to use it.

#### Simulator Interface

The simulator interface is designed to balance flexibility of predictor design
with faithfulness to the typical external design constraints placed on branch
predictors.

The `predictor` interface your predictor must implement is specified in
[`cbp.hpp`](https://github.com/AmpereComputing/cbp-ng/tree/main/cbp.hpp). There
are code comments alongside the interface describing it, and a brief
explanation of it also follows:

![predictor interface flowchart](/docs/interface-flowchart.svg)

There are two main 'levels' of branch prediction your predictor may implement -
levels 1 and 2. This interface structure is intended to support prediction
pipelining (for example, with a fast prediction providing throughput, but with
a slower predictor correcting the prediction if desired). The simulator calls
different methods on your predictor for each level, as described in the next
paragraph. Note that you may provide simple (zero-latency) implementations of
either level if you desire a single prediction level.

Your predictor is also responsible for choosing its own prediction block length
(the number of instructions predicted at one time). At the beginning of a
block, the simulator will call your predictor's `predict1()` (for level 1) and
`predict2()` (level 2) methods. These methods are responsible for returning the
prediction for the first instruction at each corresponding prediction level,
but they may additionally call a `reuse_prediction()` callback with a value of
`1` to specify that the next instruction be predicted by the simulator calling
`reuse_predict1()` and `reuse_predict2()` instead of `predict1()` and
`predict2()`. This prediction block will continue (the "reuse\_" methods will be
called) until either you call `reuse_prediction()` with a `0`, a level-2
misprediction occurs, or a taken branch is encountered, at which point
`predict1()` and `predict2()` will be called once more.

The separation of these two sets of methods allows your predictor to both use
different logic for the first instruction in a given block (i.e. an initial
array lookup) than it does for subsequent instructions, and to directly control
the length of a block.

#### Example Predictors

Sometimes an example is worth much more than an explanation. To that end,
example predictors are available in [the `./predictors` subdirectory of the
CBP-NG
repository](https://github.com/AmpereComputing/cbp-ng/tree/main/predictors).
These include bimodal, gshare, perceptron, and TAGE reference predictors.

#### Common Utilities

Different predictors may re-use many of the same components. To help provide
some basic building blocks, we've gathered several potentially-common
components together into
[`predictors/common.hpp`](https://github.com/AmpereComputing/cbp-ng/blob/main/predictors/common.hpp)
in the CBP-NG repository. These common bits include helper functions for
updating saturating counters, tracking and "folding" branch history, and
reading/writing a banked RAM. Many of the example predictors in the same
directory provide examples of how to use them.

### Predictor Scoring

The competition score will take into account prediction accuracy,
energy-efficiency, and implementation complexity as part of a
"Voltage-Frequency-Scaled Speedup" (a.k.a. VFS) score. Pierre Michaud has
written [a paper available on the competition's github
repository](https://github.com/AmpereComputing/cbp-ng/blob/main/docs/vfs.pdf)
explaining this scoring to help participants gain intuition for it.

Though we have attempted to ensure this scoring mechanism is aligned with
real-world design constraints and you are heavily encouraged to use your
creativity in maximizing it, submissions which optimize it in an unrealistic
way or which undermine the intention of the scoring will not be considered. All
submissions will be judged in the spirit of the competition: pushing the
boundaries of energy-efficient and high-performance branch prediction.

### Building and Running Predictors

#### Requirements

The CBP-NG Simulator and HARCOM require either GCC version 12 or later or Clang
version 19 or later.

The simulator and HARCOM are tested on Linux (Ubuntu), MacOS, and Windows
(Ubuntu-based WSL).

If you are familiar with
[`nix-shell`](https://nix.dev/manual/nix/2.18/command-ref/nix-shell), this
repository contains a shell.nix containing the simulator's dependencies.

#### Compiling

Though you are welcome to compile your predictor however you wish, the
simulator repository contains a `./compile` helper script. To compile the
default predictor (i.e. that which `branch_predictor.hpp` sets the `PREDICTOR`
preprocessor macro to - `tage<>` in the main repository):

```console
./compile cbp
```

To compile a specific predictor, in this case gshare:

```console
./compile cbp -DPREDICTOR="gshare<>"
```

To add your own predictor named "my_predictor", it is suggested to add a new
file (for example, `./predictors/my_predictor.hpp`) to the repository
containing a class named `my_predictor` which inherits from `predictor`,
include your newly-created header file at the top of `branch_predictor.hpp`,
and then compile as:

```console
./compile cbp -DPREDICTOR="my_predictor<>"
```

There is also a simple CMakeLists.txt file checked in if you prefer to use
cmake.

#### Simulating

Assuming your compiled binary is named `./cbp`, you can simulate one trace with
1M instructions of warmup and up to 40M instructions of measurement like:

```console
./cbp ./gcc_test_trace.gz test 1000000 40000000
```

If you are planning to look at the simulator output directly, you can pass
`--format human` when running to output the simulation results with more
human-readable formatting.

You may also use the run script like:

```console
./run ./cbp ./gcc_test_trace.gz
```

Note: the simulation output per traces is one row of CSV, with fields in the
order: (1) trace name, (2) instructions, (3) branches, (4) conditional
branches, (5) blocks, (6) extra cycles, (7) P1/P2 divergences, (8) P1/P2
divergences coinciding with block end, (9) P2 mispredictions, (10) P1 latency
(cycles), (11) P2 latency (cycles), (12) dynamic energy per instruction (fJ)

There is also a `run_all` script which may help simulate many traces at once
using the same binary. For example, to simulate all traces in the 'traces'
directory:

```console
mkdir OUTDIR
./run_all ./cbp ./traces OUTDIR
```

#### Score Calculations

There are several scripts intended to help calculate scores and make sense of
the provided simulator metrics.

Once you have run a set of traces, you can compute ratios between statistics
using the `ratio` script. For example, the number of mispredictions per
instruction:

```console
./ratio 2 9 OUTDIR
```

The `predictor_metrics.py` script will compute the average IPC<sub>cbp</sub>,
CPI<sub>cbp</sub>, EPI<sub>cbp</sub> (as defined for VFS scoring, not their
usual meanings), as well as other metrics such as average counts of conditional
branches and mispredictions, across a full set of traces:

```console
./predictor_metrics.py OUTDIR
```

The output of `predictor_metrics.py` can be further used to compute the VFS
score for a set of runs via:

```console
./predictor_metrics.py OUTDIR | ./vfs.py
```

Or, if you would like to play around with the VFS score for arbitrary
IPC<sub>cbp</sub>, CPI<sub>cbp</sub>, and EPI<sub>cbp</sub> values (as defined
for VFS scoring), you may pass those (in that order) like:

```console
./vfs.py 7,0.03,1500
```

#### Reference Predictor

The "reference" TAGE-SC-L predictor (from CBP 2025) was used to help us set the
prediction accuracy portion of the VFS score's reference predictor. It is
contained in `reference.cpp` and `seznec_cbp2025.h`. Note: this predictor is
not written using the CBP-NG simulator and therefore provides only prediction
accuracy (no prediction latency or energy usage). You may use it for your
research, but please be aware that all submitted predictors must be implemented
using the predictor interface detailed above, unlike the reference predictor!

To compile the TAGE-SC-L reference predictor:

```console
g++ -std=c++20 -o reference -O3 reference.cpp -lz
```

To run one trace:

```console
./reference ./gcc_test_trace.gz test 1000000 40000000
```

or

```console
./run ./reference ./gcc_test_trace.gz
```

To simulate all traces in the 'traces' directory:

```console
./run_all ./reference ./traces OUTDIR
```

### 'Training' Traces

You are encouraged to use the official set of 168 CBP-NG training traces,
available for download at
[https://drive.google.com/file/d/1kLKn_iKVBP-YxRpC4WiCy-ca-agU0BFG/view](https://drive.google.com/file/d/1kLKn_iKVBP-YxRpC4WiCy-ca-agU0BFG/view),
to develop your predictor designs. Once downloaded, you may un-compress and
extract the traces using the `tar xf cbp-ng_training_traces.tar.gz` command.
You can then point the CBP-NG simulator run script at this resulting directory
when running your simulations (see `./run_all` above for how to run multiple
traces). Though you are welcome to use other traces, we strongly recommend you
primarily use our provided training traces because we have gone to great
lengths to ensure they are representative of the set we will use for final
scoring.
