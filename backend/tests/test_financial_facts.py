"""Tests for financial facts extraction, R3 original value selection, restatements, and duration filters."""

from datetime import date

from backend.app.ingest.facts_parser import FactsParser


def test_original_vs_restated_selection():
    """Verify R3 rule: earliest filing is original; subsequent differing value is flagged is_restated."""
    parser = FactsParser()

    # Synthetic excerpt simulating real restated filing scenario
    facts_json = {
        "cik": "0000320193",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            # 1. Original 10-K filing (filed 2016-01-28 for FY2015)
                            {
                                "end": "2015-12-31",
                                "val": 500000000.0,
                                "form": "10-K",
                                "accn": "0000320193-16-000010",
                                "filed": "2016-01-28",
                                "fp": "FY",
                            },
                            # 2. Subsequent 10-K comparative column (filed 2017-01-30, unchanged)
                            {
                                "end": "2015-12-31",
                                "val": 500000000.0,
                                "form": "10-K",
                                "accn": "0000320193-17-000015",
                                "filed": "2017-01-30",
                                "fp": "FY",
                            },
                            # 3. Restated 10-K/A amendment (filed 2018-02-15, modified value)
                            {
                                "end": "2015-12-31",
                                "val": 420000000.0,
                                "form": "10-K/A",
                                "accn": "0000320193-18-000020",
                                "filed": "2018-02-15",
                                "fp": "FY",
                            },
                        ]
                    }
                }
            }
        },
    }

    results = parser.extract_raw_facts(facts_json, fiscal_year_end_mmdd="1231")
    assert len(results) == 3

    # Map by accession
    by_accn = {r["accession_number"]: r for r in results}

    orig = by_accn["0000320193-16-000010"]
    assert orig["is_original_filing"] is True
    assert orig["is_restated"] is False
    assert orig["value"] == 500000000.0

    comp = by_accn["0000320193-17-000015"]
    assert comp["is_original_filing"] is False
    assert comp["is_restated"] is False  # Value did not change
    assert comp["value"] == 500000000.0

    restated = by_accn["0000320193-18-000020"]
    assert restated["is_original_filing"] is False
    assert restated["is_restated"] is True  # Value differed from original
    assert restated["value"] == 420000000.0


def test_full_year_duration_filter():
    """Income statement facts must cover ~365 days; quarterly and YTD facts must be rejected."""
    parser = FactsParser()

    facts_json = {
        "cik": "0000320193",
        "facts": {
            "us-gaap": {
                "OperatingIncomeLoss": {
                    "units": {
                        "USD": [
                            # Quarterly fact (91 days) -> must be rejected
                            {
                                "start": "2023-01-01",
                                "end": "2023-04-01",
                                "val": 100000.0,
                                "form": "10-K",
                                "accn": "0000320193-23-000050",
                                "filed": "2023-10-27",
                            },
                            # 9-Month YTD fact (273 days) -> must be rejected
                            {
                                "start": "2023-01-01",
                                "end": "2023-09-30",
                                "val": 300000.0,
                                "form": "10-K",
                                "accn": "0000320193-23-000050",
                                "filed": "2023-10-27",
                            },
                            # Full-year fact (365 days) -> must be accepted
                            {
                                "start": "2022-10-01",
                                "end": "2023-09-30",
                                "val": 500000.0,
                                "form": "10-K",
                                "accn": "0000320193-23-000050",
                                "filed": "2023-10-27",
                            },
                        ]
                    }
                }
            }
        },
    }

    results = parser.extract_raw_facts(facts_json, fiscal_year_end_mmdd="0930")
    assert len(results) == 1
    assert results[0]["value"] == 500000.0
    assert results[0]["fiscal_year"] == 2023


def test_bulk_insert_facts(db_session):
    """Verify batch insertion of financial facts into PostgreSQL test database."""
    parser = FactsParser()
    sample_facts = [
        {
            "cik": "0000001000",
            "tag": "Assets",
            "unit": "USD",
            "value": 1500000.0,
            "period_start": None,
            "period_end": date(2022, 12, 31),
            "fiscal_year": 2022,
            "fiscal_period": "FY",
            "form_type": "10-K",
            "accession_number": "0000001000-23-000001",
            "filed_date": date(2023, 2, 15),
            "is_original_filing": True,
            "is_restated": False,
        }
    ]

    inserted = parser.bulk_insert_facts(sample_facts, db_session)
    assert inserted == 1
