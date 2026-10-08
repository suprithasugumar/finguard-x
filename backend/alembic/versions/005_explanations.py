"""Add company_year_explanations table for multi-modal risk scoring and explanations.

Revision ID: 005_explanations
Revises: 004_graph_and_fncs
Create Date: 2026-10-08 20:25:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_explanations"
down_revision: Union[str, None] = "004_graph_and_fncs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_year_explanations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filing_id", sa.Integer(), nullable=True),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=25), nullable=False),
        sa.Column("fraud_probability", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_category", sa.String(length=20), nullable=False),
        sa.Column("review_priority_label", sa.String(length=50), server_default="Fraud Risk / Review Priority", nullable=False),
        sa.Column("modality_breakdown", sa.JSON(), nullable=False),
        sa.Column("top_factors", sa.JSON(), nullable=False),
        sa.Column("plain_language_summary", sa.Text(), nullable=False),
        sa.Column("evidence_snippets", sa.JSON(), nullable=False),
        sa.Column("evidence_edges", sa.JSON(), nullable=False),
        sa.Column("fncs_evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["filing_id"], ["filings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cye_cik_fy", "company_year_explanations", ["cik", "fiscal_year"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_cye_cik_fy", table_name="company_year_explanations")
    op.drop_table("company_year_explanations")
