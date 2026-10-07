"""Tests for AAER parsing, exclusions, formerNames CIK resolution, and year range expansion."""

from backend.app.ingest.aaer_parser import AAERParser, normalize_company_name


def test_exclusion_filters():
    """Verify Section 12(j), Rule 102(e), and auditor sanctions are properly filtered out."""
    parser = AAERParser()

    # Section 12(j)
    reason_12j = parser.is_excluded_case(
        "Order Instituting Administrative Proceedings Pursuant to Section 12(j)",
        "The Commission finds that the Respondent failed to file periodic reports.",
    )
    assert reason_12j is not None
    assert "Section 12(j)" in reason_12j

    # Rule 102(e)
    reason_102e = parser.is_excluded_case(
        "In the Matter of John Doe, CPA, Respondent - Rule 102(e) Suspension",
        "Suspended from appearing or practicing before the Commission as an accountant.",
    )
    assert reason_102e is not None
    assert "Rule 102(e)" in reason_102e

    # Auditor firm
    reason_aud = parser.is_excluded_case(
        "SEC Charges KPMG LLP with Audit Deficiencies",
        "KPMG agrees to pay penalty.",
    )
    assert reason_aud is not None
    assert "Auditor" in reason_aud

    # Valid corporate fraud action should NOT be excluded
    reason_valid = parser.is_excluded_case(
        "SEC Charges Valeant Pharmaceuticals and Former Executives with Fraud",
        "Valeant materially misstated revenue from Philidor.",
    )
    assert reason_valid is None


def test_cik_resolution_with_former_names():
    """Verify company CIK resolution handles formerNames and explicit text CIKs."""
    company_lookup = {
        normalize_company_name("Luminary Technologies Inc."): {
            "cik": "0001555555",
            "name": "Luminary Technologies Inc.",
            "former_names": ["Solaris Solar Systems Corp.", "Solaris Energy Inc."],
        },
        normalize_company_name("Apple Inc."): {
            "cik": "0000320193",
            "name": "Apple Inc.",
            "former_names": [],
        },
    }

    parser = AAERParser(company_lookup)

    # 1. Exact match
    cik, method, score = parser.resolve_cik("Apple Inc.", "Text mentions Apple.")
    assert cik == "0000320193"
    assert method == "exact_name"

    # 2. Match via formerNames
    cik_former, method_former, score_former = parser.resolve_cik(
        "Solaris Solar Systems Corp.", "Release text about Solaris."
    )
    assert cik_former == "0001555555"
    assert method_former == "former_name"

    # 3. Explicit CIK in text
    cik_exp, method_exp, _ = parser.resolve_cik(
        "Unknown Sub Corp", "Respondent CIK 0000789019 filed false statements."
    )
    assert cik_exp == "0000789019"
    assert method_exp == "explicit_cik_text"


def test_affected_fiscal_years_expansion():
    """Verify range expansion and quarter-to-fiscal-year mapping."""
    parser = AAERParser()

    # Range: "fiscal years 2013 through 2015"
    text_range = "The company improperly recognized revenue during fiscal years 2013 through 2015."
    extracted_range = parser.extract_affected_fiscal_years(text_range)
    years = [y for y, conf, rat in extracted_range]
    assert years == [2013, 2014, 2015]
    assert all(conf == "high" for _, conf, _ in extracted_range)

    # Quarter only: "third quarter of 2017"
    text_q = "Misstatements occurred during the third quarter of 2017."
    extracted_q = parser.extract_affected_fiscal_years(text_q)
    assert len(extracted_q) == 1
    assert extracted_q[0][0] == 2017
    assert extracted_q[0][1] == "medium"
    assert "quarterly" in extracted_q[0][2]
