# FinGuard-X Architecture & Technical Decisions Log

This log records every non-obvious choice, design trade-off, rationale, and date for FinGuard-X.

| Date | ID | Decision | Rationale | Alternatives Considered |
|---|---|---|---|---|
| 2026-10-07 | DEC-001 | Python 3.11 Environment Setup | Python 3.11 is specified in R6 for reproducibility, compatible with PyTorch/SentenceTransformers CPU and spaCy. | Python 3.12 (potential package compatibility hiccups with older ML libraries). |
| 2026-10-07 | DEC-002 | PostgreSQL Dedicated Test Database | Tests run against a dedicated real PostgreSQL test database (`finguard_test`) ensuring 100% parity with production DDL and PostgreSQL-specific features. | SQLite in-memory fallback (can hide dialect-specific differences like types and constraints). |
| 2026-10-07 | DEC-003 | Cross-Platform Task Automation | Make is provided for Linux/CI, while `scripts/run_pipeline.py` provides a native Python CLI runner that executes on Windows PowerShell without requiring GNU Make. | Relying solely on GNU Make on Windows. |
| 2026-10-07 | DEC-004 | Lazy SEC User-Agent Validation | SEC User-Agent compliance is validated lazily when SEC client network operations are called, rather than at module import, allowing database migrations, tests, and offline ML to run without network credentials. | Strict validation at `Settings` import time. |
| 2026-10-07 | DEC-005 | Tracking `data/gold/` in Git | Hand-labeled gold evaluation sets (e.g., related-party entity extraction benchmarks) must be tracked for reproducibility, while raw, cache, and processed data remain gitignored. | Gitignoring all data/ folders. |
| 2026-10-07 | DEC-006 | Alembic Settings Integration | Alembic `env.py` dynamically imports `get_settings()` from `backend.app.core.config`, ensuring single source of truth for database URLs with override support. | Hardcoded database URLs in `alembic.ini`. |
