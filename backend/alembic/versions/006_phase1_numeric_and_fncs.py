"""Phase 1 Numeric Pipeline and FNCS Alignment.

Revision ID: 006_phase1_numeric_and_fncs
Revises: 005_explanations
Create Date: 2026-10-27 19:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_phase1_numeric_and_fncs"
down_revision: Union[str, None] = "005_explanations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. company_year_labels
    op.add_column(
        "company_year_labels",
        sa.Column("eval_excluded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    # 2. company_year_features
    op.add_column("company_year_features", sa.Column("beneish_strict", sa.Float(), nullable=True))
    op.add_column("company_year_features", sa.Column("beneish_neutral", sa.Float(), nullable=True))
    op.add_column(
        "company_year_features",
        sa.Column("beneish_n_components", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "company_year_features",
        sa.Column("inventory_applicable", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "company_year_features",
        sa.Column("feature_statuses", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
    )

    # 3. company_year_fncs_features
    op.add_column("company_year_fncs_features", sa.Column("cat_growth", sa.Float(), nullable=True))
    op.add_column("company_year_fncs_features", sa.Column("cat_profitability", sa.Float(), nullable=True))
    op.add_column("company_year_fncs_features", sa.Column("cat_liquidity", sa.Float(), nullable=True))
    op.add_column("company_year_fncs_features", sa.Column("cat_demand", sa.Float(), nullable=True))
    op.add_column("company_year_fncs_features", sa.Column("cat_cash_flow", sa.Float(), nullable=True))
    op.add_column("company_year_fncs_features", sa.Column("cat_risk", sa.Float(), nullable=True))
    op.add_column("company_year_fncs_features", sa.Column("cat_outlook", sa.Float(), nullable=True))
    op.add_column(
        "company_year_fncs_features",
        sa.Column("category_statuses", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("company_year_labels", "eval_excluded")
    op.drop_column("company_year_features", "beneish_strict")
    op.drop_column("company_year_features", "beneish_neutral")
    op.drop_column("company_year_features", "beneish_n_components")
    op.drop_column("company_year_features", "inventory_applicable")
    op.drop_column("company_year_features", "feature_statuses")
    op.drop_column("company_year_fncs_features", "cat_growth")
    op.drop_column("company_year_fncs_features", "cat_profitability")
    op.drop_column("company_year_fncs_features", "cat_liquidity")
    op.drop_column("company_year_fncs_features", "cat_demand")
    op.drop_column("company_year_fncs_features", "cat_cash_flow")
    op.drop_column("company_year_fncs_features", "cat_risk")
    op.drop_column("company_year_fncs_features", "cat_outlook")
    op.drop_column("company_year_fncs_features", "category_statuses")
