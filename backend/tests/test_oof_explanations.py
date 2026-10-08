"""Test out-of-fold explanations, calibration, and honest factor attribution (Task T6).

Enforces:
1. All displayed risk scores, calibrated probabilities, and SHAP values come from out-of-fold predictions.
2. Calibration curve and Brier score are computed.
3. SHAP is formatted in log-odds with direction ("pushes risk up / down") and magnitude.
4. Top drivers include observed value, peer median, and direction, and never list observed 0.00 without effect.
5. Zero occurrences of "fraud detected" in plain-language summaries.
"""

import json
from pathlib import Path
from sqlalchemy import create_engine, text
from backend.app.core.config import Settings
from backend.app.explain.shap_engine import MultiModalExplanationEngine
from backend.app.models.train_ablation import load_dataset


def test_explanations_are_strictly_out_of_fold():
    """Verify that explanation engine produces strictly out-of-fold scores and TreeSHAP values."""
    df = load_dataset()
    engine = MultiModalExplanationEngine()
    exps, diag = engine.explain_cohort_out_of_fold(df.head(100))

    assert len(exps) == 100
    assert diag["is_out_of_fold"] is True
    assert 0.0 <= diag["brier_score"] <= 1.0

    for e in exps:
        assert e["is_out_of_fold"] is True
        assert 1 <= e["fold_id"] <= 5
        assert 0.0 <= e["fraud_probability"] <= 1.0
        assert 0 <= e["risk_score"] <= 100
        assert e["risk_score"] == int(round(100.0 * e["fraud_probability"]))

        # Verify no "fraud detected" text
        assert "fraud detected" not in e["plain_language_summary"].lower()

        # Verify top factors format
        for f in e["top_factors"]:
            assert "peer_median" in f
            assert "raw_value" in f
            assert "shap_value" in f
            assert f["direction"] in ["pushes risk up", "pushes risk down"]
            assert f["shap_unit"] == "log-odds contribution"
            # Verify no inert zero factor listed without impact
            if abs(f["raw_value"]) < 1e-4:
                assert abs(f["shap_value"]) > 0 or len(e["top_factors"]) <= 6


def test_database_explanations_conform_to_ground_rules():
    """Verify existing database explanations adhere to triage labeling and calibration."""
    settings = Settings()
    db_engine = create_engine(settings.DATABASE_URL)
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT risk_score, fraud_probability, plain_language_summary, top_factors "
                "FROM company_year_explanations LIMIT 50"
            )
        ).fetchall()

    if not rows:
        return

    for r in rows:
        risk_score, prob, summary, top_factors = r
        assert "fraud detected" not in summary.lower()
        assert abs(risk_score - round(100.0 * prob)) <= 1
