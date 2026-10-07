"""Add financial_facts, aaer_cases, and company_year_labels tables.

Revision ID: 002_sec_ingest_and_labels
Revises: 001_initial_scaffold
Create Date: 2026-10-07 22:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_sec_ingest_and_labels"
down_revision: Union[str, None] = "001_initial_scaffold"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend companies
    op.add_column("companies", sa.Column("exchange", sa.String(length=10), nullable=True))

    # 2. Extend filings
    op.add_column("filings", sa.Column("period_end", sa.Date(), nullable=True))
    op.add_column("filings", sa.Column("primary_document", sa.String(length=500), nullable=True))
    op.add_column(
        "filings",
        sa.Column("is_amendment", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(op.f("ix_filings_period_end"), "filings", ["period_end"], unique=False)
    op.create_index(op.f("ix_filings_is_amendment"), "filings", ["is_amendment"], unique=False)

    # 3. Create financial_facts
    op.create_table(
        "financial_facts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("tag", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=20), server_default="USD", nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_period", sa.String(length=10), server_default="FY", nullable=False),
        sa.Column("form_type", sa.String(length=10), server_default="10-K", nullable=False),
        sa.Column("accession_number", sa.String(length=25), nullable=False),
        sa.Column("filed_date", sa.Date(), nullable=False),
        sa.Column(
            "is_original_filing", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("is_restated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_financial_facts_cik"), "financial_facts", ["cik"], unique=False)
    op.create_index(op.f("ix_financial_facts_tag"), "financial_facts", ["tag"], unique=False)
    op.create_index(
        op.f("ix_financial_facts_period_end"), "financial_facts", ["period_end"], unique=False
    )
    op.create_index(
        op.f("ix_financial_facts_fiscal_year"), "financial_facts", ["fiscal_year"], unique=False
    )
    op.create_index(
        op.f("ix_financial_facts_accession_number"),
        "financial_facts",
        ["accession_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_financial_facts_filed_date"), "financial_facts", ["filed_date"], unique=False
    )
    op.create_index(
        op.f("ix_financial_facts_is_original_filing"),
        "financial_facts",
        ["is_original_filing"],
        unique=False,
    )
    op.create_index(
        op.f("ix_financial_facts_is_restated"), "financial_facts", ["is_restated"], unique=False
    )
    op.create_index(
        "ix_facts_cik_fy_tag", "financial_facts", ["cik", "fiscal_year", "tag"], unique=False
    )
    op.create_index(
        "ix_facts_cik_tag_period", "financial_facts", ["cik", "tag", "period_end"], unique=False
    )

    # 4. Create aaer_cases
    op.create_table(
        "aaer_cases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("aaer_number", sa.String(length=20), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=False),
        sa.Column("enforcement_date", sa.Date(), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=True),
        sa.Column("affected_fiscal_years", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("raw_text_path", sa.String(length=500), nullable=True),
        sa.Column("exclusion_reason", sa.String(length=255), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_aaer_cases_aaer_number"), "aaer_cases", ["aaer_number"], unique=False)
    op.create_index(
        op.f("ix_aaer_cases_release_date"), "aaer_cases", ["release_date"], unique=False
    )
    op.create_index(
        op.f("ix_aaer_cases_enforcement_date"), "aaer_cases", ["enforcement_date"], unique=False
    )
    op.create_index(op.f("ix_aaer_cases_cik"), "aaer_cases", ["cik"], unique=False)
    op.create_index(
        "ix_aaer_cases_cik_enf", "aaer_cases", ["cik", "enforcement_date"], unique=False
    )

    # 5. Create company_year_labels
    op.create_table(
        "company_year_labels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("label", sa.Integer(), nullable=False),
        sa.Column("label_confidence", sa.String(length=20), server_default="high", nullable=False),
        sa.Column("label_rationale", sa.Text(), nullable=False),
        sa.Column("aaer_case_id", sa.Integer(), nullable=True),
        sa.Column("matched_positive_id", sa.Integer(), nullable=True),
        sa.Column("match_distance", sa.Float(), nullable=True),
        sa.Column("review_status", sa.String(length=30), server_default="auto", nullable=False),
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
        sa.ForeignKeyConstraint(["aaer_case_id"], ["aaer_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["matched_positive_id"], ["company_year_labels.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_company_year_labels_cik"), "company_year_labels", ["cik"], unique=False
    )
    op.create_index(
        op.f("ix_company_year_labels_fiscal_year"),
        "company_year_labels",
        ["fiscal_year"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_year_labels_label"), "company_year_labels", ["label"], unique=False
    )
    op.create_index(
        op.f("ix_company_year_labels_aaer_case_id"),
        "company_year_labels",
        ["aaer_case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_year_labels_matched_positive_id"),
        "company_year_labels",
        ["matched_positive_id"],
        unique=False,
    )
    op.create_index("ix_cyl_cik_fy", "company_year_labels", ["cik", "fiscal_year"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cyl_cik_fy", table_name="company_year_labels")
    op.drop_index(
        op.f("ix_company_year_labels_matched_positive_id"), table_name="company_year_labels"
    )
    op.drop_index(op.f("ix_company_year_labels_aaer_case_id"), table_name="company_year_labels")
    op.drop_index(op.f("ix_company_year_labels_label"), table_name="company_year_labels")
    op.drop_index(op.f("ix_company_year_labels_fiscal_year"), table_name="company_year_labels")
    op.drop_index(op.f("ix_company_year_labels_cik"), table_name="company_year_labels")
    op.drop_table("company_year_labels")

    op.drop_index("ix_aaer_cases_cik_enf", table_name="aaer_cases")
    op.drop_index(op.f("ix_aaer_cases_cik"), table_name="aaer_cases")
    op.drop_index(op.f("ix_aaer_cases_enforcement_date"), table_name="aaer_cases")
    op.drop_index(op.f("ix_aaer_cases_release_date"), table_name="aaer_cases")
    op.drop_index(op.f("ix_aaer_cases_aaer_number"), table_name="aaer_cases")
    op.drop_table("aaer_cases")

    op.drop_index("ix_facts_cik_tag_period", table_name="financial_facts")
    op.drop_index("ix_facts_cik_fy_tag", table_name="financial_facts")
    op.drop_index(op.f("ix_financial_facts_is_restated"), table_name="financial_facts")
    op.drop_index(op.f("ix_financial_facts_is_original_filing"), table_name="financial_facts")
    op.drop_index(op.f("ix_financial_facts_filed_date"), table_name="financial_facts")
    op.drop_index(op.f("ix_financial_facts_accession_number"), table_name="financial_facts")
    op.drop_index(op.f("ix_financial_facts_fiscal_year"), table_name="financial_facts")
    op.drop_index(op.f("ix_financial_facts_period_end"), table_name="financial_facts")
    op.drop_index(op.f("ix_financial_facts_tag"), table_name="financial_facts")
    op.drop_index(op.f("ix_financial_facts_cik"), table_name="financial_facts")
    op.drop_table("financial_facts")

    op.drop_index(op.f("ix_filings_is_amendment"), table_name="filings")
    op.drop_index(op.f("ix_filings_period_end"), table_name="filings")
    op.drop_column("filings", "is_amendment")
    op.drop_column("filings", "primary_document")
    op.drop_column("filings", "period_end")

    op.drop_column("companies", "exchange")
