# FinGuard-X: Methodological Limitations & Risk Disclosures

This document outlines the methodological boundaries, data constraints, and operational caveats of the FinGuard-X forensic detection system, adhering strictly to Operational Rules R1 (No Fake Data), R2 (Honest Reporting), and R5 (Language Standards).

---

## 1. Small Positive Cohort Size & Statistical Power

- **Cohort Structure**: The current evaluation cohort consists of 500 company-years spanning 84 unique SEC registrants (14 positive corporate issuers with 80 company-years, matched 1:5 to 70 control registrants with 420 company-years).
- **Degrees of Freedom**: In 5-fold CIK-grouped stratified cross-validation, each validation fold evaluates exactly 16 positive company-years and 84 control company-years. Registrant-level clustering prevents data leakage across years of the same firm, but restricts the effective sample size to 14 independent positive clusters.
- **Consequence for Statistical Inference**: 
  - Metric estimates exhibit wide 95% cluster bootstrap confidence intervals (e.g., Model 9 XGBoost PR-AUC of 0.2240 has a 95% CI of [0.166, 0.305]; ROC-AUC of 0.6024 has a 95% CI of [0.534, 0.670]).
  - Point estimates must be interpreted alongside their confidence intervals rather than as single definitive figures.

---

## 2. AAER Label Noise & Regulatory Enforcement Asymmetry

- **Enforcement Asymmetry (Detection Bias)**: Positive labels are derived from official SEC Accounting and Auditing Enforcement Releases (AAERs). The SEC Enforcement Division initiates proceedings based on whistleblower tips, market crashes, investigative resources, and regulatory priorities. Consequently, the positive class represents *detected, investigated, and prosecuted* accounting violations, which may over-represent high-visibility registrants or particularly severe frauds.
- **The Positive-Unlabeled (PU) Problem**: Registrants in the control pool are matched on 2-digit SIC industry division, fiscal year, and total asset size ($\pm 30\%$). While controls have no recorded AAER enforcement actions in our database, they are not guaranteed to be entirely free of accounting impropriety. Unlabeled manipulation in the control pool acts as label noise, biasing classification metrics downward.
- **Temporal Alignment**: Enforcement actions often conclude years after the violation period. FinGuard-X strictly maps violations to the fiscal years explicitly cited in the AAER findings as containing misleading financial statements, avoiding forward-looking leakage.

---

## 3. Unstructured SEC Filing Extraction Errors

- **Format Diversity**: SEC EDGAR 10-K filings from FY2010 to FY2023 exhibit substantial variation in document format, ranging from modern inline XBRL (iXBRL) to legacy HTML tables and pre-HTML ASCII submissions.
- **Extraction Rates**:
  - Item 7 (MD&A): 91.45% extraction success across 982 attempted filings.
  - Item 1A (Risk Factors): 89.71% extraction success.
  - Related-Party Transaction Footnotes: 34.52% extraction success due to non-standard note numbering, merged footnotes, and inconsistent table formatting.
- **Mitigation & Integrity**: When a section cannot be extracted with high confidence, FinGuard-X never interpolates or fabricates text. Instead, features are zero-imputed and accompanied by explicit boolean availability indicators (`has_mda=0`, `has_risk_factors=0`, `graph_available=0`) that tree-based models leverage directly.

---

## 4. Knowledge Graph Coverage & Sparse Related-Party Disclosures

- **Graph Coverage**: Entity-relationship graphs were successfully constructed for 149 out of 500 company-years (29.80% coverage), comprising 3,268 nodes, 3,871 edges, and 484 shell/holding entities.
- **Absence vs. True Zero**: In corporate financial reporting, many firms have no material related-party transactions in a given fiscal year. Under US GAAP (ASC 850), such firms disclose nothing or state "none". Therefore, a missing graph often reflects a legitimate absence of reportable ties rather than extraction failure.
- **Anomaly Score Handling**: For company-years lacking graph disclosures, `graph_available` is set to 0, topological metrics (density, clustering, shell entity ratios) are set to 0.0, and `GRAPH_ANOMALY_SCORE` is assigned 0.0. The XGBoost model learns split paths conditioned on `graph_available`.

---

## 5. Absence of Human-Curated Gold Standard Benchmark

- **Unsupervised / Distant Extraction**: While XBRL numerical facts are auditable against SEC archives, NLP sentence pairings, sentiment tones, and extracted network edges lack an external third-party human-annotated gold standard.
- **Validation Methodology**: Graph and text representations are validated through:
  1. Downstream ablation testing (measuring incremental PR-AUC and ROC-AUC gains over numeric baselines).
  2. Qualitative spot-audits of real SEC disclosure excerpts (e.g., verifying CECO Environmental FY2019, LSB Industries FY2012, and Moog Inc FY2023 against raw filings).
  3. Redundancy analysis (confirming $|r| \le 0.15$ between FNCS components and standard financial ratios).

---

## 6. Regulatory & Decision Scope: Review Signals, Never Proof

- **Strict Terminology (Rule R5)**: All model outputs, API responses, and dashboard views are strictly labeled **"Fraud Risk / Review Priority"** (Low: 0–29, Moderate: 30–59, High: 60–79, Very High: 80–100). The terms "fraud detected" or "fraudster" are prohibited across the platform.
- **Triage and Scoping Only**: Model predictions, Beneish components, narrative drift scores, and TreeSHAP attributions are designed solely as decision-support signals for:
  - Regulatory triage and audit scoping.
  - Prioritizing forensic examination of high-discrepancy registrants.
  - Identifying non-obvious cross-modal inconsistencies between management discussions and underlying accounting ratios.
- **No Substitute for Human Audit**: An elevated risk score does not constitute legal, accounting, or regulatory proof of wrongdoing. Legitimate corporate events (e.g., rapid mergers, restructuring, abrupt macroeconomic shifts) can produce statistical anomalies that mimic manipulation patterns. Human forensic investigation remains indispensable.
