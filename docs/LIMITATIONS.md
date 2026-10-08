# FinGuard-X: Methodological Limitations & Risk Disclosures

This document outlines the methodological boundaries, data constraints, and operational caveats of the FinGuard-X forensic detection system, adhering strictly to Operational Rules R1 (Zero Synthetic Data), R2 (Honest Reporting), and R5 (Language Standards).

---

## 1. Effective Sample Size & Statistical Power

- **Cohort Structure**: The full evaluation cohort consists of **1,106 company-years** spanning 801 unique SEC registrants:
  - **Positives**: **185 company-years** across **104 independent CIKs** citing authentic corporate accounting misstatements in SEC AAER findings.
  - **Controls**: **921 matched control company-years** across **697 independent CIKs**, matched 1:5 on 2-digit SIC industry division, fiscal year, and total assets ($\pm 30\%$) without replacement.
- **Effective Sample Size**: Because multiple misstated fiscal years often belong to the same issuer (e.g. multi-year restatements), the effective independent positive sample size is **104 independent clusters**.
- **Cross-Validation Degrees of Freedom**: In 5-fold CIK-grouped stratified cross-validation, each fold evaluates exactly 37 positive company-years (20–21 independent CIKs) and ~184 control company-years. This limits statistical power to detect small effect sizes and yields wide bootstrap confidence intervals.

---

## 2. AAER Label Noise & Enforcement Asymmetry (Positive-Unlabeled Problem)

- **Enforcement Asymmetry (Detection Bias)**: Positive labels are derived exclusively from official SEC Accounting and Auditing Enforcement Releases (AAERs). The SEC Enforcement Division initiates investigations based on whistleblower tips, market crashes, short-seller reports, and regulatory priorities. Consequently, the positive class represents *detected, investigated, and successfully prosecuted* accounting violations, which systematically over-represents high-profile firms.
- **The Positive-Unlabeled (PU) Problem**: Controls have zero recorded AAER enforcement actions in our database, but are not guaranteed to be free of accounting impropriety. Unlabeled manipulation in the control pool acts as label noise, attenuating classification metrics.
- **Temporal Alignment**: To prevent forward-looking leakage, labels are mapped strictly to the fiscal years explicitly cited in SEC PDF findings text as containing false or misleading statements.

---

## 3. Unstructured SEC Filing Extraction Errors

- **Format Diversity**: SEC EDGAR 10-K filings from FY2010 to FY2023 exhibit extreme document format heterogeneity, ranging from modern inline XBRL (iXBRL) to legacy HTML tables and pre-HTML ASCII submissions.
- **Coverage**:
  - Item 7 (MD&A): Extracted with 150-sentence truncation cap to prevent OOM errors and memory exhaustion.
  - Related-Party Transaction Footnotes: Disclosed in only ~5% of company-years (54 controls / 9 positives), reflecting sparse reporting under ASC 850.
- **Missingness Handling**: When a section or footnote is absent, FinGuard-X never interpolates or fabricates text. Instead, features are zero-imputed and accompanied by explicit boolean availability flags (`graph_available=0`) that tree-based models leverage directly.

---

## 4. Unmeasured Knowledge Graph Quality & Absence of Gold Set

- **Heuristic Extraction**: Footnote entity-relationship extraction relies on regex patterns and spaCy NER rather than human-audited ground truth. A hand-labeled graph benchmark was not constructed. Graph precision and recall remain unmeasured against a human gold standard.
- **Size-Matching Artifact**: Because controls were matched 1:5 on total assets $\pm 30\%$, their corporate scale closely mirrors that of positive issuers. Consequently, graph topology alone (Model 4 ROC-AUC ~0.49–0.50) provides zero discriminative advantage.

---

## 5. FNCS Narrative Alignment & Non-Orthogonality

- **Macroeconomic vs. Firm-Specific Signal**: An empirical control experiment shuffling narratives across companies within the same fiscal year yielded PR-AUC 0.1796 (compared to 0.1646 for unshuffled narratives). This confirms that FNCS reflects broad sector/macroeconomic sentiment rather than firm-specific forensic dissonance.
- **Retraction of Orthogonality Claims**: Claims that $|r| \le 0.15$ proves mathematical orthogonality are retracted. FNCS exhibits mild correlation ($r = 0.0477$) with sales growth and an estimated VIF of 1.002.

---

## 6. Regulatory & Decision Scope: Review Signals, Never Proof (Rule R5)

- **Strict Terminology**: All model outputs, API responses, and dashboard views are strictly labeled **"Fraud Risk / Review Priority"** (Low: 0–29, Moderate: 30–59, High: 60–79, Very High: 80–100). The terms "fraud detected" or "fraudster" are strictly prohibited across the platform.
- **Triage and Scoping Only**: Model predictions, Beneish components, narrative drift scores, and TreeSHAP attributions are designed solely as decision-support signals for audit scoping and forensic review prioritization.
- **No Substitute for Human Audit**: Legitimate corporate events (rapid acquisitions, sudden restructuring, abrupt macroeconomic shocks) can produce statistical anomalies that mimic manipulation patterns. Human forensic investigation remains indispensable.
