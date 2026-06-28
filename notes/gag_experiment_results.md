# GAG Predictor History Length Experiment

This experiment fixes the PHT size to **1024 entries** (index size = 10 bits, counter size = 2 bits).
We vary the history length (`HIST_B`) from 1 to 16 bits and measure the predictor's accuracy on 1,000,000 instructions of `gcc_test_trace`.

## Configuration

- **PHT Index size**: 10 bits
- **Counter size**: 2 bits
- **Trace**: `gcc_test_trace` (1,000,000 instructions)

## Results

| History Size (bits) | Conditional Branches | Mispredictions | Accuracy (%) |
| :-----------------: | :------------------: | :------------: | :----------: |
|          1          |        158767        |     10785      | **93.207%**  |
|          2          |        158767        |      9924      | **93.749%**  |
|          3          |        158767        |      9953      | **93.731%**  |
|          4          |        158767        |     10135      | **93.616%**  |
|          5          |        158767        |      9911      | **93.758%**  |
|          6          |        158767        |     10196      | **93.578%**  |
|          7          |        158767        |     10871      | **93.153%**  |
|          8          |        158767        |     11219      | **92.934%**  |
|          9          |        158767        |     12093      | **92.383%**  |
|         10          |        158767        |     12895      | **91.878%**  |
|         11          |        158767        |     14648      | **90.774%**  |
|         12          |        158767        |     14480      | **90.880%**  |
|         13          |        158767        |     15431      | **90.281%**  |
|         14          |        158767        |     14011      | **91.175%**  |
|         15          |        158767        |     14317      | **90.982%**  |
|         16          |        158767        |     14397      | **90.932%**  |

### Architectural Analysis

#### 1. The Value of PC-Padding (H < 10)

We see a peak in accuracy at H = 5 bits (93.758%) and very high accuracy from H = 2 to H = 5.

• When H < 10, the PHT index is formed by concatenating the lowest bits of the PC with the global history (e.g., for H = 5, 5 bits of PC and 5 bits of history).
• This introduces address sensitivity (acting like a GAP predictor). Knowing which branch instruction is executing is extremely critical for branch prediction. Combining a short history (2 to 5
bits) with PC bits avoids severe aliasing between different branches that happen to share the same global history patterns.

#### 2. The Pure GAG Bottleneck (H = 10)

At H = 10, the accuracy drops significantly to 91.878% (12,895 mispredictions).

• Here, the PHT is indexed purely by the 10-bit global history register without any PC address bits.
• Because different branches share the same global history register and map to the same PHT entries, they suffer from destructive conflict aliasing (e.g., branch A expecting "Taken" and branch
B expecting "Not-Taken" for the same history pattern, overwriting each other's counters).

#### 3. Long History Folding (H > 10)

For H > 10, the accuracy decreases further, reaching a low of 90.281% at H = 13, and hovering around 90.9% up to H = 16.

• Since we are folding longer histories down to 10 bits using XOR, we still lack address sensitivity (no PC bits are mixed in).
• While longer history lengths can theoretically capture deeper execution paths, folding them into a small 1024-row PHT without address sensitivity causes severe destructive aliasing and XOR-
based collision, leading to poorer results than short histories.

### Summary

For a fixed-size table, address sensitivity is vital. A hybrid index combining branch address bits (PC) with a moderate history length (e.g., 5 PC bits + 5 history bits) performs significantly
better than a pure global history index, even when that history is folded from 16 bits.
