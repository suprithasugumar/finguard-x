"""Add company_year_graph_features and company_year_fncs_features tables.

Revision ID: 004_graph_and_fncs
Revises: 003_sprint_a_features
Create Date: 2026-10-08 19:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_graph_and_fncs"
down_revision: Union[str, None] = "003_sprint_a_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create company_year_graph_features
    op.create_table(
        "company_year_graph_features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filing_id", sa.Integer(), nullable=True),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=25), nullable=False),
        sa.Column("graph_available", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("graph_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("num_nodes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("num_edges", sa.Integer(), server_default="0", nullable=False),
        sa.Column("density", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("avg_degree", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("num_officers", sa.Integer(), server_default="0", nullable=False),
        sa.Column("num_entities", sa.Integer(), server_default="0", nullable=False),
        sa.Column("num_undisclosed_or_shell", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_clique_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("clustering_coefficient", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("betweenness_centrality_max", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("yoy_node_churn", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("yoy_edge_churn", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("graph_anomaly_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("graph_payload", sa.JSON(), nullable=False),
        sa.Column("evidence_edges", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["filing_id"], ["filings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cygf_cik_fy", "company_year_graph_features", ["cik", "fiscal_year"], unique=True
    )

    # 2. Create company_year_fncs_features
    op.create_table(
        "company_year_fncs_features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filing_id", sa.Integer(), nullable=True),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=25), nullable=False),
        sa.Column("cat1_revenue_recognition", sa.Float(), nullable=True),
        sa.Column("cat2_inventory_valuation", sa.Float(), nullable=True),
        sa.Column("cat3_reserve_manipulation", sa.Float(), nullable=True),
        sa.Column("cat4_capitalized_expenses", sa.Float(), nullable=True),
        sa.Column("cat5_related_party", sa.Float(), nullable=True),
        sa.Column("cat6_governance_executive", sa.Float(), nullable=True),
        sa.Column("cat7_going_concern", sa.Float(), nullable=True),
        sa.Column("contradiction_score", sa.Float(), nullable=True),
        sa.Column("fncs_score", sa.Float(), nullable=True),
        sa.Column("fncs_evidence", sa.JSON(), nullable=False),
        sa.Column("explanation_sentences", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["filing_id"], ["filings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cyfncs_cik_fy", "company_year_fncs_features", ["cik", "fiscal_year"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_cyfncs_cik_fy", table_name="company_year_fncs_features")
    op.drop_table("company_year_fncs_features")
    op.drop_index("ix_cygf_cik_fy", table_name="company_year_graph_features")
    op.drop_table("company_year_graph_features")
