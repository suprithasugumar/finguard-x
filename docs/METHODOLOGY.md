# FinGuard-X: Scientific Methodology & Architecture

This document describes the multi-modal data ingestion, label reconstruction, feature engineering, model evaluation, and explanation architecture of FinGuard-X.

---

## 1. Ground Truth Cohort & SEC Bulk Ingestion

- **Universe**: Raw SEC EDGAR bulk archives (`companyfacts.zip`, `submissions.zip`) covering 14,841 registrants, 128,091 annual filings (Form 10-K), and 4,196,717 quantitative XBRL facts (FY2010–FY2023).
- **Rule R1 Provenance Check**: Automated pre-flight integrity check verifies that 100% of filing accessions exist verbatim in SEC submissions and sampled facts match SEC companyfacts archives. Zero synthetic rows.
- **Label Reconstruction Funnel**:
  - AAER enforcement index: 6,647 scraped proceedings (3,322 distinct AAERs).
  - Corporate exclusions: Excluded 1,841 individual officer sanctions and Rule 102(e) auditor suspensions.
  - CIK resolution: 1,124 corporate proceedings resolved to 296 CIKs via clean names, formerName history, and tickers.
  - Quarantined: 245 ambiguous matches isolated in `data/gold/label_review.csv` for human audit (never auto-accepted).
  - Authentic PDF Fiscal Years: Extracted from SEC enforcement findings text via `pypdf`, yielding 185 corporate accounting fraud company-years across 104 independent CIKs.
- **Control Matching (1:5)**:
  - 921 control company-years across 697 independent CIKs.
  - Matched without replacement on 2-digit SIC code, fiscal year, and total assets within $\pm 30\%$.
  - Control contamination: 0.0% (Zero registrants ever cited in an AAER are admitted to the control pool).
- **Total Cohort**: **1,106 company-years** (185 positives, 921 controls).

---

## 2. Analytical Modalities

### Modality 1: Numeric Financial Features (26 Features)
- 18 core financial ratios: `asset_turnover`, `roa`, `operating_margin`, `net_margin`, `current_ratio`, `debt_to_equity`, `cash_to_assets`, `working_capital_to_assets`, `cfo_to_assets`, `sales_to_receivables`, `receivables_to_assets`, `inventory_to_assets`, `capex_to_assets`, `debt_to_assets`, `cash_flow_margin`, `accruals_bs_to_assets`, `accruals_cf_to_assets`, `asset_growth`.
- 8 Beneish M-Score component indices: Days Sales in Receivables (`DSRI`), Gross Margin Index (`GMI`), Asset Quality Index (`AQI`), Sales Growth Index (`SGI`), Depreciation Index (`DEPI`), SG&A Expense Index (`SGAI`), Leverage Index (`LVGI`), and Total Accruals to Total Assets (`TATA`).

### Modality 2: Textual Narrative Drift (8 Features)
- As-filed Item 7 (MD&A) and Item 1A (Risk Factors) extracted from SEC 10-K filings.
- Capped at 150 sentences per section to prevent truncation artifacts and memory exhaustion.
- Cross-year consecutive filing sentence alignment using `all-MiniLM-L6-v2` embeddings:
  - `narrative_drift_score`: Mean Wasserstein distance between consecutive MD&A embeddings.
  - `doc_embedding_cosine_drift`: Cosine distance between mean document representations.
  - `vocab_jaccard_distance`: Lexical turnover between consecutive filings.
  - Loughran-McDonald dictionary rates: `uncertainty_rate`, `negative_sentiment_rate`, `financial_uncertainty_rate`.
  - Readability metrics: `avg_sentence_length`, `readability_fog_index`.

### Modality 3: Related-Party Knowledge Graphs (15 Features)
- Footnote extraction from SEC 10-K financial statement notes covering related-party transactions (ASC 850).
- NetworkX entity-relationship graphs capturing focal company, directors, officers, shell entities, and LLC affiliates.
- Features: `graph_available`, `graph_size`, `num_nodes`, `num_edges`, `density`, `avg_degree`, `num_officers`, `num_entities`, `num_undisclosed_or_shell`, `max_clique_size`, `clustering_coefficient`, `betweenness_centrality_max`, `yoy_node_churn`, `yoy_edge_churn`, `graph_anomaly_score`.
- Handled via `graph_available` indicator; zero-imputed when footnote is absent or discloses no transactions.

### Modality 4: Financial-Narrative Contradiction Score (FNCS) (9 Features)
- Compares numeric directional trends against MD&A sentiment across 7 core narrative categories:
  1. `GROWTH`: SGI and receivables turnover vs. narrative expansion claims.
  2. `PROFITABILITY`: Operating margin and GMI vs. gross profit commentary.
  3. `LIQUIDITY`: Current ratio vs. liquid capital buffer claims.
  4. `DEMAND`: Asset turnover and sales-to-receivables vs. order demand claims.
  5. `CASH FLOW`: Operating cash flow ratio vs. cash generation tone.
  6. `RISK`: Leverage index and asset quality vs. risk mitigation tone.
  7. `OUTLOOK`: YoY sales growth vs. forward-looking guidance tone.
- Contradiction computed as:
  $$\text{Contradiction}_c = \frac{1 - \operatorname{sign}(z_c) \cdot \operatorname{sign}(\tau_c)}{2} \cdot |z_c - \tau_c|$$
  where $z_c$ is the winsorized industry-year numeric signal passed through $\tanh$, and $\tau_c$ is the Loughran-McDonald sentiment tone of top-retrieved disclosure sentences.
- Features: 7 category contradiction scores, overall `contradiction_score`, and aggregate `fncs_score`.

---

## 3. Evaluation Design & Honest Statistics

### Primary Evaluation: Time-Aware Held-Out Split
- **Train Split (FY2010–FY2018)**: 614 records (94 positives, 457 unique CIKs).
- **Validation Split (FY2019–FY2020)**: 267 records (53 positives, 186 unique CIKs) for Platt calibration and threshold tuning.
- **Held-Out Test Split (FY2021–FY2023)**: 225 records (38 positives, 158 unique CIKs) for final evaluation.
- **Strict Isolation**: Zero CIK leakage across time partitions (each registrant appears in exactly one split).

### Secondary Evaluation: 5-Fold CIK-Grouped Stratified CV
- 1,106 company-years split into 5 folds grouped by CIK to guarantee zero firm overlap between training and validation.
- Exactly 37 positives per fold; 21, 21, 21, 21, 20 positive CIKs per fold.
- Prevalence baseline: **16.73%** (reported alongside all PR-AUC numbers).

### Classifiers Evaluated Across All 10 Models
- Every model evaluated across:
  1. `LogReg`: Balanced regularized logistic regression.
  2. `XGBoost`: Gradient boosted decision trees with `scale_pos_weight`.
  3. `RandomForest`: Bagged tree ensemble via `XGBRFClassifier`.

### Statistical Significance: CIK-Cluster Bootstrap & Holm-Bonferroni
- $B = 2000$ bootstrap resamples clustering by CIK.
- P-values reported as $< 1/B$ when zero resamples cross zero; never "p = 0.0000".
- Family-wise error rate across M9 vs M1, M2, and M8 controlled via step-down Holm-Bonferroni correction.

---

## 4. Multi-Modal Explainability & Calibration

- **Out-of-Fold Calibration**: Predictions calibrated via Platt scaling (logistic sigmoid fit on validation logits).
- **TreeSHAP Attributions**: SHAP values computed strictly from out-of-fold models so no sample is explained by a model trained on its own CIK.
- **Factor Attribution**: Expressed in log-odds contributions accompanied by observed value, industry peer median, and direction ("pushes risk up / down by $\pm X$ log-odds").
- **Ground Rules Wording**: Outputs strictly labeled **"Fraud Risk / Review Priority"** (Low, Moderate, High, Very High). The phrase "fraud detected" is prohibited.
