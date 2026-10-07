"""Tests for PostgreSQL database models, relationships, and constraints."""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import Company, Filing, RequestLog


def test_create_and_query_company(db_session: Session):
    """Verify company insertion and retrieval with fields."""
    company = Company(
        cik="0000320193",
        ticker="AAPL",
        name="Apple Inc.",
        sic="3571",
        sic_description="Electronic Computers",
        fiscal_year_end="0930",
        state_location="CA",
    )
    db_session.add(company)
    db_session.flush()

    assert company.id is not None
    assert company.created_at is not None

    stmt = select(Company).where(Company.cik == "0000320193")
    fetched = db_session.scalar(stmt)
    assert fetched is not None
    assert fetched.ticker == "AAPL"
    assert fetched.name == "Apple Inc."


def test_unique_cik_constraint(db_session: Session):
    """Verify that duplicate CIKs violate unique constraint."""
    comp1 = Company(cik="0001018724", name="Amazon.com Inc.", ticker="AMZN")
    comp2 = Company(cik="0001018724", name="Duplicate Amazon", ticker="AMZN2")
    db_session.add(comp1)
    db_session.flush()

    db_session.add(comp2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_filing_relationship_and_cascade(db_session: Session):
    """Verify Filing foreign key, relationship, and cascade delete."""
    company = Company(cik="0000789019", ticker="MSFT", name="Microsoft Corp")
    db_session.add(company)
    db_session.flush()

    filing = Filing(
        company_id=company.id,
        cik=company.cik,
        accession_number="0000789019-23-000050",
        form_type="10-K",
        fiscal_year=2023,
        fiscal_period="FY",
        filing_date=date(2023, 7, 27),
        report_date=date(2023, 6, 30),
    )
    db_session.add(filing)
    db_session.flush()

    assert len(company.filings) == 1
    assert company.filings[0].accession_number == "0000789019-23-000050"

    # Delete company and verify filing cascade
    db_session.delete(company)
    db_session.flush()

    filing_check = db_session.scalar(
        select(Filing).where(Filing.accession_number == "0000789019-23-000050")
    )
    assert filing_check is None, "Filing must be deleted by cascade when company is removed"


def test_request_log_audit(db_session: Session):
    """Verify SEC request audit logging model."""
    log_entry = RequestLog(
        url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        method="GET",
        status_code=200,
        response_time_ms=142.5,
        cached=False,
    )
    db_session.add(log_entry)
    db_session.flush()

    assert log_entry.id is not None
    assert log_entry.timestamp is not None

    stmt = select(RequestLog).where(RequestLog.id == log_entry.id)
    fetched = db_session.scalar(stmt)
    assert fetched is not None
    assert fetched.status_code == 200
    assert fetched.cached is False
