# FinGuard-X: Empirical Evaluation & Multimodal Benchmark Results

> **Note on Empirical Evidence**: Following rigorous standards, every metric in this report is derived directly from PostgreSQL database records and pipeline artifacts. No claim of 'proof' or 'high statistical significance' is made; results are documented as objective evidence for or against performance improvements.

## 1. Evaluation Cohort & Integrity

- **Total Labeled Cohort**: 1,106 company-years.
- **Fraud Prevalence (Random-Guess PR-AUC Baseline)**: **16.73%**.
- **Control Contamination**: 0.0% (Zero AAER-cited entities in the control pool).

### 5-Fold Stratified Grouped Split Composition
| Fold | Positives | Controls | Positive CIKs | Control CIKs | Total CIKs |
|---|---|---|---|---|---|
| Fold 1 | 37 | 185 | 21 | 140 | 161 |
| Fold 2 | 37 | 184 | 21 | 140 | 161 |
| Fold 3 | 37 | 184 | 21 | 139 | 160 |
| Fold 4 | 37 | 184 | 21 | 139 | 160 |
| Fold 5 | 37 | 184 | 20 | 139 | 159 |


## 2. Primary Evaluation: Time-Aware Held-Out Split

To rigorously simulate forward-looking deployment and prevent temporal leakage, models are trained on earlier fiscal years, decision thresholds and calibration are tuned on middle fiscal years, and final evaluation is measured on held-out latest years. **CIKs never cross splits** (zero CIK leakage across time partitions).

| Split | Fiscal Years | Records | Positives | Independent CIKs | Prevalence Baseline |
|---|---|---|---|---|---|
| Train | FY2010–FY2018 | 614 | 94 | 457 | 15.31% |
| Validation | FY2019–FY2020 | 267 | 53 | 186 | 19.85% |
| Held-Out Test | FY2021–FY2023 | 225 | 38 | 158 | 16.89% |


### Primary Evaluation Benchmark Table (Test Set Results)
| Model | Classifier | PR-AUC | Random Baseline | ROC-AUC | F1-Score | Brier Score | 95% CI (PR-AUC) |
|---|---|---|---|---|---|---|---|
| M1: Beneish M-Score | Rule-based | 0.1716 | 0.1689 | 0.4377 | 0.1311 | 0.2032 | [0.1015, 0.2978] |
| Model 2: Numeric-only | LogReg | 0.1742 | 0.1689 | 0.5122 | 0.1667 | 0.1576 | [0.1062, 0.2839] |
| Model 2: Numeric-only | XGBoost | 0.2220 | 0.1689 | 0.5502 | 0.1538 | 0.1627 | [0.1344, 0.3621] |
| Model 2: Numeric-only | RandomForest | 0.1974 | 0.1689 | 0.5471 | 0.1404 | 0.1642 | [0.1248, 0.3279] |
| Model 3: Text-only | LogReg | 0.1782 | 0.1689 | 0.5222 | 0.0000 | 0.1443 | [0.1058, 0.2675] |
| Model 3: Text-only | XGBoost | 0.1923 | 0.1689 | 0.5330 | 0.0488 | 0.1547 | [0.1149, 0.2883] |
| Model 3: Text-only | RandomForest | 0.2025 | 0.1689 | 0.5642 | 0.0476 | 0.1473 | [0.1242, 0.3038] |
| Model 4: Graph-only | LogReg | 0.1718 | 0.1689 | 0.4929 | 0.2809 | 0.1490 | [0.1039, 0.2617] |
| Model 4: Graph-only | XGBoost | 0.1746 | 0.1689 | 0.5112 | 0.2845 | 0.1449 | [0.1061, 0.2687] |
| Model 4: Graph-only | RandomForest | 0.1744 | 0.1689 | 0.5099 | 0.2845 | 0.1448 | [0.1060, 0.2684] |
| Model 5: Numeric + Text | LogReg | 0.1856 | 0.1689 | 0.5576 | 0.1778 | 0.1560 | [0.1124, 0.2988] |
| Model 5: Numeric + Text | XGBoost | 0.2027 | 0.1689 | 0.5287 | 0.1224 | 0.1647 | [0.1240, 0.3321] |
| Model 5: Numeric + Text | RandomForest | 0.2000 | 0.1689 | 0.5563 | 0.1493 | 0.1669 | [0.1285, 0.3333] |
| Model 6: Numeric + Graph | LogReg | 0.2175 | 0.1689 | 0.5401 | 0.2182 | 0.1563 | [0.1304, 0.3579] |
| Model 6: Numeric + Graph | XGBoost | 0.2251 | 0.1689 | 0.5443 | 0.1633 | 0.1612 | [0.1316, 0.3686] |
| Model 6: Numeric + Graph | RandomForest | 0.2119 | 0.1689 | 0.5509 | 0.1379 | 0.1626 | [0.1314, 0.3508] |
| Model 7: Text + Graph | LogReg | 0.1663 | 0.1689 | 0.4826 | 0.0678 | 0.1512 | [0.0972, 0.2544] |
| Model 7: Text + Graph | XGBoost | 0.1720 | 0.1689 | 0.4939 | 0.0000 | 0.1588 | [0.0959, 0.2606] |
| Model 7: Text + Graph | RandomForest | 0.1756 | 0.1689 | 0.5157 | 0.0000 | 0.1634 | [0.1020, 0.2650] |
| Model 8: Numeric + Text + Graph | LogReg | 0.2533 | 0.1689 | 0.5670 | 0.2366 | 0.1484 | [0.1454, 0.3991] |
| Model 8: Numeric + Text + Graph | XGBoost | 0.2099 | 0.1689 | 0.5267 | 0.1154 | 0.1624 | [0.1231, 0.3489] |
| Model 8: Numeric + Text + Graph | RandomForest | 0.1949 | 0.1689 | 0.5505 | 0.0769 | 0.1655 | [0.1253, 0.3200] |
| Model 9: Numeric + Text + Graph + FNCS | LogReg | 0.2592 | 0.1689 | 0.5602 | 0.2366 | 0.1487 | [0.1479, 0.4067] |
| Model 9: Numeric + Text + Graph + FNCS | XGBoost | 0.1965 | 0.1689 | 0.5293 | 0.0800 | 0.1670 | [0.1235, 0.3199] |
| Model 9: Numeric + Text + Graph + FNCS | RandomForest | 0.2054 | 0.1689 | 0.5609 | 0.1333 | 0.1641 | [0.1328, 0.3391] |
| Model 10: FNCS-alone (Extra) | LogReg | 0.1579 | 0.1689 | 0.4274 | 0.1176 | 0.1449 | [0.1048, 0.2334] |
| Model 10: FNCS-alone (Extra) | XGBoost | 0.1851 | 0.1689 | 0.5367 | 0.0714 | 0.1760 | [0.1190, 0.2787] |
| Model 10: FNCS-alone (Extra) | RandomForest | 0.1793 | 0.1689 | 0.5128 | 0.1127 | 0.1724 | [0.1158, 0.2692] |


## 3. Secondary Evaluation: 5-Fold CIK-Grouped Stratified Cross-Validation

Pooled out-of-fold predictions across 5 CIK-grouped folds evaluated with all 3 classifiers:

| Model | Classifier | PR-AUC | Random Baseline | ROC-AUC | F1-Score | Brier Score | 95% CI (PR-AUC) |
|---|---|---|---|---|---|---|---|
| M1: Beneish M-Score | Rule-based | 0.1799 | 0.1673 | 0.4820 | 0.0870 | 0.1825 | [0.1375, 0.2318] |
| Model 2: Numeric-only | LogReg | 0.1526 | 0.1673 | 0.4704 | 0.2637 | 0.1503 | [0.1208, 0.1934] |
| Model 2: Numeric-only | XGBoost | 0.1704 | 0.1673 | 0.4922 | 0.2249 | 0.1805 | [0.1318, 0.2202] |
| Model 2: Numeric-only | RandomForest | 0.1776 | 0.1673 | 0.5139 | 0.1977 | 0.1804 | [0.1383, 0.2267] |
| Model 3: Text-only | LogReg | 0.1564 | 0.1673 | 0.4710 | 0.2798 | 0.1410 | [0.1235, 0.1994] |
| Model 3: Text-only | XGBoost | 0.1620 | 0.1673 | 0.4886 | 0.2842 | 0.1464 | [0.1266, 0.2070] |
| Model 3: Text-only | RandomForest | 0.1630 | 0.1673 | 0.4914 | 0.2850 | 0.1444 | [0.1280, 0.2091] |
| Model 4: Graph-only | LogReg | 0.1617 | 0.1673 | 0.4879 | 0.2857 | 0.1472 | [0.1274, 0.2069] |
| Model 4: Graph-only | XGBoost | 0.1656 | 0.1673 | 0.4996 | 0.2889 | 0.1453 | [0.1305, 0.2112] |
| Model 4: Graph-only | RandomForest | 0.1649 | 0.1673 | 0.4946 | 0.2871 | 0.1438 | [0.1313, 0.2119] |
| Model 5: Numeric + Text | LogReg | 0.1514 | 0.1673 | 0.4669 | 0.2630 | 0.1512 | [0.1202, 0.1919] |
| Model 5: Numeric + Text | XGBoost | 0.1714 | 0.1673 | 0.4978 | 0.2181 | 0.1837 | [0.1308, 0.2226] |
| Model 5: Numeric + Text | RandomForest | 0.1740 | 0.1673 | 0.5115 | 0.1752 | 0.1830 | [0.1351, 0.2230] |
| Model 6: Numeric + Graph | LogReg | 0.1530 | 0.1673 | 0.4711 | 0.2623 | 0.1535 | [0.1214, 0.1935] |
| Model 6: Numeric + Graph | XGBoost | 0.1744 | 0.1673 | 0.4990 | 0.2254 | 0.1819 | [0.1344, 0.2298] |
| Model 6: Numeric + Graph | RandomForest | 0.1776 | 0.1673 | 0.5124 | 0.1934 | 0.1816 | [0.1378, 0.2291] |
| Model 7: Text + Graph | LogReg | 0.1549 | 0.1673 | 0.4682 | 0.2796 | 0.1460 | [0.1223, 0.1968] |
| Model 7: Text + Graph | XGBoost | 0.1633 | 0.1673 | 0.4810 | 0.2823 | 0.1513 | [0.1289, 0.2115] |
| Model 7: Text + Graph | RandomForest | 0.1619 | 0.1673 | 0.4816 | 0.2801 | 0.1509 | [0.1269, 0.2090] |
| Model 8: Numeric + Text + Graph | LogReg | 0.1508 | 0.1673 | 0.4624 | 0.2599 | 0.1549 | [0.1191, 0.1921] |
| Model 8: Numeric + Text + Graph | XGBoost | 0.1751 | 0.1673 | 0.5026 | 0.2093 | 0.1804 | [0.1355, 0.2265] |
| Model 8: Numeric + Text + Graph | RandomForest | 0.1771 | 0.1673 | 0.5175 | 0.1629 | 0.1828 | [0.1376, 0.2285] |
| Model 9: Numeric + Text + Graph + FNCS | LogReg | 0.1510 | 0.1673 | 0.4594 | 0.2544 | 0.1541 | [0.1187, 0.1915] |
| Model 9: Numeric + Text + Graph + FNCS | XGBoost | 0.1661 | 0.1673 | 0.4941 | 0.2071 | 0.1862 | [0.1279, 0.2151] |
| Model 9: Numeric + Text + Graph + FNCS | RandomForest | 0.1720 | 0.1673 | 0.5027 | 0.1798 | 0.1831 | [0.1336, 0.2212] |
| Model 10: FNCS-alone (Extra) | LogReg | 0.1513 | 0.1673 | 0.4518 | 0.2767 | 0.1399 | [0.1190, 0.1921] |
| Model 10: FNCS-alone (Extra) | XGBoost | 0.1718 | 0.1673 | 0.4911 | 0.2867 | 0.1467 | [0.1349, 0.2197] |
| Model 10: FNCS-alone (Extra) | RandomForest | 0.1669 | 0.1673 | 0.4796 | 0.2813 | 0.1482 | [0.1316, 0.2139] |


## 4. Honest Statistical Significance & Hypotheses (CIK-Cluster Bootstrap B=2000)

Pairwise comparisons of Model 9 (Full Multimodal) against baselines with Holm-Bonferroni correction across family of hypotheses:

| Comparison | Metric | Mean Difference | 95% Bootstrap CI | Raw p-value | Adjusted p-value (Holm-Bonferroni) | Empirical Conclusion |
|---|---|---|---|---|---|---|
| M9 (Full Multimodal) vs M8 (No FNCS) | PR-AUC | -0.0094 | [-0.0201, +0.0005] | 0.9705 | 1.0000 | no evidence for improvement |
| M9 (Full Multimodal) vs M2 (Numeric-Only) | PR-AUC | -0.0045 | [-0.0161, +0.0062] | 0.8035 | 1.0000 | no evidence for improvement |
| M9 (Full Multimodal) vs M1 (Beneish Baseline) | PR-AUC | -0.0126 | [-0.0584, +0.0287] | 0.7015 | 1.0000 | no evidence for improvement |


### Plain Statement on Multimodal Fusion

Empirical evidence indicates that multimodal fusion did **not** achieve a statistically significant improvement over strong numeric-only baselines (mean Δ = -0.0045, adjusted p = 1.0000). Financial accounting ratios remain the primary predictive signal for reporting misstatements.
