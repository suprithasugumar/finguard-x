"""Populate multi-modal TreeSHAP explanations and calibrated risk scores for all 500 cohort company-years (Stage 4)."""
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.core.config import Settings
from backend.app.db.models.explain import CompanyYearExplanation
from backend.app.explain.shap_engine import MultiModalExplanationEngine
from backend.app.models.train_ablation import load_dataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("finguard.stage4.explanations")


def populate_explanations():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)

    logger.info("Initializing Stage 4: SHAP Explanations Population...")
    df = load_dataset()

    # Compute strictly out-of-fold explanations via 5-fold CIK-grouped cross validation
    explain_engine = MultiModalExplanationEngine()
    logger.info("Computing strictly OUT-OF-FOLD TreeSHAP attributions and calibrated risk scores...")
    raw_explanations, cal_diag = explain_engine.explain_cohort_out_of_fold(df)
    logger.info(
        f"Generated {len(raw_explanations)} out-of-fold explanations. "
        f"Brier score: {cal_diag['brier_score']}"
    )

    # Save calibration diagnostics
    diag_path = Path("data/processed/calibration_diagnostics.json")
    diag_path.parent.mkdir(parents=True, exist_ok=True)
    with open(diag_path, "w", encoding="utf-8") as f:
        json.dump(cal_diag, f, indent=2)

    with Session(engine) as session:
        # Load evidence snippets from filing_nlp_features
        nlp_rows = session.execute(
            text("SELECT cik, fiscal_year, drift_evidence_snippets FROM filing_nlp_features")
        ).fetchall()
        nlp_snippets_map = {(r[0], r[1]): r[2] for r in nlp_rows}

        # Load evidence edges from company_year_graph_features
        graph_rows = session.execute(
            text("SELECT cik, fiscal_year, evidence_edges FROM company_year_graph_features")
        ).fetchall()
        graph_edges_map = {(r[0], r[1]): r[2] for r in graph_rows}

        # Load FNCS evidence from company_year_fncs_features
        fncs_rows = session.execute(
            text("SELECT cik, fiscal_year, fncs_evidence FROM company_year_fncs_features")
        ).fetchall()
        fncs_evidence_map = {(r[0], r[1]): r[2] for r in fncs_rows}

        # Load filing IDs
        filing_rows = session.execute(
            text("SELECT cik, fiscal_year, id, accession_number FROM filings WHERE form_type = '10-K'")
        ).fetchall()
        filing_map = {(r[0], r[1]): (r[2], r[3]) for r in filing_rows}

        # Clear existing explanations
        session.execute(text("DELETE FROM company_year_explanations"))
        session.commit()

        batch_to_insert = []
        category_counts = Counter()
        real_samples = []

        for exp in raw_explanations:
            cik = exp["cik"]
            fy = exp["fiscal_year"]

            f_id, acc = filing_map.get((cik, fy), (None, exp.get("accession_number", "")))
            snippets = nlp_snippets_map.get((cik, fy), [])
            edges = graph_edges_map.get((cik, fy), [])
            fncs_ev = fncs_evidence_map.get((cik, fy), {})

            category = exp["risk_category"]
            category_counts[category] += 1

            if len(real_samples) < 4 and exp["risk_score"] >= 60:
                real_samples.append({
                    "cik": cik,
                    "fiscal_year": fy,
                    "risk_score": exp["risk_score"],
                    "risk_category": category,
                    "summary": exp["plain_language_summary"],
                    "top_factor": exp["top_factors"][0]["plain_language"] if exp["top_factors"] else "N/A",
                })

            rec = CompanyYearExplanation(
                filing_id=f_id,
                cik=cik,
                fiscal_year=fy,
                accession_number=acc,
                fraud_probability=exp["fraud_probability"],
                risk_score=exp["risk_score"],
                risk_category=category,
                review_priority_label=exp["review_priority_label"],
                modality_breakdown=exp["modality_breakdown"],
                top_factors=exp["top_factors"],
                plain_language_summary=exp["plain_language_summary"],
                evidence_snippets=snippets,
                evidence_edges=edges,
                fncs_evidence=fncs_ev,
            )
            batch_to_insert.append(rec)

        session.add_all(batch_to_insert)
        session.commit()

        logger.info("Stage 4 Explanations Population Complete!")
        logger.info(f"Total cohort company-years explained: {len(batch_to_insert)}")
        logger.info(f"Risk Category Distribution: {dict(category_counts)}")
        logger.info("--- HIGH REVIEW PRIORITY REAL EXAMPLES ---")
        for i, ex in enumerate(real_samples[:3], 1):
            logger.info(
                f"Example {i}: CIK {ex['cik']} (FY{ex['fiscal_year']}) | Score={ex['risk_score']}/100 ({ex['risk_category']})\n"
                f"  Top Factor: {ex['top_factor']}\n"
                f"  Summary: {ex['summary']}\n"
            )

        summary = {
            "total_explained": len(batch_to_insert),
            "distribution": dict(category_counts),
            "samples": real_samples[:3],
        }
        with open("data/processed/stage4_explanations_summary.json", "w") as f:
            json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    populate_explanations()
