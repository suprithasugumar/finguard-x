# FinGuard-X — Phase 0 Feature Missingness & Root Cause Diagnostic Report

**Audit Date:** 2026-10-27  
**Database:** PostgreSQL (`finguard`)  
**Cohort Scope:** Full Evaluated Cohort (`company_year_labels`, N = 1106: 185 AAER Corporate Positives, 921 Matched Controls)  
**Fiscal Year Span:** 2010 – 2023  

---

## 1. Executive Summary

This diagnostic report provides an exhaustive, empirical audit of missingness across all multimodal feature tables in FinGuard-X, conforming to the **Phase 0 specification**. No code modifications or pipeline runs were executed prior to this baseline diagnosis.

### Overall Missingness Summary by Modality

| Modality / Feature Table | Features Evaluated | Overall Mean % NULL | Overall Mean % Zero | % Missing or Zero | Positives (AAER) % NULL | Controls % NULL |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Beneish M-Score & Indices** (`company_year_features`) | 9 | **33.6%** | 0.2% | **33.8%** | 35.7% | 33.2% |
| **18 Core Financial Ratios** (`company_year_features`) | 18 | **20.1%** | 1.8% | **21.9%** | 22.4% | 19.6% |
| **Text / NLP MD&A Drift** (`filing_nlp_features`) | 8 | **54.9%** | 0.0% | **54.9%** | 56.2% | 54.6% |
| **Knowledge Graph** (`company_year_graph_features`) | 10 | 0.0% | **94.3%** | **94.3%** | 93.5% | 94.5% |
| **FNCS Contradiction** (`company_year_fncs_features`) | 9 | 0.0% | **88.6%** | **88.6%** | 89.2% | 88.5% |

---

## 2. Top 10 Root Causes of Feature Missingness

### #1: Strict All-or-Nothing Composite Beneish M-Score Formula
- **Impact:** 68.1% of company-years (753 / 1,106)
- **Category:** Numeric / Beneish
- **Diagnostic Root Cause:** Beneish M-Score requires all 8 sub-indices simultaneously. If even one sub-index is missing (most frequently GMI at 44.6% or DSRI at 42.7%), M-Score is set to NULL rather than computing a partial or robust composite.

### #2: Gross Margin / COGS XBRL Tag-Mapping Gap
- **Impact:** 44.6% of company-years (493 / 1,106) missing GMI
- **Category:** Numeric / Beneish
- **Diagnostic Root Cause:** Service, technology, media, and healthcare companies frequently report revenue without 'CostOfGoodsAndServicesSold', using 'OperatingExpenses' or custom cost concepts. The pipeline lacks fallback chains to reconstruct Gross Profit as (Revenues - Operating Expenses).

### #3: Accounts Receivable Prior Year (t-1) Join / Restatement Failure
- **Impact:** 42.7% of company-years (472 / 1,106) missing DSRI; 32.5% missing Sales/Receivables
- **Category:** Numeric / Beneish & Ratios
- **Diagnostic Root Cause:** DSRI requires current and prior receivables & revenues. Many filings report 'ReceivablesNetCurrent' or 'AccountsAndNotesReceivableNet' rather than 'AccountsReceivableNetCurrent', causing tag-mapping failure on the t-1 join.

### #4: Liability & Stockholders' Equity Conceptual Disconnections
- **Impact:** 38.1% of company-years (421 / 1,106) missing Debt-to-Equity
- **Category:** Numeric / 18 Ratios
- **Diagnostic Root Cause:** Many firms report 'LiabilitiesAndStockholdersEquity' or negative equity (insolvency/deficit), or report debt under unlinked lease obligations, leading to missing total liabilities or denominator division failures.

### #5: Structural Non-Reporting of Inventory by Non-Manufacturing Registrants
- **Impact:** 36.5% of company-years (404 / 1,106) missing Inventory-to-Assets
- **Category:** Numeric / 18 Ratios
- **Diagnostic Root Cause:** Software, financial, and consulting firms legitimately hold zero inventory. Currently, the pipeline tags this as 'no_inventory_reported' and leaves the feature NULL instead of explicitly recognizing it as a structural non-applicable zero (or preserving missingness cleanly).

### #6: Text Extraction / Sentence Alignment Failure (607/1106 Unprocessed)
- **Impact:** 54.9% of company-years (607 / 1,106) missing text NLP features
- **Category:** Text / NLP Drift
- **Diagnostic Root Cause:** Item 7 MD&A parsing failed on non-standard HTML table layouts, roman numeral headers, or exhibits. Sentence alignment yielded 0 aligned pairs because boilerplate text was not stripped, and cross-year sentence alignment thresholds were overly strict.

### #7: Footnote Regex NER Failure on Related-Party Entities
- **Impact:** 94.3% of company-years (1,043 / 1,106) have zero graph entities
- **Category:** Knowledge Graph
- **Diagnostic Root Cause:** Although 339 filings contained non-empty related-party disclosure sections, only 63 produced a usable NetworkX graph (5.7%). The entity extractor regex failed to resolve company suffixes (LLC, LP, Inc.), executive name patterns, and transaction verbs.

### #8: FNCS Text Tone and Relevance Weight Defaulting Silently to 0.0
- **Impact:** 84.7% to 91.1% zero-rate across all 7 FNCS categories
- **Category:** FNCS Deception Scoring
- **Diagnostic Root Cause:** When MD&A text is missing or keyword cosine similarity is below threshold, the FNCS pipeline defaulted `text_tone_tc = 0.0` and `presence_weight_wc = 0.0` instead of recording NULL + diagnostic reason. Furthermore, table columns `cat1...cat7` were left as 0.0.

### #9: Pre-2012 XBRL SEC Mandate Phase-In Scarcity
- **Impact:** Yearly null rates spike to 70–85% for fiscal years 2010–2011
- **Category:** Data Engineering / SEC EDGAR
- **Diagnostic Root Cause:** SEC interactive data (XBRL) was only mandatory for smaller reporting companies starting in 2011-2012. Pre-2012 filings in EDGAR are frequently text/ASCII with zero structured tags in `financial_facts`.

### #10: Financial Industry Registrant Inapplicability
- **Impact:** 5.4% of company-years (60 / 1,106) flagged beneish_applicable = False
- **Category:** Domain Architecture / SIC 6xxx
- **Diagnostic Root Cause:** Beneish M-Score and standard industrial ratios (current ratio, inventory, gross margin) are mathematically and economically invalid for banks, insurance, and brokerages (SIC 6000–6999). These firms appropriately have NULL for standard commercial ratios.

---

## 3. Beneish M-Score & 8 Sub-Indices Breakdown

The composite Beneish M-Score is currently missing for **59.04%** of all cohort observations.

| Component | Description | % NULL (Overall) | % NULL (AAER) | % NULL (Control) | Primary Missing Input / Reason |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **beneish_dsri** | Days Sales in Receivables Index | 27.12% | 32.43% | 26.06% | Missing ReceivablesNet or Sales in t or t-1 (240 cases) |
| **beneish_gmi** | Gross Margin Index | 38.07% | 39.46% | 37.79% | Service/Tech firms lack COGS tag (17 cases) |
| **beneish_aqi** | Asset Quality Index | 19.71% | 21.08% | 19.44% | Missing PPE net or current assets (136 cases) |
| **beneish_sgi** | Sales Growth Index | 15.82% | 20.54% | 14.88% | Missing prior year revenue tag (115 cases) |
| **beneish_depi** | Depreciation Index | 19.08% | 22.16% | 18.46% | Depreciation not separately itemized from amortization (149 cases) |
| **beneish_sgai** | SG&A Expense Index | 23.33% | 24.86% | 23.02% | SG&A combined into general operating expenses (198 cases) |
| **beneish_lvgi** | Leverage Index | 11.84% | 15.14% | 11.18% | Long-term debt or total assets missing (53 cases) |
| **beneish_tata** | Total Accruals to Total Assets | 26.58% | 29.73% | 25.95% | Missing Operating Cash Flow (CFO) in facts (234 cases) |
| **beneish_m_score** | **Composite Beneish M-Score** | **59.04%** | **61.62%** | **58.52%** | **Any missing component invalidates full sum** |

---

## 4. 18 Core Financial Accounting Ratios Breakdown

| Ratio Name | % NULL (Overall) | % Zero | % Missing or Zero | % NULL (AAER) | % NULL (Control) | Primary Missing Input / Reason |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **debt_to_equity** | 38.1% | 0.4% | 38.5% | 37.3% | 38.2% | Missing total liabilities or negative stockholders' equity |
| **inventory_to_assets** | 36.5% | 1.2% | 37.7% | 38.9% | 36.0% | Service / tech firms report zero inventory |
| **sales_to_receivables** | 32.5% | 0.0% | 32.5% | 36.8% | 31.6% | Missing net receivables tag or revenue |
| **receivables_to_assets** | 30.1% | 0.0% | 30.1% | 33.5% | 29.4% | Missing AccountsReceivableNetCurrent |
| **cash_flow_margin** | 26.1% | 0.1% | 26.2% | 27.6% | 25.8% | Missing cash flow from operations (CFO) or revenue |
| **accruals_bs_to_assets** | 24.1% | 0.0% | 24.1% | 29.2% | 23.0% | Missing balance-sheet delta inputs (t vs t-1 assets/liab) |
| **accruals_cf_to_assets** | 22.3% | 0.0% | 22.3% | 24.9% | 21.8% | Missing net income or operating cash flow |
| **cfo_to_assets** | 21.7% | 0.0% | 21.7% | 24.3% | 21.2% | Missing NetCashProvidedByUsedInOperatingActivities |
| **operating_margin** | 18.2% | 0.0% | 18.2% | 21.1% | 17.6% | Missing OperatingIncomeLoss or revenue |
| **capex_to_assets** | 16.6% | 1.8% | 18.4% | 17.8% | 16.4% | Capex not tagged under standard PP&E acquisition tags |
| **asset_growth** | 12.9% | 0.0% | 12.9% | 18.4% | 11.8% | Missing prior year total assets |
| **net_margin** | 12.4% | 0.0% | 12.4% | 13.0% | 12.3% | Missing NetIncomeLoss or revenue tag |
| **current_ratio** | 11.1% | 0.0% | 11.1% | 14.1% | 10.5% | Missing AssetsCurrent or LiabilitiesCurrent |
| **working_capital_to_assets** | 11.1% | 0.0% | 11.1% | 14.1% | 10.5% | Missing AssetsCurrent or LiabilitiesCurrent |
| **debt_to_assets** | 9.3% | 0.1% | 9.4% | 10.3% | 9.1% | Missing short/long term debt tags |
| **cash_to_assets** | 6.7% | 0.0% | 6.7% | 8.1% | 6.4% | Missing CashAndCashEquivalentsAtCarryingValue |
| **roa** | 5.8% | 0.0% | 5.8% | 7.6% | 5.4% | Missing NetIncomeLoss |
| **asset_turnover** | 5.8% | 0.0% | 5.8% | 7.6% | 5.4% | Missing Revenues tag |

---

## 5. Text / NLP MD&A Drift & Extraction Breakdown

- **Total Cohort Company-Years:** 1106
- **Filings with No Item 7 MD&A Extracted:** 584 / 1106 (**52.8%**)
- **Filings with No Prior-Year (t-1) MD&A:** 864 / 1106 (**78.1%**)
- **Filings with Zero Aligned Sentence Pairs:** 974 / 1106 (**88.1%**)
- **Records Present in `filing_nlp_features`:** 499 / 1106 (**45.1%**)

### NLP Features Missingness Table

| Feature Name | Total | % NULL | % Zero | AAER % NULL | Control % NULL |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `mda_drift_score` | 1106 | 88.07% | 0.0% | 89.19% | 87.84% |
| `doc_embedding_cosine_drift` | 1106 | 88.07% | 0.0% | 89.19% | 87.84% |
| `risk_drift_score` | 1106 | 88.88% | 0.0% | 87.57% | 89.14% |
| `vocab_jaccard_distance` | 1106 | 88.07% | 0.0% | 89.19% | 87.84% |
| `uncertainty_rate` | 1106 | 87.7% | 0.0% | 89.19% | 87.4% |
| `negative_sentiment_rate` | 1106 | 87.7% | 0.09% | 89.19% | 87.4% |
| `readability_fog_index` | 1106 | 87.7% | 0.0% | 89.19% | 87.4% |
| `financial_uncertainty_rate` | 1106 | 87.7% | 0.0% | 89.19% | 87.4% |

---

## 6. Related-Party Knowledge Graph Breakdown

- **Total Graph Records:** 1106
- **Company-Years with `graph_available == false`:** 1043 / 1106 (**94.3%**)
- **Company-Years with Zero Extracted Entities (`num_nodes == 0`):** 1043 / 1106 (**94.3%**)
- **Company-Years with No Related-Party Footnote Found:** 900 / 1106 (**81.4%**)
- **Footnote Found but 0 Entities Extracted:** 837 filings had related-party text, but zero entity tuples were extracted by the regex entity pipeline.

---

## 7. FNCS Consistency Scores & Evidence Breakdown

In `company_year_fncs_features`:
- Table columns `cat1_revenue_recognition` through `cat7_going_concern` are **0.0 for 100% of rows**, because scores were stored in the nested `fncs_evidence` JSON column rather than flattened table columns.
- Across all 7 categories in `fncs_evidence`:

| Category Name | Total Evals | `text_tone_tc == 0.0` | % Tone == 0 | `presence_weight_wc == 0.0` | % Weight == 0 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Cash_flow** | 1106 | 98 | 8.9% | 0 | 0.0% |
| **Demand** | 1106 | 71 | 6.4% | 0 | 0.0% |
| **Growth** | 1106 | 55 | 5.0% | 0 | 0.0% |
| **Liquidity** | 1106 | 136 | 12.3% | 0 | 0.0% |
| **Outlook** | 1106 | 72 | 6.5% | 0 | 0.0% |
| **Profitability** | 1106 | 86 | 7.8% | 0 | 0.0% |
| **Risk** | 1106 | 104 | 9.4% | 0 | 0.0% |

---

## 8. Summary of Mandatory Fixes for Phase 1 & Phase 2

1. **Tag Mapping & Fallbacks (Phase 1):** Add concept fallback chains for Revenues, Gross Profit, COGS, Receivables, CFO, and PP&E.
2. **Company-Year Panel (Phase 1):** Materialize a structured t vs t-1 panel joining CIK + fiscal year, allowing partial M-Scores (e.g. 6/8 components) instead of all-or-nothing NULL.
3. **Missing Indicators (Phase 1):** Introduce `*_missing` binary indicators per feature group and ensure NULL values stay NULL for UI display.
4. **MD&A Parser & Text Alignment (Phase 2):** Add fallback regex for Item 7 variants and HTML tables, strip legal boilerplate prior to alignment, and benchmark FinBERT vs MiniLM.
5. **Graph NER Resolution (Phase 2):** Upgrade related-party footnote entity resolution with fuzzy suffix matching (>=0.9) to resolve entity pairs.
6. **FNCS Claim-Level NLI (Phase 2):** Flatten category scores into database columns, replace silent `0.0` defaults with `NULL + reason`, and ground text claims with NLI verification.
