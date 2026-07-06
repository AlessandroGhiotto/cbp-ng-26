# CBP-NG Trace Dataset Exploratory Data Analysis (EDA)

This document profiles the branch characteristics of the 168 trace dataset and shows how the 12 evaluation traces were selected to represent the boundaries of the workload space.

The complete list of all 168 trace statistics is stored at:
📂 [trace_characteristics.csv](file:///home/ghi/Documents/HPC-PoliMi/2-ACA/cbp-ng-26/profiling/outputs/trace_characteristics.csv)

---

## 1. Trace Dataset Distribution Statistics (168 Traces)

The workload behaviors across the 168 traces show a highly diverse program spectrum:

| Metric                                     |  Min  | 25% Quartile | Median | 75% Quartile |  Max   |
| :----------------------------------------- | :---: | :----------: | :----: | :----------: | :----: |
| **Branch Density** (branches/instructions) | 1.51% |    15.38%    | 18.86% |    20.68%    | 33.32% |
| **Conditional Taken Rate**                 | 6.46% |    33.24%    | 39.65% |    45.80%    | 99.23% |
| **Backward Cond Branch Rate**              | 0.47% |    10.64%    | 14.87% |    23.05%    | 79.68% |
| **Unique Conditional Branch PCs**          |  40   |     568      | 1,554  |    10,422    | 66,766 |

### Key Observations:

- **Footprint Variability**: The code size ranges from tiny kernels with only **40** static conditional branches to complex modern software (e.g. Node.js, Web, SPEC) with up to **66,766** static branches, putting extreme pressure on branch predictor capacity and aliasing mitigation.
- **Taken Rates**: While the median taken rate sits at **39.65%**, some traces are highly biased: `compress_44` has a taken rate of **99.23%**, while `web_99` is heavily not-taken biased at **6.46%**.

---

## 2. Selected Workloads branch Characteristics

Here is the detailed EDA profile of the 12 traces selected for the predictor evaluations:

| Trace Name                  | Instructions | Br Density | Taken Rate | Loop/Back Rate | Uncond Rate | Indirect Rate | Unique Cond PCs | Selection Reason / Workload Type                               |
| :-------------------------- | :----------: | :--------: | :--------: | :------------: | :---------: | :-----------: | :-------------: | :------------------------------------------------------------- |
| `fp_28`                     |    39.0M     |   1.51%    |   86.38%   |     79.68%     |    0.71%    |     0.02%     |       40        | **Min Branch Density / Min PCs**: Floating Point / tight loops |
| `nodejs-misc-util_7039`     |    21.0M     |   33.32%   |   33.33%   |     33.33%     |    0.02%    |     0.01%     |       274       | **Max Branch Density**: Node.js helper utility                 |
| `compress_44`               |    40.0M     |   24.77%   |   99.23%   |     49.59%     |    0.21%    |     0.02%     |       382       | **Max Taken Rate**: Data compression stream                    |
| `web_99`                    |    39.0M     |   29.04%   |   6.46%    |     2.55%      |   24.54%    |     0.58%     |      1,080      | **Min Taken Rate**: Web application workload                   |
| `web_13`                    |    39.0M     |   16.47%   |   31.04%   |     17.49%     |   25.24%    |     12.00%    |     66,766      | **Max Unique PCs**: High-footprint Web server                  |
| `infra_32`                  |    39.0M     |   23.61%   |   10.59%   |     0.47%      |   26.09%    |     12.88%    |       306       | **Min Backward Cond Branch Rate**: Infrastructure framework    |
| `tomcat-wrk2-panel.3289_0`  |    21.1M     |   17.77%   |   54.14%   |     7.26%      |   37.45%    |     27.21%    |      6,012      | **Max Indirect Branch Rate**: Java Servlet/Web Server          |
| `int_48`                    |    39.0M     |   16.86%   |   39.23%   |     32.71%     |    3.87%    |     0.00%     |       538       | **Min Indirect Branch Rate**: Integer kernel workload          |
| `505-mcf-1_14364`           |    21.5M     |   11.63%   |   39.65%   |     23.28%     |    6.92%    |     0.03%     |       301       | **Median Taken Rate**: SPEC CPU 2017 MCF                       |
| `compress_47`               |    40.0M     |   13.27%   |   39.65%   |     28.70%     |    7.67%    |     1.20%     |      1,566      | **Median unique PCs**: Data compression kernel                 |
| `int_210`                   |    39.0M     |   15.38%   |   41.85%   |     17.89%     |   15.45%    |     4.04%     |      1,170      | **Median characteristics**: Integer execution kernel           |
| `java16-specjbb-4k.23837_0` |    21.0M     |   13.55%   |   43.03%   |     14.01%     |   23.95%    |     10.25%    |       493       | **Representative Java**: SPECjbb2015 transaction engine        |
