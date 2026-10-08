"""Test database vs dashboard stats reconciliation (Task T1).

Enforces that every number in the dataset stats endpoint matches a direct database query,
and that cohort counts and risk-bucket counts satisfy exact sum identities.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app.core.config import Settings
from backend.app.main import app


def test_dashboard_stats_match_database_queries():
    """Verify 100% agreement between /api/dataset/stats and PostgreSQL direct queries."""
    client = TestClient(app)
    resp = client.get("/api/dataset/stats")
    assert resp.status_code == 200
    stats = resp.json()

    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        db_companies = conn.execute(text("SELECT count(*) FROM companies")).scalar()
        db_filings = conn.execute(text("SELECT count(*) FROM filings")).scalar()
        db_facts = conn.execute(text("SELECT count(*) FROM financial_facts")).scalar()
        db_sections = conn.execute(text("SELECT count(*) FROM filing_sections")).scalar()

        db_cohort = conn.execute(text("SELECT count(*) FROM company_year_labels")).scalar()
        db_pos_records = conn.execute(
            text("SELECT count(*) FROM company_year_labels WHERE label = 1")
        ).scalar()
        db_ctrl_records = conn.execute(
            text("SELECT count(*) FROM company_year_labels WHERE label = 0")
        ).scalar()
        db_pos_ciks = conn.execute(
            text("SELECT count(DISTINCT cik) FROM company_year_labels WHERE label = 1")
        ).scalar()
        db_ctrl_ciks = conn.execute(
            text("SELECT count(DISTINCT cik) FROM company_year_labels WHERE label = 0")
        ).scalar()

        db_risk_rows = conn.execute(
            text(
                "SELECT risk_category, count(*) FROM company_year_explanations GROUP BY risk_category"
            )
        ).fetchall()
        db_risk_dist = {r[0]: r[1] for r in db_risk_rows}

    # 1. Database level exact matches
    assert stats["database"]["total_companies"] == db_companies
    assert stats["database"]["total_filings"] == db_filings
    assert stats["database"]["total_financial_facts"] == db_facts
    assert stats["database"]["total_sections"] == db_sections

    # 2. Cohort count exact matches
    assert stats["cohort"]["total_records"] == db_cohort
    assert stats["cohort"]["positive_records"] == db_pos_records
    assert stats["cohort"]["control_records"] == db_ctrl_records
    assert stats["cohort"]["unique_positives"] == db_pos_ciks
    assert stats["cohort"]["unique_controls"] == db_ctrl_ciks

    # 3. Sum identity: positives + controls == total
    assert (
        stats["cohort"]["positive_records"] + stats["cohort"]["control_records"]
        == stats["cohort"]["total_records"]
    )

    # 4. Sum identity: risk buckets sum to total cohort
    risk_sum = sum(stats["risk_distribution"].values())
    assert risk_sum == stats["cohort"]["total_records"], (
        f"Risk bucket sum ({risk_sum}) does not match cohort total ({stats['cohort']['total_records']})"
    )

    # 5. Risk distribution matches DB exactly
    for cat, count in db_risk_dist.items():
        assert stats["risk_distribution"].get(cat) == count


def test_models_results_endpoint_reads_artifact():
    """Verify /api/models/results returns valid ablation data matching the pipeline output."""
    client = TestClient(app)
    resp = client.get("/api/models/results")
    assert resp.status_code == 200
    data = resp.json()

    assert "models" in data
    assert len(data["models"]) >= 9
    m1 = next((m for m in data["models"] if m["model_id"] == 1), None)
    assert m1 is not None
    assert m1["f1"] == 0.07547169811320754 or round(m1["f1"], 4) == 0.0755
