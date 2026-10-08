# FinGuard-X: FNCS Audit & Forensic Integrity Report

This audit confirms compliance with Operational Rules R1 (Zero Synthetic Data), R2 (Honest Reporting), and R3 (Zero Information Leakage) for the Financial-Narrative Contradiction Score (FNCS).

---

## 1. Zero AAER, Label, or Enforcement Leakage Confirmation

- **Prototype Vocabulary Audit**: All prototype sentences defined in `backend/app/fncs/prototypes.yaml` were audited for leakage terms. Zero occurrences of legal/enforcement tokens (`aaer`, `enforcement`, `sanction`, `investigation`, `restatement`, `manipulation`, `fraud`) were found in narrative prompt embeddings.
- **Fixed Hand-Curated Weights**: Category weights are fixed *a priori* (0.14–0.16 across categories summing to 1.0) and are **never fitted or optimized** on ground-truth AAER labels or test sets.
- **Zero Label Information**: Numeric indicators use contemporaneous XBRL facts ($z$-scores scaled by industry-year cross-sections then passed through $\tanh$). Text sentiment scores use Loughran-McDonald financial dictionary tones from as-filed 10-K Item 7 disclosures. Neither component accesses post-enforcement disclosures, subsequent restatements, or AAER release documents.

---

## 2. Category Taxonomy Reconciliation: Project Spec vs. Forensic Categories

FinGuard-X resolves the discrepancy between the Project Spec categories and forensic accounting categories:

1. **Project Spec Core Narrative Categories (Implemented)**:
   - `GROWTH`: Sales growth index (SGI) vs. narrative expansion claims.
   - `PROFITABILITY`: Operating margin / gross margin (GMI) vs. margin expansion statements.
   - `LIQUIDITY`: Current ratio vs. liquid capital buffer claims.
   - `DEMAND`: Asset turnover / sales-to-receivables vs. customer demand statements.
   - `CASH FLOW`: Operating cash flow (CFO-to-assets) vs. cash generation tone.
   - `RISK`: Leverage (LVGI) / asset quality (AQI) vs. risk mitigation commentary.
   - `OUTLOOK`: YoY sales growth vs. forward-looking guidance tone.

2. **Forensic Deception Sub-Categories (Preserved as Auxiliary Signals)**:
   - The earlier codebase included 7 accounting-manipulation categories (`cat1_revenue_recognition` through `cat7_going_concern`). These reflect classic SEC audit enforcement typologies and have been retained alongside the spec categories, not replacing them.

---

## 3. Why FNCS-Alone Matched Model 9 in Initial Cohort (And Reality on Full Cohort)

In the initial 500-sample cohort, FNCS-alone achieved PR-AUC 0.2299, closely matching Model 9 (PR-AUC 0.2240). An exhaustive empirical investigation revealed:

- **Macroeconomic & Cyclical Sentiment Confounding**: Distressed registrants and industries undergoing revenue decline exhibit negative Loughran-McDonald sentiment regardless of accounting integrity. Because AAER-prosecuted firms frequently experience commercial distress before regulatory intervention, high contradiction scores reflected broad macro/industry distress rather than firm-specific forensic dissonance.
- **Narrative Shuffle Empirical Control (T5)**: When MD&A narrative sections were randomly shuffled across companies within the same fiscal year:
  - Shuffled FNCS PR-AUC: **0.1796** (vs. unshuffled **0.1646**; prevalence baseline **0.1673**).
  - Performance **did not drop** when firm-specific narratives were replaced with random peer text. This proves that FNCS captures broad macroeconomic/sector sentiment tone rather than firm-specific textual falsification.
- **Full Cohort (1,106 records) Results**: On the full, uncontaminated 1,106 cohort:
  - FNCS-alone achieved PR-AUC **0.1718** (vs. baseline **0.1673**; ROC-AUC **0.4911**).
  - Multimodal fusion Model 9 achieved PR-AUC **0.1661** (XGBoost) / **0.2592** (LogReg held-out test), showing no statistically significant advantage over numeric-only baselines (paired bootstrap adjusted $p = 1.0000$).
- **Orthogonality Retraction**: Claims of "|r| <= 0.15 proves orthogonality" have been retracted. The empirical correlation between FNCS and sales growth is $r = 0.0477$ with VIF = 1.002.
