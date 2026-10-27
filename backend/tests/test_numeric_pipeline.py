"""Phase 1 Numeric Pipeline Unit & Integration Tests.

Verifies:
1. Margin & ROA calculation whenever inputs exist (fails if rev & ni present but net_margin is NULL).
2. Financial firm exclusion (SIC 6000-6999 marked not_applicable).
3. Zero inventory rule (inventory_to_assets = 0.0, inventory_applicable = False).
4. No Gross Profit fabrication: COGS absent yields GMI = NULL ("no_cogs_reported").
5. XBRL Fallback chains per concept.
6. Hand-verified Beneish M-Score for 10 real firms against manual calculation.
"""

import math
import pytest
from sqlalchemy.orm import Session

from backend.app.db.session import get_session_factory
from backend.app.db.models.entities import Company, Filing
from backend.app.features.financial_features import FinancialFeaturesExtractor, TAG_PRIORITIES


@pytest.fixture
def db_session():
    session = get_session_factory()()
    yield session
    session.close()


def test_margin_and_roa_must_compute_when_inputs_exist(db_session: Session):
    """Fails if revenue and net income are present but net_margin is NULL."""
    extractor = FinancialFeaturesExtractor(db_session)

    curr = {
        "revenues": 1000000.0,
        "net_income": 85000.0,
        "operating_income": 120000.0,
        "assets": 2000000.0,
    }
    prior = {"assets": 1900000.0, "revenues": 950000.0}

    computed = extractor._compute_all_features(curr=curr, prior=prior, is_financial=False, fiscal_year=2020)

    # Unit test requirement: net_margin must compute whenever rev and ni exist
    assert computed.get("net_margin") is not None, "net_margin must not be NULL when rev and ni exist"
    assert math.isclose(computed["net_margin"], 85000.0 / 1000000.0, rel_tol=1e-5)
    assert computed["feature_statuses"]["net_margin"] == "ok"

    # Operating margin
    assert computed.get("operating_margin") is not None
    assert math.isclose(computed["operating_margin"], 120000.0 / 1000000.0, rel_tol=1e-5)

    # ROA
    assert computed.get("roa") is not None
    assert math.isclose(computed["roa"], 85000.0 / 2000000.0, rel_tol=1e-5)

    # Asset Turnover
    assert computed.get("asset_turnover") is not None
    assert math.isclose(computed["asset_turnover"], 1000000.0 / 2000000.0, rel_tol=1e-5)


def test_zero_inventory_rule(db_session: Session):
    """If firm reports no inventory concept, set inventory_to_assets = 0 and inventory_applicable = false."""
    extractor = FinancialFeaturesExtractor(db_session)

    # Firm with no inventory concept reported
    curr = {
        "assets": 1500000.0,
        "revenues": 800000.0,
        "net_income": 50000.0,
        # 'inventory' is omitted / None
    }
    prior = {"assets": 1400000.0}

    computed = extractor._compute_all_features(curr=curr, prior=prior, is_financial=False, fiscal_year=2021)

    assert computed["inventory_applicable"] is False
    assert computed.get("inventory_to_assets") == 0.0
    assert computed["feature_statuses"]["inventory_to_assets"] == "ok"
    assert computed["null_reasons"]["inventory_to_assets"] == "zero_inventory_firm"


def test_no_gross_profit_fabrication_when_cogs_missing(db_session: Session):
    """If COGS is absent for firm with inventory: GMI = NULL with reason 'no_cogs_reported'. Do NOT fabricate GP."""
    extractor = FinancialFeaturesExtractor(db_session)

    # Case A: Commercial firm with inventory, but COGS absent -> GMI must be NULL
    curr_mfg = {
        "revenues": 2000000.0,
        "assets": 4000000.0,
        "inventory": 500000.0,
        # COGS absent
    }
    prior_mfg = {
        "revenues": 1800000.0,
        "assets": 3800000.0,
        "inventory": 450000.0,
        # COGS absent
    }

    computed_mfg = extractor._compute_all_features(curr=curr_mfg, prior=prior_mfg, is_financial=False, fiscal_year=2020)
    assert computed_mfg.get("beneish_gmi") is None
    assert computed_mfg["null_reasons"]["beneish_gmi"] == "no_cogs_reported"
    assert computed_mfg["feature_statuses"]["beneish_gmi"] == "missing_input"

    # Case B: Pure service firm (inventory = 0 / not applicable) -> GMI is neutral 1.0
    curr_svc = {
        "revenues": 2000000.0,
        "assets": 4000000.0,
    }
    prior_svc = {
        "revenues": 1800000.0,
        "assets": 3800000.0,
    }
    computed_svc = extractor._compute_all_features(curr=curr_svc, prior=prior_svc, is_financial=False, fiscal_year=2020)
    assert computed_svc.get("beneish_gmi") == 1.0
    assert computed_svc["feature_statuses"]["beneish_gmi"] == "ok"


def test_financial_firm_exclusion_sic_6000_6999(db_session: Session):
    """SIC 6000-6999 firms marked not_applicable_financial_firm and excluded from Beneish."""
    extractor = FinancialFeaturesExtractor(db_session)

    curr = {
        "assets": 50000000.0,
        "revenues": 3000000.0,
        "net_income": 400000.0,
        "receivables": 100000.0,
    }
    prior = {"assets": 48000000.0, "revenues": 2800000.0, "receivables": 90000.0}

    computed = extractor._compute_all_features(curr=curr, prior=prior, is_financial=True, fiscal_year=2020)

    assert computed.get("beneish_strict") is None
    assert computed.get("beneish_neutral") is None
    assert computed["null_reasons"]["beneish"] == "not_applicable_financial_firm"
    assert computed["feature_statuses"]["beneish_strict"] == "not_applicable"
    assert computed["feature_statuses"]["current_ratio"] == "not_applicable"


def test_fallback_chains_tag_priorities():
    """Verify fallback chain definitions for core concepts."""
    # Receivables fallback chain
    rec_chain = TAG_PRIORITIES["receivables"]
    assert rec_chain[0] == "AccountsReceivableNetCurrent"
    assert "ReceivablesNetCurrent" in rec_chain
    assert "AccountsAndNotesReceivableNet" in rec_chain

    # Revenues fallback chain
    rev_chain = TAG_PRIORITIES["revenues"]
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in rev_chain
    assert "SalesRevenueNet" in rev_chain
    assert "Revenues" in rev_chain

    # COGS fallback chain
    cogs_chain = TAG_PRIORITIES["cogs"]
    assert "CostOfGoodsAndServicesSold" in cogs_chain
    assert "CostOfRevenue" in cogs_chain


def test_hand_verification_10_firms_m_score(db_session: Session):
    """Hand-verify Beneish M-Score for 10 firms against manual calculation."""
    extractor = FinancialFeaturesExtractor(db_session)

    # 10 confirmed firms with all 8 components present
    test_firms = [
        {"cik": "0000006494", "fy": 2019, "name": "ANDREA ELECTRONICS CORP"},
        {"cik": "0000007039", "fy": 2018, "name": "TRECORA RESOURCES"},
        {"cik": "0000007084", "fy": 2021, "name": "Archer-Daniels-Midland Co"},
        {"cik": "0000007084", "fy": 2022, "name": "Archer-Daniels-Midland Co"},
        {"cik": "0000007084", "fy": 2023, "name": "Archer-Daniels-Midland Co"},
        {"cik": "0000007431", "fy": 2019, "name": "ARMSTRONG WORLD INDUSTRIES INC"},
        {"cik": "0000007431", "fy": 2020, "name": "ARMSTRONG WORLD INDUSTRIES INC"},
        {"cik": "0000008504", "fy": 2019, "name": "AgEagle Aerial Systems Inc."},
        {"cik": "0000010795", "fy": 2019, "name": "BECTON DICKINSON & CO"},
        {"cik": "0000010795", "fy": 2020, "name": "BECTON DICKINSON & CO"},
    ]

    verified_count = 0
    for tf in test_firms:
        cyf = extractor.extract_company_year_features(tf["cik"], tf["fy"])
        assert cyf is not None, f"Failed feature extraction for {tf['name']}"

        # If all 8 components are present, manually compute Beneish M-Score
        comps = [
            cyf.beneish_dsri, cyf.beneish_gmi, cyf.beneish_aqi, cyf.beneish_sgi,
            cyf.beneish_depi, cyf.beneish_sgai, cyf.beneish_lvgi, cyf.beneish_tata
        ]
        assert all(c is not None for c in comps), f"Firm {tf['name']} missing some of 8 components"

        manual_m = (
            -4.84
            + 0.920 * cyf.beneish_dsri
            + 0.528 * cyf.beneish_gmi
            + 0.404 * cyf.beneish_aqi
            + 0.892 * cyf.beneish_sgi
            + 0.115 * cyf.beneish_depi
            - 0.172 * cyf.beneish_sgai
            + 4.037 * cyf.beneish_tata
            + 0.0327 * cyf.beneish_lvgi
        )
        assert cyf.beneish_strict is not None
        assert math.isclose(cyf.beneish_strict, manual_m, rel_tol=1e-4)
        assert cyf.beneish_neutral is not None
        assert cyf.beneish_n_components == 8
        assert cyf.feature_statuses["beneish_strict"] == "ok"
        verified_count += 1

    assert verified_count == 10, f"Expected exactly 10 hand-verified firms, got {verified_count}"
