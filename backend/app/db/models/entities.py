"""Core database models for companies, filings, and request audits."""

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
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
    report_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
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
