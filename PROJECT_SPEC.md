# FinGuard-X: Master Build Specification

## 0. Role and operating protocol

You are the lead software architect, ML engineer, data engineer, NLP engineer and UI engineer building **FinGuard-X** from scratch.

**Protocol (mandatory):**
1. Work in **Planning mode**. Before each phase, write a short implementation plan and wait for approval.
2. Build **one phase at a time**. At the end of each phase, run the tests and the phase's **gate checks**, then write `docs/phase_N_report.md` (what was built, what was verified, known gaps, row counts, failures).
3. If a gate fails, fix it before moving on. Never skip ahead.
4. Prefer the simplest method that can be experimentally justified. No over-engineering.
5. Keep a `docs/DECISIONS.md` log of every non-obvious choice and why.

**FinGuard-X full title:**
"FinGuard-X: Explainable Multimodal Financial Statement Fraud Detection using Numeric, Textual and Related-Party Network Signals"

---

## 1. Non-negotiable rules

**R1. No fake data.** Never synthesize, simulate, hard-code or "fill in" companies, filings, financials, labels, entities, or metrics. If data is missing or extraction fails, log it, store a null with a reason code, and report it in the phase report. Unit-test fixtures may be tiny real excerpts clearly marked as fixtures.

**R2. Honest reporting.** Report all results, including negative ones. If multimodal fusion does not beat the numeric baseline, say so. Never tune on the test set. Never cherry-pick seeds.

**R3. No leakage.**
- Features for company-year (CIK, FY) may only use information available at that filing's date.
- Use values **as originally reported** in the filing for that fiscal year (use `accn` / `filed` in XBRL facts to pick the original filing's value, not later restated values).
- Enforcement dates and AAER text are used only to build labels, never as features.
- Prior-year features may use earlier filings only.

**R4. SEC compliance.** Declared User-Agent from env var `SEC_USER_AGENT` (app name + contact email). Max 5 requests/second (SEC cap is 10), retry with exponential backoff, local disk cache keyed by URL/accession, request log table. Never re-download a cached file. Prefer **SEC bulk files** (`companyfacts.zip`, `submissions.zip`, described on the SEC EDGAR APIs page) over per-company API calls. Per-filing document fetches are still required for MD&A / notes text.

**R5. Language.** The system never says "fraud detected" or "proof". Use: "Fraud Risk / Review Priority", "Potential inconsistency", "Unusual related-party network pattern", "Risk signal", "Requires review".

**R6. Reproducibility.** Python 3.11, pinned dependencies, global seed (`SEED=42`) used everywhere, deterministic splits, one command per pipeline stage (Makefile or `scripts/`), CPU-only (no GPU assumed), `.env.example` provided.

---

## 2. Scope: must-have vs stretch

**Must-have:** SEC ingestion (10-K), AAER labels + matched controls, financial features + Beneish (all 8 components), section extraction (MD&A, related-party note), narrative drift, related-party graph (NetworkX), FNCS, Models 1-9 ablation, SHAP explanations, FastAPI, React dashboard, tests, README + methodology doc.

**Stretch (only after everything above works):** 10-Q support, manual entity-correction UI, FinBERT upgrade, graph embeddings, PDF export of a company report.

**Out of scope (do not add):** blockchain, crypto, computer vision, LLM fine-tuning, multi-agent systems, Kubernetes, microservices, graph databases, GNNs, paid APIs.

---

## 3. Tech stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.x, Alembic migrations, Pydantic v2, PostgreSQL (local, with SQLite supported for local testing/dev flexibility)
- **Data/ML:** pandas, scikit-learn, XGBoost, SHAP, NetworkX, statsmodels
- **NLP:** spaCy (`en_core_web_sm`), `sentence-transformers` (`all-MiniLM-L6-v2` default, CPU), BeautifulSoup/lxml for filing HTML, textstat for readability, Loughran-McDonald word lists (sentiment/uncertainty; verify licence/availability and cite) as the baseline lexicon
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, Recharts (or similar), a graph viz lib such as react-force-graph or Cytoscape
- **Repo layout:**
```
finguard-x/
  backend/app/{api,core,db,ingest,features,nlp,graph,fncs,models,explain}/
  backend/tests/
  frontend/
  data/{raw,cache,processed}/      (gitignored)
  docs/
  scripts/
  Makefile  README.md  .env.example
```

---

## 4. Core design decisions (apply across phases)

### 4.1 Dataset
- Unit: **company-year** (CIK, fiscal year, 10-K accession).
- Fiscal-year range: **FY2010 to latest available** (XBRL coverage is sparse earlier). Document the exact range chosen.
- Start with a **pilot** (~200-300 companies incl. all positives that are resolvable), verify the whole pipeline, then scale up.
- Raw XBRL facts stored separately from normalized company-year features. Missing fields allowed; every feature has a null-reason or imputation flag. Handle tag variants (e.g. multiple revenue tags) through an explicit, documented tag-priority map.

### 4.2 Labels (AAER)
- Source: SEC AAER index and release documents. Optionally a published research AAER-to-misstatement-year dataset if it is publicly accessible; verify availability and licence, do not assume.
- Policy:
  - Positive (1) = company-year whose fiscal period is identified in the AAER as materially misstated / subject of the enforcement action.
  - Do NOT label a company positive merely because it appears in an AAER (e.g. auditors, third parties, unrelated mentions are excluded or flagged low confidence).
  - Store per label: company, CIK, AAER number, enforcement date, affected fiscal years, source URL, `label_confidence` (high/medium/low), `label_rationale`.
  - Years after the enforcement date for the same company are excluded from controls and from training (contaminated).
- Controls (0): same SIC 2-digit industry, same fiscal year, similar size (log total assets bucket), no AAER ever. Default ratio 1:5 matched; also keep an "all non-enforcement firms" variant for sensitivity analysis. Document the matching procedure and its limits.
- Output a label-quality report: counts by confidence, unresolved CIKs, years covered.

### 4.3 Narrative drift (Novelty 1)
- Sentence-segment MD&A (and separately the related-party note and risk factors) per filing; embed sentences; cache embeddings by text hash.
- Alignment: for each current-year sentence, take **best-match cosine similarity** to any previous-year sentence (and the reverse direction). 
- `NARRATIVE_DRIFT_SCORE` = 1 - mean(best-match similarity), symmetrized, in [0,1]. Also store the document-level mean-embedding cosine drift as a secondary feature.
- Store the **lowest-similarity current sentences with their nearest previous sentence** (the evidence snippets), plus section source location.
- Supporting features: vocabulary change (Jaccard / TF-IDF cosine), uncertainty-word rate, negative sentiment, financial-uncertainty rate, avg sentence length, readability (Flesch/Fog), conditional-language rate, passive-voice rate (spaCy dependency heuristic), numeric disclosure density.
- Large drift is a risk signal only, never "fraud".

### 4.4 Related-party graph (Novelty 2)
- Extraction from the related-party note: rule-based patterns + spaCy NER (ORG/PERSON), section-restricted. Capture amounts and currency where parseable.
- Entity normalization: lowercase, strip punctuation, unify suffixes (Ltd/Limited, Inc/Incorporated, Corp/Corporation, LLC, LP, Co), simple fuzzy match (rapidfuzz, high threshold). Store `raw_entity_name`, `normalized_entity_name`, `entity_type`, `confidence`.
- Node types: company, related_company, subsidiary, director, executive, vendor, customer, other_entity. Edge types: related_party, transaction, ownership, management_relationship. Each edge stores amount, currency, year, source accession, disclosure text reference, confidence.
- One NetworkX graph per company-year. Features: entity count, edge count, new entities, removed entities, degree centrality (max/mean), transaction concentration (HHI), largest transaction (and as % of revenue/assets where available), share of amount involving top-k entities, density (only where meaningful), network growth rate, YoY graph change (Jaccard on entity sets, change in edge count).
- `GRAPH_ANOMALY_SCORE` from interpretable feature combination (e.g. percentile-ranked sub-signals within industry-year, averaged), documented.
- **Extraction quality:** hand-label a sample of ~30 related-party notes (store in `data/gold/`) and report entity extraction precision/recall.
- **No-graph handling:** many filings will have no or tiny graphs. Add `graph_available` and `graph_size` flags; missing graph = zeros plus flag, never treated as an anomaly. Report % of company-years with usable graphs.
- UI wording: "Unusual related-party network pattern."

### 4.5 FNCS (Novelty 3, most important)
Seven categories: GROWTH, PROFITABILITY, LIQUIDITY, DEMAND, CASH_FLOW, RISK, OUTLOOK.

**Numeric side** - for each category compute `n_c` in [-1, 1] from mapped indicators, e.g.
- GROWTH: revenue growth, asset growth
- PROFITABILITY: net income growth, gross/operating margin change
- LIQUIDITY: current ratio change, debt change
- DEMAND: revenue growth, receivables growth relative to revenue
- CASH_FLOW: OCF growth, OCF/net income, accruals/assets
- RISK: leverage, debt-to-equity change
- OUTLOOK: composite trend of the above

Scale indicators with industry-year z-scores (winsorized) then `tanh`, so signals are comparable.

**Text side** - for each category compute `t_c` in [-1, 1] and a presence weight `w_c`:
1. Embed MD&A sentences.
2. Retrieve sentences relevant to each category by cosine similarity to a small, versioned set of **prototype sentences per category** (stored in `backend/app/fncs/prototypes.yaml`).
3. Score tone of retrieved sentences (financial-domain sentiment: Loughran-McDonald baseline; FinBERT or zero-shot NLI as stretch upgrade), with uncertainty/hedging penalty.
4. `t_c` = similarity-weighted mean tone; `w_c` = share of relevant sentences, capped.
Not keyword matching alone: retrieval is semantic, tone is lexicon/model-based.

**Combination**
- Gap `d_c = t_c - n_c`; category contradiction `x_c = w_c * max(0, |d_c| - tolerance)`, direction recorded (`narrative_more_positive` or `narrative_more_negative`; the first is weighted higher).
- `NUMERIC_TEXT_CONTRADICTION_SCORE` = weighted mean of `x_c` scaled to [0,1].
- `FNCS` = 1 - contradiction score (1 = consistent, 0 = strongly inconsistent). Also output per-category scores.
- Explicit rule-based "red-flag pattern" features (e.g. revenue up, receivables up much faster, OCF down, with positive tone) as additional interpretable indicators.
- Explanation templates produce sentences such as: "Potential inconsistency detected because revenue increased strongly while operating cash flow declined and receivables increased substantially." Always show the contributing numbers and the supporting text snippets.
- Weights, tolerance and prototypes are fixed from design reasoning or training folds only, never tuned on the test fold.

**Redundancy check (required):** FNCS is derived from features already in Model 8. Show whether it adds value: (a) Model 9 vs Model 8 with paired bootstrap CI on the PR-AUC/ROC-AUC difference, (b) FNCS-alone performance, (c) correlation of FNCS with its constituent features, (d) permutation-importance of FNCS in Model 9.

### 4.6 Models and evaluation
- Models: Logistic Regression (scaled, class-weighted), Random Forest (class-weighted), XGBoost (`scale_pos_weight`).
- **Ablation (all nine):**
  1. Beneish M-Score baseline (raw score as ranking for PR/ROC-AUC; also thresholds -1.78 and -2.22 for P/R/F1)
  2. Numeric-only
  3. Text-only
  4. Graph-only
  5. Numeric + Text
  6. Numeric + Graph
  7. Text + Graph
  8. Numeric + Text + Graph
  9. Numeric + Text + Graph + FNCS  **(proposed)**
- **Splitting:** time-aware **rolling-origin** evaluation (train on years <= T, validate T+1, test T+2, rolled forward), AND **grouped-by-CIK** splits so no company appears in both train and test. Report the number of positives and negatives in every fold. If the test set has too few positives, say so and rely on pooled out-of-fold results.
- **Uncertainty:** cluster bootstrap by CIK (1,000 resamples) for 95% CIs on PR-AUC, ROC-AUC, F1; paired bootstrap for model-vs-model differences.
- **Metrics:** Precision, Recall, F1, PR-AUC (primary), ROC-AUC, Balanced Accuracy, Confusion Matrix. Never report accuracy. Choose thresholds on validation data only.
- **Calibration:** calibrate (Platt/isotonic on validation). `fraud_probability` = calibrated probability. `risk_score` = `round(100 * fraud_probability)`. Document that probabilities reflect the matched-sample prior, not the real-world base rate.
- Risk categories: 0-29 Low, 30-59 Moderate, 60-79 High, 80-100 Very High. Always labelled "Fraud Risk / Review Priority".
- Persist every run in `model_runs`, `model_predictions`, `experiments` with config hash, seed, data version.

### 4.7 Explainability
- SHAP for tree models (and coefficients for logistic regression).
- Group SHAP values by modality: numeric, text, graph, FNCS. Output top contributors per modality in plain language, e.g. "+18 Receivables growth anomaly".
- Store in `explanations`; every explanation includes the supporting snippets/edges/values.

### 4.8 Database
PostgreSQL via Alembic. Tables: `companies, filings, financial_facts, financial_features, beneish_scores, filing_sections, text_features, text_embeddings, related_entities, related_transactions, graph_features, fraud_labels, model_runs, model_predictions, explanations, experiments, request_log`. Indexes on company_id, CIK, fiscal_year, accession_number, filing_date. Do not duplicate large raw text; store raw HTML on disk with a path/hash reference, and `clean_text` in `filing_sections` with `section_id, company_id, fiscal_year, section_type, raw_text (or ref), clean_text, source_location`.
