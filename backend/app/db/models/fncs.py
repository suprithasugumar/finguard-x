"""Financial Narrative Contradiction Score (FNCS) database models."""

from typing import Any, Optional

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin


class CompanyYearFNCSFeatures(Base, TimestampMixin):
    """FNCS multi-category numeric-text alignment and contradiction features."""

    __tablename__ = "company_year_fncs_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filing_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("filings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    accession_number: Mapped[str] = mapped_column(String(25), nullable=False, index=True)

    # 7 Real Spec Category Contradiction Scores [0, 1]
    cat_growth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat_profitability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat_liquidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat_demand: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat_cash_flow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat_risk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat_outlook: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    category_statuses: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)

    # Legacy Category Columns (maintained for schema backward compatibility)
    cat1_revenue_recognition: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat2_inventory_valuation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat3_reserve_manipulation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat4_capitalized_expenses: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat5_related_party: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat6_governance_executive: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cat7_going_concern: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Composite Contradiction Metrics
    contradiction_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fncs_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Primary FNCS Index

    # Per-Category Evidence & Explanation Sentences
    fncs_evidence: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    explanation_sentences: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (Index("ix_cyfncs_cik_fy", "cik", "fiscal_year", unique=True),)
