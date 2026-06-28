# Branch Predictors Memory Footprint Analysis

This document provides a systematic analysis and calculation of the memory requirements for the custom branch predictors located in predictors/our_predictors.

---

## Memory Footprint Comparison Table (Default Parameters)

| Predictor | Default Parameters | GHT / GHR Size | PHT Size | Total Size (in bits) | Total Size (in Bytes) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| gag | BHR_B = 8, CTR_B = 2 | 8 bits *(GHR Register)* | 512 bits | 520 bits | **65.0 B** *(64 B RAM only)* |
| gagL | BHR_B = 8, CTR_B = 2, LINE_B = 4 | 8 bits *(GHR Register)* | 8,192 bits | 8,200 bits | **1,025.0 B** *(1,024 B RAM only)* |
| gap | BHR_B = 4, PC_B = 4, CTR_B = 2 | 4 bits *(GHR Register)* | 512 bits | 516 bits | **64.5 B** *(64 B RAM only)* |
| gapL | BHR_B = 8, PC_B = 4, CTR_B = 2, LINE_B = 4 | 8 bits *(GHR Register)* | 131,072 bits | 131,080 bits | **16,385.0 B** *(16,384 B RAM only)* |
| gshare | BHR_B = 8, PC_B = 10, CTR_B = 2 | 8 bits *(GHR Register)* | 2,048 bits | 2,056 bits | **257.0 B** *(256 B RAM only)* |
| lxor | LOG_GHT = 10, HIST_BITS = 8 | 8,192 bits *(GHT Table)* | 131,072 bits | 139,264 bits | **17,408.0 B** *(17.0 KB)* |
| pag | BHR_B = 8, PC_B = 10, CTR_B = 2 | 8,192 bits *(GHT Table)* | 512 bits | 8,704 bits | **1,088.0 B** *(1.06 KB)* |
| pagL | BHR_B = 8, PC_B = 10, CTR_B = 2, LINE_B = 4 | 8,192 bits *(GHT Table)* | 8,192 bits | 16,384 bits | **2,048.0 B** *(2.0 KB)* |
| pap | BHR_B = 8, PC_B1 = 10, PC_B2 = 4, CTR_B = 2 | 8,192 bits *(GHT Table)* | 8,192 bits | 16,384 bits | **2,048.0 B** *(2.0 KB)* |
| papL | BHR_B = 8, PC_B1 = 10, PC_B2 = 4, CTR_B = 2, LINE_B = 4 | 8,192 bits *(GHT Table)* | 131,072 bits | 139,264 bits | **17,408.0 B** *(17.0 KB)* |

---

## Predictor Memory Usage Comments & Analysis

### 1. gag & gagL
* **GHR/GHT**: These predictors do not have a physical GHT (Global History Table) in RAM. They keep track of branch history in a single global history register (**GHR**) of **8 bits** (`bhr`).
* **PHT**:
  * `gag`: $2^8 = 256$ entries $\times$ 2 bits = **512 bits (64 B)**.
  * `gagL`: $2^8 = 256$ entries $\times$ 16 counters $\times$ 2 bits = **8,192 bits (1,024 B)**.
* **Analysis**: This is the most basic global predictor. The memory footprint is extremely small (65 B for standard, 1 KB for line-based `gagL`). However, it suffers from heavy aliasing and poor accuracy because it does not include PC address bits in its PHT indexing.

### 2. gap & gapL
* **GHR/GHT**: Only uses a global history register (**GHR**) of **4 bits** for `gap` and **8 bits** for `gapL`. No physical GHT table is present.
* **PHT**:
  * `gap`: Indexed by concatenating 4 bits of PC and 4 bits of BHR ($2^{8} = 256$ entries $\times$ 2 bits) = **512 bits (64 B)**.
  * `gapL`: Indexed by concatenating 4 bits of PC and 8 bits of BHR ($2^{12} = 4,096$ entries $\times$ 16 counters $\times$ 2 bits) = **131,072 bits (16,384 B)**.
* **Analysis**: Incorporating PC bits (address sensitivity) significantly reduces conflict aliasing compared to GAG. The standard version requires only 64 B of RAM, whereas the block-based `gapL` grows to 16 KB due to the deeper address space and storing 16 counters per PHT row (LINE_B = 4).

### 3. gshare
* **GHR/GHT**: Single global history register (**GHR**) of **8 bits** (`bhr`).
* **PHT**: $2^{10} = 1,024$ entries $\times$ 2 bits = **2,048 bits (256 B)**.
* **Analysis**: By XORing the PC (10 bits) and the global history (8 bits), it indexes a 256 B PHT. This design allows indexing a wider table (1,024 entries) with few history bits, reducing conflict aliasing at a very low memory cost (257 B total).

### 4. lxor
* **GHT (Local History Table)**: Table of local branch histories indexed by PC: $2^{10} = 1,024$ entries $\times$ 8 bits = **8,192 bits (1,024 B)**.
* **NHT (Neutral / Next History Index)**: This design does not instantiate a physical NHT RAM. Instead, it defines a temporary logic register `nht_index` of **8 bits** (`HIST_BITS`) that holds the history retrieved from the GHT (`nht_index = local_history`). The final index for the PHT is formed by concatenating `nht_index` with its bitwise complement `ctr_index` (`~local_history`).
* **PHT**: $2^{16} = 65,536$ entries $\times$ 2 bits = **131,072 bits (16,384 B)**.
* **Analysis**: Consumes **17 KB** of RAM. Tracking local histories per static branch PC makes it highly accurate for branches with complex periodic behaviors, though concatenating the history and its complement makes the PHT quite large (65,536 entries, 16 KB).

### 5. pag & pagL
* **GHT (Local History Table)**: $2^{10} = 1,024$ entries $\times$ 8 bits = **8,192 bits (1,024 B)**.
* **PHT**:
  * `pag`: $2^8 = 256$ entries $\times$ 2 bits = **512 bits (64 B)**.
  * `pagL`: $2^8 = 256$ entries $\times$ 16 counters $\times$ 2 bits = **8,192 bits (1,024 B)**.
* **Analysis**: A two-level local predictor using local history to index a global PHT. In the standard `pag` model, the PHT is very small (64 B), which creates a major collision bottleneck. The block version `pagL` balances this by allocating 1 KB for GHT and 1 KB for PHT (2 KB total).

### 6. pap & papL
* **GHT (Local History Table)**: $2^{10} = 1,024$ entries $\times$ 8 bits = **8,192 bits (1,024 B)**.
* **PHT**:
  * `pap`: $2^{8+4} = 4,096$ entries $\times$ 2 bits = **8,192 bits (1,024 B)**.
  * `papL`: $2^{8+4} = 4,096$ entries $\times$ 16 counters $\times$ 2 bits = **131,072 bits (16,384 B)**.
* **Analysis**: Compared to PAG, PAP incorporates PC bits when indexing the PHT, logically dividing the PHT among addresses. This eliminates most conflict aliasing. It costs 2 KB for `pap` and 17 KB for `papL`. It is one of the most accurate yet memory-intensive designs.
