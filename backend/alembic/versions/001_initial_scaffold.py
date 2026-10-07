"""Initial scaffold migration: companies, filings, and request_log.

Revision ID: 001_initial_scaffold
Revises:
Create Date: 2026-10-07 21:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_scaffold"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create companies table
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sic", sa.String(length=4), nullable=True),
        sa.Column("sic_description", sa.String(length=255), nullable=True),
        sa.Column("fiscal_year_end", sa.String(length=4), nullable=True),
        sa.Column("state_location", sa.String(length=2), nullable=True),
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
        sa.UniqueConstraint("cik"),
    )
    op.create_index(op.f("ix_companies_cik"), "companies", ["cik"], unique=True)
    op.create_index(op.f("ix_companies_ticker"), "companies", ["ticker"], unique=False)
    op.create_index(op.f("ix_companies_sic"), "companies", ["sic"], unique=False)
    op.create_index("ix_companies_cik_ticker", "companies", ["cik", "ticker"], unique=False)

    # 2. Create filings table
    op.create_table(
        "filings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("accession_number", sa.String(length=25), nullable=False),
        sa.Column("form_type", sa.String(length=10), nullable=False, server_default="10-K"),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_period", sa.String(length=10), nullable=False, server_default="FY"),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("raw_file_path", sa.String(length=500), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
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
        sa.UniqueConstraint("accession_number"),
    )
    op.create_index(op.f("ix_filings_company_id"), "filings", ["company_id"], unique=False)
    op.create_index(op.f("ix_filings_cik"), "filings", ["cik"], unique=False)
    op.create_index(
        op.f("ix_filings_accession_number"), "filings", ["accession_number"], unique=True
    )
    op.create_index(op.f("ix_filings_fiscal_year"), "filings", ["fiscal_year"], unique=False)
    op.create_index(op.f("ix_filings_filing_date"), "filings", ["filing_date"], unique=False)
    op.create_index("ix_filings_cik_fy", "filings", ["cik", "fiscal_year"], unique=False)

    # 3. Create request_log table
    op.create_table(
        "request_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False, server_default="GET"),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_time_ms", sa.Float(), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_request_log_timestamp"), "request_log", ["timestamp"], unique=False)
    op.create_index(op.f("ix_request_log_cached"), "request_log", ["cached"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_request_log_cached"), table_name="request_log")
    op.drop_index(op.f("ix_request_log_timestamp"), table_name="request_log")
    op.drop_table("request_log")

    op.drop_index("ix_filings_cik_fy", table_name="filings")
    op.drop_index(op.f("ix_filings_filing_date"), table_name="filings")
    op.drop_index(op.f("ix_filings_fiscal_year"), table_name="filings")
    op.drop_index(op.f("ix_filings_accession_number"), table_name="filings")
    op.drop_index(op.f("ix_filings_cik"), table_name="filings")
    op.drop_index(op.f("ix_filings_company_id"), table_name="filings")
    op.drop_table("filings")

    op.drop_index("ix_companies_cik_ticker", table_name="companies")
    op.drop_index(op.f("ix_companies_sic"), table_name="companies")
    op.drop_index(op.f("ix_companies_ticker"), table_name="companies")
    op.drop_index(op.f("ix_companies_cik"), table_name="companies")
    op.drop_table("companies")
