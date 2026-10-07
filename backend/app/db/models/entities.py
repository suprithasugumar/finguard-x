"""Core database models for companies, filings, financial facts, AAER cases, and labels."""

from datetime import date, datetime
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin


class Company(Base, TimestampMixin):
    """Company entity identified by SEC CIK."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cik: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False)
    ticker: Mapped[Optional[str]] = mapped_column(String(10), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    sic: Mapped[Optional[str]] = mapped_column(String(4), index=True, nullable=True)
    sic_description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    fiscal_year_end: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    state_location: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)

    # Relationships
    filings: Mapped[List["Filing"]] = relationship(
        "Filing", back_populates="company", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_companies_cik_ticker", "cik", "ticker"),)


class Filing(Base, TimestampMixin):
    """SEC 10-K filing metadata and on-disk file references."""

    __tablename__ = "filings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    accession_number: Mapped[str] = mapped_column(
        String(25), unique=True, nullable=False, index=True
    )
    form_type: Mapped[str] = mapped_column(String(10), default="10-K", nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    fiscal_period: Mapped[str] = mapped_column(String(10), default="FY", nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    report_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    primary_document: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_amendment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    raw_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="filings")

    __table_args__ = (
        Index("ix_filings_cik_fy", "cik", "fiscal_year"),
        Index("ix_filings_filing_date", "filing_date"),
    )


class RequestLog(Base):
    """SEC EDGAR request audit trail to guarantee R4 rate-limiting and logging compliance."""

    __tablename__ = "request_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="GET", nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_request_log_timestamp", "timestamp"),
        Index("ix_request_log_cached", "cached"),
    )


class FinancialFact(Base, TimestampMixin):
    """Raw financial facts from XBRL submissions with R3 anti-leakage original value tracking."""

    __tablename__ = "financial_facts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    tag: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    unit: Mapped[str] = mapped_column(String(20), default="USD", nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    fiscal_period: Mapped[str] = mapped_column(String(10), default="FY", nullable=False)
    form_type: Mapped[str] = mapped_column(String(10), default="10-K", nullable=False)
    accession_number: Mapped[str] = mapped_column(String(25), nullable=False, index=True)
    filed_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_original_filing: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    is_restated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    __table_args__ = (
        Index("ix_facts_cik_fy_tag", "cik", "fiscal_year", "tag"),
        Index("ix_facts_cik_tag_period", "cik", "tag", "period_end"),
    )


class AAERCase(Base, TimestampMixin):
    """Enforcement case record extracted from SEC AAER releases."""

    __tablename__ = "aaer_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    aaer_number: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    release_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    enforcement_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cik: Mapped[Optional[str]] = mapped_column(String(10), index=True, nullable=True)
    affected_fiscal_years: Mapped[Any] = mapped_column(JSON, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    raw_text_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    exclusion_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (Index("ix_aaer_cases_cik_enf", "cik", "enforcement_date"),)


class CompanyYearLabel(Base, TimestampMixin):
    """Ground truth company-year label (Positive 1 or Matched Control 0)."""

    __tablename__ = "company_year_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    label: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )  # 1 = positive, 0 = control
    label_confidence: Mapped[str] = mapped_column(
        String(20), default="high", nullable=False
    )  # high, medium, low
    label_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    aaer_case_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("aaer_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    matched_positive_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("company_year_labels.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    match_distance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), default="auto", nullable=False)

    __table_args__ = (Index("ix_cyl_cik_fy", "cik", "fiscal_year"),)
