"""Automated tests for Data Provenance Guard (Rule R1 verification)."""

import json
import zipfile
from pathlib import Path

import pytest

from backend.app.db.models.entities import Company, Filing, FinancialFact
from backend.app.ingest.provenance_guard import (
    ProvenanceGuard,
    ProvenanceViolationError,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def mock_archives_dir(tmp_path):
    """Create isolated mock SEC archives in a test temporary directory (never touches main DB)."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    # 1. Mock companyfacts.zip
    facts_data = {
        "cik": 1750,
        "entityName": "AAR CORP",
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "end": "2020-05-31",
                                "val": 1500000000.0,
                                "fy": 2020,
                                "fp": "FY",
                                "form": "10-K",
                                "accn": "0001047469-20-004123",
                            }
                        ]
                    }
                }
            }
        },
    }
    facts_zip_path = raw_dir / "companyfacts.zip"
    with zipfile.ZipFile(facts_zip_path, "w") as zf:
        zf.writestr("CIK0000001750.json", json.dumps(facts_data))

    # 2. Mock submissions.zip
    sub_data = {
        "cik": "1750",
        "name": "AAR CORP",
        "filings": {
            "recent": {
                "accessionNumber": ["0001047469-20-004123"],
                "form": ["10-K"],
                "filingDate": ["2020-07-21"],
                "reportDate": ["2020-05-31"],
            }
        },
    }
    sub_zip_path = raw_dir / "submissions.zip"
    with zipfile.ZipFile(sub_zip_path, "w") as zf:
        zf.writestr("CIK0000001750.json", json.dumps(sub_data))

    # 3. Mock manifest.json
    manifest = {
        "files": {
            "submissions.zip": {
                "sha256": "a" * 64,
                "size_bytes": 1000,
            },
            "companyfacts.zip": {
                "sha256": "b" * 64,
                "size_bytes": 1000,
            },
        }
    }
    with open(raw_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    return raw_dir


def test_provenance_guard_catches_synthetic_fact(mock_archives_dir, db_session):
    """Test that the guard immediately raises ProvenanceViolationError when encountering a synthetic fact."""
    guard = ProvenanceGuard(raw_dir=mock_archives_dir)

    # Insert a synthetic fact that is NOT in the mock companyfacts.zip
    fake_fact = FinancialFact(
        cik="0000001750",
        tag="Assets",
        unit="USD",
        value=999999999.0,
        period_end="2020-05-31",
        fiscal_year=2020,
        fiscal_period="FY",
        form_type="10-K",
        accession_number="FAKE-000000-00-000001",  # Synthetic!
        filed_date="2020-07-21",
        is_original_filing=True,
        is_restated=False,
    )
    db_session.add(fake_fact)
    db_session.commit()

    with pytest.raises(ProvenanceViolationError, match="Synthetic fact detected"):
        guard.verify_facts_provenance(db_session, sample_size=10)


def test_provenance_guard_catches_synthetic_filing(mock_archives_dir, db_session):
    """Test that the guard immediately raises ProvenanceViolationError when encountering a synthetic filing."""
    guard = ProvenanceGuard(raw_dir=mock_archives_dir)

    company = Company(cik="0000001750", name="AAR CORP")
    db_session.add(company)
    db_session.flush()

    fake_filing = Filing(
        company_id=company.id,
        cik="0000001750",
        accession_number="FAKE-000000-00-000002",  # Synthetic!
        form_type="10-K",
        fiscal_year=2020,
        fiscal_period="FY",
        filing_date="2020-07-21",
        period_end="2020-05-31",
    )
    db_session.add(fake_filing)
    db_session.commit()

    with pytest.raises(ProvenanceViolationError, match="Synthetic filing detected"):
        guard.verify_filings_provenance(db_session, sample_size=10)


def test_provenance_guard_passes_for_authentic_fact(mock_archives_dir, db_session):
    """Test that authentic facts matching the raw archive pass verification without error."""
    guard = ProvenanceGuard(raw_dir=mock_archives_dir)

    real_fact = FinancialFact(
        cik="0000001750",
        tag="Assets",
        unit="USD",
        value=1500000000.0,
        period_end="2020-05-31",
        fiscal_year=2020,
        fiscal_period="FY",
        form_type="10-K",
        accession_number="0001047469-20-004123",  # Matches mock companyfacts.zip!
        filed_date="2020-07-21",
        is_original_filing=True,
        is_restated=False,
    )
    db_session.add(real_fact)
    db_session.commit()

    verified_count = guard.verify_facts_provenance(db_session, sample_size=10)
    assert verified_count >= 1
