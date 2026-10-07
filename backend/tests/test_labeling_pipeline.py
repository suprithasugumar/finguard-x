"""Tests for LabelingPipeline manual overrides and execution."""

import csv
from datetime import date

from backend.app.db.models.entities import (
    AAERCase,
    Company,
    Filing,
    FinancialFact,
)
from backend.app.ingest.labeling_pipeline import LabelingPipeline


def test_labeling_pipeline_execution_and_overrides(tmp_path, db_session):
    """Verify that LabelingPipeline processes positives, matches controls, and respects manual overrides."""
    pipeline = LabelingPipeline(seed=42)
    pipeline.review_csv_path = tmp_path / "label_review.csv"

    # Setup 1 positive company and 5 control companies
    pos_comp = Company(cik="0000885590", name="Valeant Inc", sic="2834")
    db_session.add(pos_comp)
    db_session.flush()

    # Filings for positive: FY2015 and FY2014
    f1 = Filing(
        company_id=pos_comp.id,
        cik=pos_comp.cik,
        accession_number="0000885590-15-000010",
        fiscal_year=2015,
        filing_date=date(2016, 2, 1),
        period_end=date(2015, 12, 31),
    )
    f0 = Filing(
        company_id=pos_comp.id,
        cik=pos_comp.cik,
        accession_number="0000885590-14-000010",
        fiscal_year=2014,
        filing_date=date(2015, 2, 1),
        period_end=date(2014, 12, 31),
    )
    db_session.add_all([f1, f0])

    # Facts for positive
    p_ast = FinancialFact(
        cik=pos_comp.cik,
        tag="Assets",
        value=10000000.0,
        period_end=date(2015, 12, 31),
        fiscal_year=2015,
        accession_number=f1.accession_number,
        filed_date=f1.filing_date,
        is_original_filing=True,
    )
    p_rev = FinancialFact(
        cik=pos_comp.cik,
        tag="Revenues",
        value=5000000.0,
        period_end=date(2015, 12, 31),
        fiscal_year=2015,
        accession_number=f1.accession_number,
        filed_date=f1.filing_date,
        is_original_filing=True,
    )
    db_session.add_all([p_ast, p_rev])

    # AAER case
    case = AAERCase(
        aaer_number="AAER-4134",
        release_date=date(2020, 7, 31),
        enforcement_date=date(2020, 7, 31),
        company_name=pos_comp.name,
        cik=pos_comp.cik,
        affected_fiscal_years=[2015],
        source_url="https://sec.gov/test.pdf",
    )
    db_session.add(case)

    # 5 controls in SIC 2834
    for i in range(5):
        c_cik = f"000007800{i}"
        comp = Company(cik=c_cik, name=f"Control Pharma {i}", sic="2834")
        db_session.add(comp)
        db_session.flush()

        cf1 = Filing(
            company_id=comp.id,
            cik=c_cik,
            accession_number=f"{c_cik}-15-000010",
            fiscal_year=2015,
            filing_date=date(2016, 2, 1),
            period_end=date(2015, 12, 31),
        )
        cf0 = Filing(
            company_id=comp.id,
            cik=c_cik,
            accession_number=f"{c_cik}-14-000010",
            fiscal_year=2014,
            filing_date=date(2015, 2, 1),
            period_end=date(2014, 12, 31),
        )
        db_session.add_all([cf1, cf0])

        c_ast = FinancialFact(
            cik=c_cik,
            tag="Assets",
            value=float((i + 1) * 8000000),
            period_end=date(2015, 12, 31),
            fiscal_year=2015,
            accession_number=cf1.accession_number,
            filed_date=cf1.filing_date,
            is_original_filing=True,
        )
        c_rev = FinancialFact(
            cik=c_cik,
            tag="Revenues",
            value=4000000.0,
            period_end=date(2015, 12, 31),
            fiscal_year=2015,
            accession_number=cf1.accession_number,
            filed_date=cf1.filing_date,
            is_original_filing=True,
        )
        db_session.add_all([c_ast, c_rev])

    db_session.flush()

    # Execute labeling
    stats = pipeline.execute_labeling(db_session, min_fiscal_year=2010)

    assert stats["positives_count"] == 1
    assert stats["matched_controls_count"] == 5
    assert stats["unmatched_positives_count"] == 0

    # Test override loading
    with open(pipeline.review_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "cik",
                "company_name",
                "fiscal_year",
                "aaer_number",
                "label",
                "confidence",
                "rationale",
                "review_status",
                "reviewer_notes",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "cik": pos_comp.cik,
                "company_name": pos_comp.name,
                "fiscal_year": 2015,
                "aaer_number": "AAER-4134",
                "label": 1,
                "confidence": "high",
                "rationale": "Verified fraud",
                "review_status": "approved",
                "reviewer_notes": "Reviewed and confirmed",
            }
        )

    overrides = pipeline.load_manual_overrides()
    assert (pos_comp.cik, 2015) in overrides
    assert overrides[(pos_comp.cik, 2015)]["review_status"] == "manual_override"
