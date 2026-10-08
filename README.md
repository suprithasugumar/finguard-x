# FinGuard-X: Explainable Multimodal Financial Statement Fraud Detection

**FinGuard-X** is an enterprise-grade multimodal research and detection system designed to identify financial statement manipulation and reporting anomalies using authentic SEC EDGAR filings and official SEC Accounting and Auditing Enforcement Releases (AAERs).

The architecture integrates four distinct analytical modalities:
1. **Numeric Financial Signals:** 18 fundamental growth/ratio metrics and all 8 Beneish M-Score components.
2. **Textual Narrative Signals:** MD&A semantic sentence alignment, sentiment, uncertainty, and semantic narrative drift across consecutive years.
3. **Related-Party Network Signals:** NetworkX entity-relationship graphs, topological clustering, shell entity ratios, and YoY structural churn.
4. **Financial-Narrative Contradiction Score (FNCS):** Cross-modal contradiction detection contrasting numeric trends against MD&A sentiment tone across 7 fundamental accounting categories.

---

## 1. Quickstart & Setup

### Prerequisites
- **Python:** 3.11 (`py -3.11` on Windows or `python3.11` on Linux/macOS)
- **Database:** PostgreSQL 15+ (local instance or Docker container)
- **Node.js:** v18+ with `npm` (for React forensic dashboard)

### Clone & Python Virtual Environment
```bash
# 1. Clone repository
git clone https://github.com/suprithasugumar/finguard-x.git
cd finguard-x

# 2. Create Python 3.11 virtual environment
py -3.11 -m venv .venv

# 3. Activate environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
```

### Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure your `.env` contains valid credentials and compliance declarations:
```ini
# SEC EDGAR Compliance (R4): Declare App Name + Contact Email
SEC_USER_AGENT=FinGuardX-Research/1.0 (researcher@university.edu)

# PostgreSQL Databases
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/finguard
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/finguard_test

# Reproducibility (R6)
SEED=42
```

---

## 2. One-Command End-to-End Pipeline

To execute the entire multi-modal pipeline from provenance verification to TreeSHAP explanation generation in a single command:

```bash
python scripts/run_pipeline.py pipeline
```

This sequentially executes:
1. **Provenance Guard**: Audits database rows against raw SEC bulk archives (`companyfacts.zip`, `submissions.zip`).
2. **Alembic Migrations**: Applies all database schema migrations up to head (`001` through `005`).
3. **Stage 1 (Graph)**: Extracts related-party entities, builds NetworkX graphs, computes topological features, and flags anomalies.
4. **Stage 2 (FNCS)**: Computes 7-category numeric z-scores, MiniLM tone, and cross-modal contradiction scores.
5. **Stage 3 (Models & Ablation)**: Executes 5-fold CIK-grouped stratified CV across Models 1–9 with 300 bootstrap resamples.
6. **Stage 4 (TreeSHAP Explanations)**: Generates modality-decomposed SHAP attributions, calibrated 0–100 risk scores, and plain-language summaries.

---

## 3. Individual Execution Order

If executing stages individually:

```bash
# Step 1: Pre-flight Provenance Audit (Mandatory Gate)
python scripts/run_pipeline.py guard

# Step 2: Database Schema Migration
python scripts/run_pipeline.py migrate head

# Step 3: Populate Related-Party Knowledge Graphs (Stage 1)
python scripts/populate_graph_features.py

# Step 4: Populate Financial-Narrative Contradiction Scores (Stage 2)
python scripts/populate_fncs_features.py

# Step 5: Train Models 1-9 & Run Multimodal Ablation (Stage 3)
python backend/app/models/train_ablation.py

# Step 6: Generate TreeSHAP Attributions & Risk Scores (Stage 4)
python scripts/populate_explanations.py
```

---

## 4. Serving the API & Forensic Dashboard

### FastAPI Backend
Start the REST API server:
```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```
API documentation (Swagger UI) is available at: `http://127.0.0.1:8000/docs`

Key API Endpoints:
- `GET /api/dataset/stats`: Database and evaluation cohort summary metrics.
- `GET /api/models/results`: Models 1–9 ablation metrics with 95% bootstrap CIs and confusion matrices.
- `GET /api/companies`: Registrant directory with search, ticker, and risk classification filters.
- `GET /api/companies/{cik}/risk`: Historical risk score progression, priority level, and modal breakdown.
- `GET /api/companies/{cik}/financials`: Raw accounting facts and 8 Beneish M-Score component ratios.
- `GET /api/companies/{cik}/narrative`: Semantic drift score and top drifted sentence pairs.
- `GET /api/companies/{cik}/graph`: Knowledge graph nodes, edges, shell entity ratio, and topological metrics.
- `GET /api/companies/{cik}/explanation`: TreeSHAP modal attributions, top drivers, and grounded plain-language review summary.

### React + Vite Forensic Dashboard (UI)
The production bundle is pre-built in `frontend/dist` and served directly from the FastAPI root at `http://127.0.0.1:8000/`.

For frontend development with hot module reloading:
```bash
cd frontend
npm install
npm run dev
```
Access the Vite dev interface at `http://localhost:5173/`.

---

## 5. Multi-Modal Ablation Benchmark Results

Evaluated across **1,106 company-years** (185 AAER corporate positives, 921 matched controls) using primary time-aware held-out evaluation (FY2021–FY2023 test) and secondary 5-fold CIK-grouped stratified cross-validation ($B=2000$ CIK-cluster bootstrap resamples):

### Primary Time-Aware Held-Out Evaluation (Test Set FY2021–FY2023)
*Prevalence (Random-Guess PR-AUC Baseline): **16.89%***

| Model Architecture | Features | Best Val Classifier | Test PR-AUC | Baseline | Test ROC-AUC | F1-Score | Brier Score |
|---|---|---|---|---|---|---|---|
| **M1: Beneish M-Score Baseline** | 1 | Rule-based | 0.1716 | 0.1689 | 0.4377 | 0.1311 | 0.2032 |
| **M2: Numeric-only** | 21 | XGBoost | 0.2220 | 0.1689 | 0.5502 | 0.1538 | 0.1627 |
| **M3: Text-only** | 8 | RandomForest | 0.2025 | 0.1689 | 0.5642 | 0.0476 | 0.1473 |
| **M4: Graph-only** | 15 | XGBoost | 0.1746 | 0.1689 | 0.5112 | 0.2845 | 0.1449 |
| **M5: Numeric + Text** | 29 | XGBoost | 0.2027 | 0.1689 | 0.5287 | 0.1224 | 0.1647 |
| **M6: Numeric + Graph** | 36 | XGBoost | 0.2251 | 0.1689 | 0.5443 | 0.1633 | 0.1612 |
| **M7: Text + Graph** | 23 | RandomForest | 0.1756 | 0.1689 | 0.5157 | 0.0000 | 0.1634 |
| **M8: Numeric + Text + Graph** | 44 | LogReg | 0.2533 | 0.1689 | 0.5670 | 0.2366 | 0.1484 |
| **M9: Numeric + Text + Graph + FNCS** | 53 | LogReg | 0.2592 | 0.1689 | 0.5602 | 0.2366 | 0.1487 |
| **M10: FNCS-alone (Extra)** | 9 | XGBoost | 0.1851 | 0.1689 | 0.5367 | 0.0714 | 0.1760 |

### Honest Statistical Significance & Hypotheses ($B=2000$ CIK-Cluster Bootstrap)
*Pairwise comparisons of Model 9 (Full Multimodal) against baselines with Holm-Bonferroni correction:*

| Comparison | Metric | Mean Difference | 95% Bootstrap CI | Raw p | Adjusted p (Holm) | Empirical Conclusion |
|---|---|---|---|---|---|---|
| M9 vs M8 (No FNCS) | PR-AUC | -0.0094 | [-0.0201, +0.0005] | 0.9705 | 1.0000 | no evidence for improvement |
| M9 vs M2 (Numeric-Only) | PR-AUC | -0.0045 | [-0.0161, +0.0062] | 0.8035 | 1.0000 | no evidence for improvement |
| M9 vs M1 (Beneish Baseline) | PR-AUC | -0.0126 | [-0.0584, +0.0287] | 0.7015 | 1.0000 | no evidence for improvement |

*Plain statement on multimodal fusion:* Empirical evidence indicates that multimodal fusion did **not** achieve a statistically significant improvement over strong numeric-only baselines (mean $\Delta = -0.0045$, adjusted $p = 1.0000$). Financial accounting ratios remain the primary predictive signal for reporting misstatements.


---

## 6. Verification & Quality Assurance

```bash
# Run pytest suite against PostgreSQL test database
python scripts/run_pipeline.py test

# Run ruff code linter
python scripts/run_pipeline.py lint

# Verify database connection and seed determinism
python scripts/run_pipeline.py status
```

---

## 7. Operational Standards & Governance

FinGuard-X is governed by 6 mandatory operating rules:
- **R1. No fake data:** All datasets, filings, and labels trace directly to authentic SEC EDGAR archives and AAER releases. ProvenanceGuard enforces this before any analytical execution.
- **R2. Honest reporting:** Negative results, wide bootstrap confidence intervals, and benchmark gaps are documented transparently.
- **R3. No temporal leakage:** XBRL facts use strictly as-originally-reported values; preprocessors (imputation, winsorization, scaling) fit strictly inside training folds.
- **R4. SEC EDGAR compliance:** Requests are limited to 5 req/s with declared contact headers and disk caching.
- **R5. Language standards:** System outputs are strictly labeled **"Fraud Risk / Review Priority"**, never legal proof or accusations.
- **R6. Reproducibility:** Global seed is fixed (`SEED=42`) with full environment dependency lockfile.

For methodological constraints, refer to [docs/LIMITATIONS.md](file:///c:/Users/RITHIKESH%20S/finguard-x/docs/LIMITATIONS.md).
