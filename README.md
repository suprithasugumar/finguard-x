# FinGuard-X

**FinGuard-X: Explainable Multimodal Financial Statement Fraud Detection using Numeric, Textual and Related-Party Network Signals**

FinGuard-X is an enterprise-grade multimodal research and detection system designed to identify financial statement manipulation and reporting anomalies using SEC EDGAR filings. The architecture integrates three distinct modalities:
1. **Numeric Financial Signals:** 18 fundamental growth/ratio metrics and all 8 Beneish M-Score components.
2. **Textual Narrative Signals:** MD&A semantic sentence alignment, sentiment, uncertainty, and narrative drift.
3. **Related-Party Network Signals:** NetworkX entity-relationship graphs and structural anomaly indicators.
4. **Financial Narrative Contradiction Score (FNCS):** Cross-modal contradiction detection contrasting numeric trends against MD&A sentiment tone across 7 fundamental financial categories.

---

## 1. Prerequisites

- **Python:** 3.11 (`py -3.11` on Windows or `python3.11` on Linux/macOS)
- **Database:** PostgreSQL (local instance or Docker container)
- **Node.js:** v18+ (for frontend dashboard in Phase 9)

---

## 2. Quickstart & Setup

### Clone and Environment Setup
```bash
# 1. Create Python 3.11 virtual environment
py -3.11 -m venv .venv

# 2. Activate environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# 3. Install pinned dependencies
pip install -r requirements.txt
```

### Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Update `.env` with your settings:
```ini
# SEC EDGAR Compliance (R4): Declare App Name + Contact Email
SEC_USER_AGENT=FinGuardX-Research/1.0 (researcher@university.edu)

# PostgreSQL Databases
DATABASE_URL=postgresql://user:password@localhost:5432/finguard
TEST_DATABASE_URL=postgresql://user:password@localhost:5432/finguard_test

# Reproducibility (R6)
SEED=42
```

---

## 3. Database Migrations

FinGuard-X uses Alembic migrations that dynamically read the connection string from application settings.

```bash
# Run migrations using the cross-platform CLI runner:
python scripts/run_pipeline.py migrate

# Or using Make (Linux/macOS):
make migrate
```

---

## 4. Running Tests & Quality Checks

Tests run against a real PostgreSQL test database (`finguard_test`) verifying schema constraints, relationships, seed determinism, and Alembic downgrade/upgrade round-trips.

```bash
# Run pytest with code coverage
python scripts/run_pipeline.py test

# Run ruff code linter
python scripts/run_pipeline.py lint

# Auto-format codebase
python scripts/run_pipeline.py format

# Check environment status and DB connectivity
python scripts/run_pipeline.py status
```

---

## 5. Repository Structure

```
finguard-x/
  backend/
    app/
      core/          # Settings, logging, seed determinism
      db/            # SQLAlchemy 2.0 Base, engine, models (Company, Filing, RequestLog)
      ingest/        # SEC EDGAR ingestion & AAER labels (Phase 1)
      features/      # Financial ratios & Beneish M-Score (Phase 2)
      nlp/           # Filing HTML parser & narrative drift (Phase 3)
      graph/         # Related-party network extraction (Phase 4)
      fncs/          # Financial Narrative Contradiction Score (Phase 5)
      models/        # Multimodal Models 1-9 & rolling-origin splits (Phase 6)
      explain/       # SHAP modality factor decomposition (Phase 7)
      api/           # FastAPI application endpoints (Phase 8)
    alembic/         # Database migrations
    tests/           # Pytest test suite (100% PostgreSQL tested)
  data/
    gold/            # Hand-labeled gold standards (tracked in git)
    raw/             # Raw SEC downloads (gitignored)
    cache/           # Local disk cache (gitignored)
    processed/       # Normalized datasets (gitignored)
  docs/              # Phase gate reports, DECISIONS.md, and specs
  frontend/          # React research dashboard (Phase 9)
  logs/              # Structured runtime logs (gitignored)
  scripts/           # CLI automation runners
  Makefile           # Automation targets
  PROJECT_SPEC.md    # Master build specification
```

---

## 6. Non-Negotiable Operational Rules

- **R1. No fake data:** All datasets, filings, and labels are sourced directly from SEC EDGAR and official SEC AAER releases.
- **R2. Honest reporting:** All experiments report negative results, confidence intervals, and limitations.
- **R3. No leakage:** Strictly as-originally-reported XBRL facts; temporal boundaries strictly preserved.
- **R4. SEC compliance:** Max 5 req/s, declared `SEC_USER_AGENT`, disk cache keyed by accession/URL.
- **R5. Language standards:** System outputs "Fraud Risk / Review Priority" or "Risk signal", never definitive accusations.
- **R6. Reproducibility:** Fixed `SEED=42`, pinned dependency lockfile, deterministic time-aware splits.
