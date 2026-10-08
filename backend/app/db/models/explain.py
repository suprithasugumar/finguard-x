"""Explanations and multi-modal risk attribution database models (Stage 4)."""

from typing import Any, Optional

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin


class CompanyYearExplanation(Base, TimestampMixin):
    """Calibrated fraud risk score, multi-modal feature attribution, and evidence snippets."""

    __tablename__ = "company_year_explanations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filing_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("filings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    accession_number: Mapped[str] = mapped_column(String(25), nullable=False, index=True)

    # Calibrated Risk Scoring
    fraud_probability: Mapped[float] = mapped_column(Float, nullable=False)
    risk_score: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # round(100 * fraud_probability)
    risk_category: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # Low, Moderate, High, Very High
    review_priority_label: Mapped[str] = mapped_column(
        String(50), default="Fraud Risk / Review Priority", nullable=False
    )

    # Modality Attribution (Numeric, Text, Graph, FNCS)
    modality_breakdown: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    top_factors: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    plain_language_summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Grounded Evidence Artifacts
    evidence_snippets: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    evidence_edges: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    fncs_evidence: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_cye_cik_fy", "cik", "fiscal_year", unique=True),)
