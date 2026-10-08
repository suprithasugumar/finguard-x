"""Add company_year_features, filing_sections, and filing_nlp_features tables.

Revision ID: 003_sprint_a_features_and_sections
Revises: 002_sec_ingest_and_labels
Create Date: 2026-10-08 18:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_sprint_a_features"
down_revision: Union[str, None] = "002_sec_ingest_and_labels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create company_year_features
    op.create_table(
        "company_year_features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=25), nullable=False),
        sa.Column("form_type", sa.String(length=10), server_default="10-K", nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("sic", sa.String(length=4), nullable=True),
        sa.Column(
            "beneish_applicable", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "prior_val_source",
            sa.String(length=30),
            server_default="prior_original_10k",
            nullable=False,
        ),
        sa.Column("source_tags", sa.JSON(), nullable=False),
        sa.Column("null_reasons", sa.JSON(), nullable=False),
        sa.Column("asset_turnover", sa.Float(), nullable=True),
        sa.Column("roa", sa.Float(), nullable=True),
        sa.Column("operating_margin", sa.Float(), nullable=True),
        sa.Column("net_margin", sa.Float(), nullable=True),
        sa.Column("current_ratio", sa.Float(), nullable=True),
        sa.Column("debt_to_equity", sa.Float(), nullable=True),
        sa.Column("cash_to_assets", sa.Float(), nullable=True),
        sa.Column("working_capital_to_assets", sa.Float(), nullable=True),
        sa.Column("cfo_to_assets", sa.Float(), nullable=True),
        sa.Column("sales_to_receivables", sa.Float(), nullable=True),
        sa.Column("receivables_to_assets", sa.Float(), nullable=True),
        sa.Column("inventory_to_assets", sa.Float(), nullable=True),
        sa.Column("capex_to_assets", sa.Float(), nullable=True),
        sa.Column("debt_to_assets", sa.Float(), nullable=True),
        sa.Column("cash_flow_margin", sa.Float(), nullable=True),
        sa.Column("accruals_bs_to_assets", sa.Float(), nullable=True),
        sa.Column("accruals_cf_to_assets", sa.Float(), nullable=True),
        sa.Column("asset_growth", sa.Float(), nullable=True),
        sa.Column("beneish_dsri", sa.Float(), nullable=True),
        sa.Column("beneish_gmi", sa.Float(), nullable=True),
        sa.Column("beneish_aqi", sa.Float(), nullable=True),
        sa.Column("beneish_sgi", sa.Float(), nullable=True),
        sa.Column("beneish_depi", sa.Float(), nullable=True),
        sa.Column("beneish_sgai", sa.Float(), nullable=True),
        sa.Column("beneish_lvgi", sa.Float(), nullable=True),
        sa.Column("beneish_tata", sa.Float(), nullable=True),
        sa.Column("beneish_tata_bs", sa.Float(), nullable=True),
        sa.Column("beneish_m_score", sa.Float(), nullable=True),
        sa.Column("beneish_flag_178", sa.Boolean(), nullable=True),
        sa.Column("beneish_flag_222", sa.Boolean(), nullable=True),
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
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cyf_cik_fy", "company_year_features", ["cik", "fiscal_year"], unique=True)
    op.create_index("ix_cyf_accn", "company_year_features", ["accession_number"], unique=False)

    # 2. Create filing_sections
    op.create_table(
        "filing_sections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filing_id", sa.Integer(), nullable=True),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=25), nullable=False),
        sa.Column("section_type", sa.String(length=50), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("word_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sentence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_location", sa.String(length=255), nullable=True),
        sa.Column(
            "extraction_status", sa.String(length=50), server_default="success", nullable=False
        ),
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
        "ix_filing_sections_cik_fy_sec",
        "filing_sections",
        ["cik", "fiscal_year", "section_type"],
        unique=True,
    )

    # 3. Create filing_nlp_features
    op.create_table(
        "filing_nlp_features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filing_id", sa.Integer(), nullable=True),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=25), nullable=False),
        sa.Column("narrative_drift_score", sa.Float(), nullable=True),
        sa.Column("doc_embedding_cosine_drift", sa.Float(), nullable=True),
        sa.Column("mda_drift_score", sa.Float(), nullable=True),
        sa.Column("risk_drift_score", sa.Float(), nullable=True),
        sa.Column("vocab_jaccard_distance", sa.Float(), nullable=True),
        sa.Column("uncertainty_rate", sa.Float(), nullable=True),
        sa.Column("negative_sentiment_rate", sa.Float(), nullable=True),
        sa.Column("financial_uncertainty_rate", sa.Float(), nullable=True),
        sa.Column("avg_sentence_length", sa.Float(), nullable=True),
        sa.Column("readability_fog_index", sa.Float(), nullable=True),
        sa.Column("conditional_language_rate", sa.Float(), nullable=True),
        sa.Column("passive_voice_rate", sa.Float(), nullable=True),
        sa.Column("numeric_density", sa.Float(), nullable=True),
        sa.Column("drift_evidence_snippets", sa.JSON(), nullable=False),
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
    op.create_index("ix_fnlp_cik_fy", "filing_nlp_features", ["cik", "fiscal_year"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_fnlp_cik_fy", table_name="filing_nlp_features")
    op.drop_table("filing_nlp_features")
    op.drop_index("ix_filing_sections_cik_fy_sec", table_name="filing_sections")
    op.drop_table("filing_sections")
    op.drop_index("ix_cyf_accn", table_name="company_year_features")
    op.drop_index("ix_cyf_cik_fy", table_name="company_year_features")
    op.drop_table("company_year_features")
