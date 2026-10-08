"""Financial features and Beneish M-Score database models."""

from datetime import date
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin


class CompanyYearFeatures(Base, TimestampMixin):
    """Normalized financial ratios, 8 Beneish components, and M-Score for each company-year."""

    __tablename__ = "company_year_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    accession_number: Mapped[str] = mapped_column(String(25), nullable=False, index=True)
    form_type: Mapped[str] = mapped_column(String(10), default="10-K", nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    sic: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)

    # Inapplicability & Prior Source Tracking (DEC-008)
    beneish_applicable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    prior_val_source: Mapped[str] = mapped_column(
        String(30), default="prior_original_10k", nullable=False
    )
    source_tags: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    null_reasons: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)

    # 18 Core Financial Ratios
    asset_turnover: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    roa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    operating_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    debt_to_equity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cash_to_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    working_capital_to_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cfo_to_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sales_to_receivables: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    receivables_to_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inventory_to_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    capex_to_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    debt_to_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cash_flow_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accruals_bs_to_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accruals_cf_to_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    asset_growth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # 8 Beneish M-Score Components
    beneish_dsri: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beneish_gmi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beneish_aqi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beneish_sgi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beneish_depi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beneish_sgai: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beneish_lvgi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beneish_tata: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beneish_tata_bs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Composite M-Score & Risk Flags
    beneish_m_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beneish_flag_178: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    beneish_flag_222: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        Index("ix_cyf_cik_fy", "cik", "fiscal_year", unique=True),
        Index("ix_cyf_accn", "accession_number"),
    )
