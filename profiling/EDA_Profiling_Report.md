# CBP-NG Predictor Exploratory Data Analysis & Profiling Report

This report summarizes trace workload characterization and predictor performance analysis under fixed hardware budgets (8KB and 16KB).

## 1. Trace Workload Characteristics

We characterized the instruction mix and branch behaviors across the traces. Here are the key statistics:

| Trace Name | Insts | Branches | Cond Br | Br Density | Cond Taken Rate | Loop Backwards Rate | Unique Cond PCs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| gcc_test | 2,004,998 | 396,599 | 334,545 | 19.78% | 56.35% | 37.72% | 447 |

