# CBP-NG Predictor Exploratory Data Analysis & Profiling Report

This report summarizes trace workload characterization and predictor performance analysis under fixed hardware budgets (8KB and 16KB).

## 1. Trace Workload Characteristics

We characterized the instruction mix and branch behaviors across the traces. Here are the key statistics:

| Trace Name | Insts | Branches | Cond Br | Br Density | Cond Taken Rate | Loop Backwards Rate | Unique Cond PCs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| gcc_test | 1,000,000 | 228,244 | 194,002 | 22.82% | 57.50% | 37.06% | 266 |

## 2. TAGE Variants Comparison

Comparison of standard TAGE, TAGE with utility bits (u), and their block-based counterparts (L) under matched budgets:

| Budget | Predictor Name | Trace Name | MPKI | IPC | VFS Score |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 16KB | tage_simple | gcc_test | 11.1610 | 0.9655 | **0.207928** |
| 16KB | tage_simpleL | gcc_test | 12.9750 | 2.5527 | **0.436601** |
| 16KB | tage_simple_u | gcc_test | 6.9840 | 0.4898 | **0.115791** |
| 16KB | tage_simple_uL | gcc_test | 8.0930 | 2.1302 | **0.415792** |
| 8KB | tage_simple | gcc_test | 11.6320 | 0.9655 | **0.209306** |
| 8KB | tage_simpleL | gcc_test | 12.6130 | 2.6002 | **0.459260** |
| 8KB | tage_simple_u | gcc_test | 7.2810 | 0.4904 | **0.116686** |
| 8KB | tage_simple_uL | gcc_test | 8.5870 | 2.1458 | **0.417267** |

## 3. Perceptron Parameter Sweep

Evaluating Perceptron with different History Lengths (BHR), weights bits (W), and block vs scalar designs:

| Budget | Configuration | Trace Name | MPKI | IPC | VFS Score |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 16KB | perceptronL_PC7_BHR31_W8 | gcc_test | 11.4530 | 0.5436 | **0.124866** |
| 16KB | perceptronL_PC8_BHR15_W8 | gcc_test | 12.5850 | 0.6754 | **0.153154** |
| 16KB | perceptron_PC8_BHR63_W8 | gcc_test | 10.9260 | 0.2484 | **0.059277** |
| 16KB | perceptron_PC9_BHR31_W8 | gcc_test | 11.2420 | 0.3305 | **0.077734** |
| 16KB | perceptron_PC9_BHR41_W6 | gcc_test | 15.2980 | 0.3293 | **0.076588** |
| 16KB | perceptron_PC9_BHR47_W5 | gcc_test | 22.0680 | 0.3275 | **0.074835** |
| 8KB | perceptronL_PC6_BHR31_W8 | gcc_test | 11.7110 | 0.5434 | **0.125061** |
| 8KB | perceptronL_PC7_BHR15_W8 | gcc_test | 12.6350 | 0.6754 | **0.153680** |
| 8KB | perceptron_PC7_BHR63_W8 | gcc_test | 11.0980 | 0.2484 | **0.059446** |
| 8KB | perceptron_PC8_BHR31_W8 | gcc_test | 11.4580 | 0.3305 | **0.078749** |
| 8KB | perceptron_PC8_BHR41_W6 | gcc_test | 15.5330 | 0.3293 | **0.077552** |
| 8KB | perceptron_PC9_BHR15_W8 | gcc_test | 12.3230 | 0.4933 | **0.114994** |

## 4. Predictor Families: Scalar vs Block Prediction

Analyzing the VFS and speedup benefits of block-based (superscalar, LI=16) branch prediction versus scalar designs:

| Budget | Family | Mode | Trace Name | MPKI | IPC | VFS Score |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 16KB | BiMode | Block | gcc_test | 12.7430 | 2.2273 | **0.426448** |
| 16KB | BiMode | Scalar | gcc_test | 12.4370 | 0.4907 | **0.115351** |
| 16KB | GAg | Block | gcc_test | 12.9770 | 2.3148 | **0.443641** |
| 16KB | GAg | Scalar | gcc_test | 13.1750 | 0.4947 | **0.117001** |
| 16KB | GAp | Block | gcc_test | 15.4180 | 2.2718 | **0.421663** |
| 16KB | GAp | Scalar | gcc_test | 12.9230 | 0.4946 | **0.117106** |
| 16KB | PAg | Block | gcc_test | 16.8190 | 1.3837 | **0.281716** |
| 16KB | PAg | Scalar | gcc_test | 14.9810 | 0.4777 | **0.111430** |
| 16KB | PAp | Block | gcc_test | 14.6500 | 1.4064 | **0.292202** |
| 16KB | PAp | Scalar | gcc_test | 13.4310 | 0.4825 | **0.113373** |
| 8KB | BiMode | Block | gcc_test | 12.8810 | 2.2229 | **0.425673** |
| 8KB | BiMode | Scalar | gcc_test | 12.7350 | 0.4908 | **0.115446** |
| 8KB | GAg | Block | gcc_test | 12.8450 | 2.3139 | **0.445214** |
| 8KB | GAg | Scalar | gcc_test | 12.8950 | 0.4947 | **0.117291** |
| 8KB | GAp | Block | gcc_test | 15.4210 | 2.2716 | **0.422437** |
| 8KB | GAp | Scalar | gcc_test | 13.2860 | 0.4944 | **0.117040** |
| 8KB | PAg | Block | gcc_test | 16.3010 | 1.9438 | **0.367802** |
| 8KB | PAg | Scalar | gcc_test | 14.1460 | 0.4795 | **0.112557** |
| 8KB | PAp | Block | gcc_test | 14.7920 | 1.9766 | **0.381939** |
| 8KB | PAp | Scalar | gcc_test | 13.1080 | 0.4825 | **0.113589** |

