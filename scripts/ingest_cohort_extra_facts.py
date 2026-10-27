"""Ingest newly curated US-GAAP tags for cohort CIKs from companyfacts.zip."""
import io
import json
import logging
import math
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import text
from backend.app.core.config import get_settings
from backend.app.db.session import get_session_factory
from backend.app.ingest.facts_parser import FactsParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.ingest_extra_facts")

NEW_TAGS = {
    "SalesRevenueServicesNet",
    "SalesRevenueGoodsGross",
    "OtherSalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "CostOfServices",
    "OperatingExpenses",
    "OtherGeneralAndAdministrativeExpense",
    "SellingExpense",
    "OtherSellingGeneralAndAdministrativeExpense",
    "AccountsReceivableGrossCurrent",
    "AccountsReceivableNet",
    "OtherReceivablesNetCurrent",
    "AccountsAndOtherReceivablesNetCurrent",
    "ReceivablesNet",
    "AccountsAndNotesReceivableNet",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
}


def ingest_extra_facts():
    settings = get_settings()
    session_factory = get_session_factory()
    session = session_factory()
    parser = FactsParser()

    # Load 801 cohort CIKs and FYEs
    with session.connection() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT c.cik, COALESCE(c.fiscal_year_end, '1231')
            FROM company_year_labels l
            JOIN companies c ON c.cik = l.cik
        """)).fetchall()
        cohort_ciks = {r[0]: r[1] for r in rows}

    logger.info(f"Targeting {len(cohort_ciks)} cohort CIKs for extra tags ingestion: {NEW_TAGS}")

    companyfacts_zip = settings.RAW_DIR / "companyfacts.zip"
    facts_to_insert = []
    cos_processed = 0

    t0 = time.time()
    with zipfile.ZipFile(companyfacts_zip, "r") as zf:
        namelist = set(zf.namelist())
        for cik, fye in cohort_ciks.items():
            fname = f"CIK{cik}.json"
            if fname not in namelist:
                continue

            try:
                raw_json = json.loads(zf.read(fname).decode("utf-8"))
            except Exception:
                continue

            cos_processed += 1
            # Extract facts using parser
            all_facts = parser.extract_raw_facts(raw_json, fiscal_year_end_mmdd=fye, min_fiscal_year=2008)
            # Filter only NEW_TAGS
            filtered = [f for f in all_facts if f["tag"] in NEW_TAGS]
            facts_to_insert.extend(filtered)

    logger.info(f"Extracted {len(facts_to_insert):,} facts across {cos_processed} companies in {time.time()-t0:.1f}s.")

    # Insert into financial_facts using COPY
    if facts_to_insert:
        buffer = io.StringIO()
        now_str = datetime.utcnow().isoformat()
        for b in facts_to_insert:
            p_start = str(b["period_start"]) if b.get("period_start") else "\\N"
            row = [
                b["cik"],
                b["tag"],
                b.get("unit") or "USD",
                str(b["value"]),
                p_start,
                str(b["period_end"]),
                str(b["fiscal_year"]),
                b.get("fiscal_period") or "FY",
                b.get("form_type") or "10-K",
                b["accession_number"],
                str(b["filed_date"]),
                "t" if b.get("is_original_filing", True) else "f",
                "t" if b.get("is_restated", False) else "f",
                now_str,
                now_str,
            ]
            buffer.write("\t".join(row) + "\n")
        buffer.seek(0)

        engine = get_settings().DATABASE_URL
        from backend.app.db.session import get_engine
        raw_conn = get_engine().raw_connection()
        with raw_conn.cursor() as cursor:
            cursor.copy_expert(
                """
                COPY financial_facts (
                    cik, tag, unit, value, period_start, period_end, fiscal_year,
                    fiscal_period, form_type, accession_number, filed_date,
                    is_original_filing, is_restated, created_at, updated_at
                ) FROM STDIN WITH (FORMAT text, DELIMITER '\t', NULL '\\N')
                """,
                buffer,
            )
        raw_conn.commit()
        raw_conn.close()
        logger.info(f"Successfully copied {len(facts_to_insert):,} extra facts into financial_facts table.")

    session.close()


if __name__ == "__main__":
    ingest_extra_facts()
