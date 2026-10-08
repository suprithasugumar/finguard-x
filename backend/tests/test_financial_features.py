"""Automated tests for normalized financial features, R3 look-ahead anti-leakage, and hand-checked SEC filings."""

import pytest

from backend.app.db.models.entities import CompanyYearLabel, Filing
from backend.app.db.session import get_session_factory
from backend.app.features.financial_features import FinancialFeaturesExtractor


@pytest.fixture
def db_session():
    session = get_session_factory()()
    yield session
    session.close()


def test_lookahead_anti_leakage(db_session):
    """Verify Rule R3: Features extracted using cutoff_date == filing_date are identical to unconstrained."""
    extractor = FinancialFeaturesExtractor(db_session)
    label = db_session.query(CompanyYearLabel).filter(CompanyYearLabel.label == 1).first()
    assert label is not None, "At least one positive label required in DB"

    filing = (
        db_session.query(Filing)
        .filter(
            Filing.cik == label.cik,
            Filing.fiscal_year == label.fiscal_year,
            Filing.is_amendment.is_(False),
        )
        .first()
    )
    assert filing is not None, "Original filing must exist"

    # Extract without cutoff
    feat_unconstrained = extractor.extract_company_year_features(label.cik, label.fiscal_year)
    # Extract with cutoff at exact filing date
    feat_constrained = extractor.extract_company_year_features(
        label.cik, label.fiscal_year, cutoff_date=filing.filing_date
    )

    assert feat_unconstrained is not None
    assert feat_constrained is not None

    # Verify key features are strictly identical
    assert feat_unconstrained.asset_turnover == feat_constrained.asset_turnover
    assert feat_unconstrained.roa == feat_constrained.roa
    assert feat_unconstrained.beneish_sgi == feat_constrained.beneish_sgi
    assert feat_unconstrained.prior_val_source == feat_constrained.prior_val_source


def test_five_hand_checked_company_years(db_session):
    """Hand-check 5 real company-years with authentic SEC EDGAR accession numbers."""
    extractor = FinancialFeaturesExtractor(db_session)

    targets = [
        {
            "cik": "0000004904",
            "fy": 2024,
            "accn": "0000004904-25-000027",
            "name": "American Electric Power",
        },
        {
            "cik": "0001090727",
            "fy": 2023,
            "accn": "0001090727-24-000008",
            "name": "United Parcel Service",
        },
        {
            "cik": "0001739104",
            "fy": 2023,
            "accn": "0001739104-24-000009",
            "name": "Elanco Animal Health",
        },
        {"cik": "0000101829", "fy": 2023, "accn": "0000101829-24-000008", "name": "RTX Corp"},
        {"cik": "0000067887", "fy": 2023, "accn": "0000067887-23-000115", "name": "Moog Inc"},
    ]

    for t in targets:
        cyf = extractor.extract_company_year_features(t["cik"], t["fy"])
        assert (
            cyf is not None
        ), f"Failed to extract features for {t['name']} (CIK {t['cik']}, FY {t['fy']})"
        assert cyf.accession_number == t["accn"], f"Accession mismatch for {t['name']}"
        assert (
            cyf.asset_turnover is not None and cyf.asset_turnover > 0
        ), f"Invalid asset turnover for {t['name']}"
        assert cyf.roa is not None, f"ROA is None for {t['name']}"
        assert cyf.prior_val_source in ("prior_original_10k", "comparative_fallback")
        assert isinstance(cyf.source_tags, dict)
        assert isinstance(cyf.null_reasons, dict)
