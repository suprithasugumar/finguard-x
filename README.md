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

Evaluated across 500 company-years (80 AAER corporate positives, 420 matched controls) using 5-fold CIK-grouped stratified cross-validation and 300 CIK-cluster bootstrap resamples:

| Model | Modalities Included | Features | Classifier | PR-AUC (95% CI) | ROC-AUC (95% CI) | F1-Score | Balanced Acc |
|---|---|---|---|---|---|---|---|
| **M1: Baseline** | Beneish M-Score Only | 8 | LogReg | 0.1537 [0.124, 0.207] | 0.4377 [0.366, 0.505] | 0.2974 | 0.4798 |
| **M2: Numeric Full** | Numeric + Beneish | 26 | LogReg | 0.1873 [0.142, 0.252] | 0.5484 [0.478, 0.618] | 0.3158 | 0.5369 |
| **M3: Text Alone** | Text Drift & Sentiment | 11 | LogReg | 0.1741 [0.134, 0.229] | 0.5332 [0.457, 0.603] | 0.3065 | 0.5286 |
| **M4: Graph Alone** | Related-Party Network | 12 | LogReg | 0.1654 [0.130, 0.218] | 0.5039 [0.435, 0.575] | 0.2936 | 0.5036 |
| **M5: FNCS Alone** | Cross-Modal Contradiction | 22 | LogReg | 0.2299 [0.173, 0.309] | 0.5960 [0.528, 0.665] | 0.3540 | 0.5702 |
| **M6: Num + Text** | Numeric + Text Drift | 37 | XGBoost | 0.1834 [0.137, 0.247] | 0.5256 [0.450, 0.598] | 0.3023 | 0.5190 |
| **M7: Num + Graph** | Numeric + Graph Metrics | 38 | XGBoost | 0.1622 [0.126, 0.218] | 0.4907 [0.418, 0.563] | 0.2885 | 0.4917 |
| **M8: Num + Txt + Grp** | Tri-Modal Combination | 49 | XGBoost | 0.1669 [0.128, 0.228] | 0.5339 [0.461, 0.604] | 0.2872 | 0.5274 |
| **M9: Full System** | All 4 Modalities (+ FNCS) | 71 | XGBoost | **0.2240 [0.166, 0.305]** | **0.6024 [0.534, 0.670]** | **0.3478** | **0.5786** |

**Statistical Significance**:
Paired bootstrap test between Model 9 (Full System) and Model 8 (Tri-Modal without FNCS):
- $\Delta\text{PR-AUC} = +0.0571$ ($p < 0.0001$)
- $\Delta\text{ROC-AUC} = +0.0685$ ($p = 0.0133$)

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
