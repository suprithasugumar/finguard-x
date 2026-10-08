"""Filing sections and NLP narrative drift database models."""

from typing import Any, Optional

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin


class FilingSection(Base, TimestampMixin):
    """Extracted text section (Item 7 MD&A, Related Party note, Item 1A Risk Factors)."""

    __tablename__ = "filing_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filing_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("filings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    accession_number: Mapped[str] = mapped_column(String(25), nullable=False, index=True)
    section_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # mda, related_party, risk_factors
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sentence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    extraction_status: Mapped[str] = mapped_column(
        String(50), default="success", nullable=False
    )  # success, not_found, malformed_html

    __table_args__ = (
        Index("ix_filing_sections_cik_fy_sec", "cik", "fiscal_year", "section_type", unique=True),
    )


class FilingNLPFeatures(Base, TimestampMixin):
    """Narrative drift and linguistic supporting features for a company-year."""

    __tablename__ = "filing_nlp_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filing_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("filings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    accession_number: Mapped[str] = mapped_column(String(25), nullable=False, index=True)

    # Novelty 1: Narrative Drift Scores
    narrative_drift_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # [0, 1]
    doc_embedding_cosine_drift: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mda_drift_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_drift_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Supporting NLP Features
    vocab_jaccard_distance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uncertainty_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    negative_sentiment_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    financial_uncertainty_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_sentence_length: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    readability_fog_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conditional_language_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    passive_voice_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    numeric_density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Evidence Snippets (Lowest-match current sentences with nearest prior sentence)
    drift_evidence_snippets: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (Index("ix_fnlp_cik_fy", "cik", "fiscal_year", unique=True),)
