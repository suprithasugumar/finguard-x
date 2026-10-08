"""Knowledge graph and related-party network database models."""
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin


class CompanyYearGraphFeatures(Base, TimestampMixin):
    """NetworkX graph topology, entity extraction, and YoY evolution features."""

    __tablename__ = "company_year_graph_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filing_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("filings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    accession_number: Mapped[str] = mapped_column(String(25), nullable=False, index=True)

    # Availability & Sizing Flags
    graph_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    graph_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Topological Metrics (zeros if graph_available = False)
    num_nodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_edges: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    density: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_degree: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    num_officers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_entities: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_undisclosed_or_shell: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_clique_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clustering_coefficient: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    betweenness_centrality_max: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # YoY Graph Dynamics
    yoy_node_churn: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    yoy_edge_churn: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Novelty 2 Composite Index
    graph_anomaly_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Graph Payload for API & UI Visualizer
    graph_payload: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    evidence_edges: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (
        Index("ix_cygf_cik_fy", "cik", "fiscal_year", unique=True),
    )
