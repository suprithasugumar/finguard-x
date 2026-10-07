"""Phase 1 Gate Validation: Counts, missing rates, spot-checks, and cache audit."""
from collections import defaultdict
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List

import pandas as pd
from sqlalchemy import func, select

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.db.models.entities import (
    AAERCase,
    Company,
    CompanyYearLabel,
    Filing,
    FinancialFact,
    RequestLog,
)
from backend.app.db.session import get_session_factory
from backend.app.ingest.facts_parser import load_curated_tags

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.validate")


def validate_phase_1():
    session_factory = get_session_factory()
    session = session_factory()

    print("==================================================")
    print(" FIN-GUARD-X PHASE 1 GATE VERIFICATION")
    print("==================================================")

    # 1. Database Counts Table
    comp_count = session.query(func.count(Company.id)).scalar()
    filing_count = session.query(func.count(Filing.id)).scalar()
    facts_count = session.query(func.count(FinancialFact.id)).scalar()
    cases_count = session.query(func.count(AAERCase.id)).scalar()
    pos_count = session.query(func.count(CompanyYearLabel.id)).filter(CompanyYearLabel.label == 1).scalar()
    ctrl_count = session.query(func.count(CompanyYearLabel.id)).filter(CompanyYearLabel.label == 0).scalar()
    logs_count = session.query(func.count(RequestLog.id)).scalar()
    cached_logs_count = session.query(func.count(RequestLog.id)).filter(RequestLog.cached.is_(True)).scalar()

    print("\n--- 1. DATABASE ENTITY COUNTS ---")
    print(f"Companies:                   {comp_count}")
    print(f"10-K Filings:                {filing_count}")
    print(f"Raw Financial Facts:         {facts_count}")
    print(f"AAER Cases:                  {cases_count}")
    print(f"Positive Labels (y=1):       {pos_count}")
    print(f"Matched Controls (y=0):      {ctrl_count}")
    print(f"Request Log Audits:          {logs_count} (Cached Hits: {cached_logs_count})")

    # Positives by Confidence
    conf_counts = (
        session.query(CompanyYearLabel.label_confidence, func.count(CompanyYearLabel.id))
        .filter(CompanyYearLabel.label == 1)
        .group_by(CompanyYearLabel.label_confidence)
        .all()
    )
    print("\nPositives by Confidence:")
    for conf, cnt in conf_counts:
        print(f"  - {conf}: {cnt}")

    # 2. Tag Missingness Rate per Fiscal Year
    curated_tags = load_curated_tags()
    years = sorted(list(range(2010, 2021)))

    print("\n--- 2. TAG MISSING-RATE TABLE (FY2010 - FY2020) ---")
    # Query distinct CIKs per year that have original filings
    filings_per_fy = dict(
        session.query(Filing.fiscal_year, func.count(func.distinct(Filing.cik)))
        .filter(Filing.is_amendment.is_(False), Filing.fiscal_year.in_(years))
        .group_by(Filing.fiscal_year)
        .all()
    )

    facts_per_fy_tag = {
        (r[0], r[1]): r[2]
        for r in session.query(
            FinancialFact.fiscal_year,
            FinancialFact.tag,
            func.count(func.distinct(FinancialFact.cik)),
        )
        .filter(FinancialFact.is_original_filing.is_(True), FinancialFact.fiscal_year.in_(years))
        .group_by(FinancialFact.fiscal_year, FinancialFact.tag)
        .all()
    }

    core_display_tags = [
        "Assets", "Liabilities", "StockholdersEquity", "Revenues",
        "OperatingIncomeLoss", "NetIncomeLoss", "AccountsReceivableNetCurrent",
        "InventoryNet", "NetCashProvidedByUsedInOperatingActivities"
    ]

    print(f"{'Tag':<45} | " + " | ".join(f"{fy}" for fy in years))
    print("-" * 130)
    for tag in core_display_tags:
        row_str = f"{tag:<45} | "
        vals = []
        for fy in years:
            total_firms = filings_per_fy.get(fy, 0)
            firms_with_tag = facts_per_fy_tag.get((fy, tag), 0)
            if total_firms > 0:
                missing_pct = ((total_firms - firms_with_tag) / total_firms) * 100.0
                vals.append(f"{missing_pct:>4.0f}%")
            else:
                vals.append(" N/A")
        print(row_str + " | ".join(vals))

    # 3. Spot Check: 10 Positives and 10 Controls End-to-End
    print("\n--- 3. END-TO-END SPOT CHECKS ---")
    positives = (
        session.query(CompanyYearLabel, Company)
        .join(Company, Company.cik == CompanyYearLabel.cik)
        .filter(CompanyYearLabel.label == 1)
        .limit(10)
        .all()
    )

    print("\n[TOP POSITIVE SPOT CHECKS (y=1)]")
    for cyl, comp in positives:
        filing = (
            session.query(Filing)
            .filter(Filing.cik == cyl.cik, Filing.fiscal_year == cyl.fiscal_year, Filing.is_amendment.is_(False))
            .first()
        )
        case = session.query(AAERCase).filter(AAERCase.id == cyl.aaer_case_id).first()
        accn = filing.accession_number if filing else "NO_FILING"
        aaer = case.aaer_number if case else "N/A"
        print(f"CIK: {cyl.cik} | FY: {cyl.fiscal_year} | {comp.name[:30]:<30} | AAER: {aaer:<10} | 10-K: {accn} | Conf: {cyl.label_confidence}")

    controls = (
        session.query(CompanyYearLabel, Company)
        .join(Company, Company.cik == CompanyYearLabel.cik)
        .filter(CompanyYearLabel.label == 0)
        .limit(10)
        .all()
    )

    print("\n[TOP CONTROL SPOT CHECKS (y=0)]")
    for cyl, comp in controls:
        filing = (
            session.query(Filing)
            .filter(Filing.cik == cyl.cik, Filing.fiscal_year == cyl.fiscal_year, Filing.is_amendment.is_(False))
            .first()
        )
        accn = filing.accession_number if filing else "NO_FILING"
        dist = f"{cyl.match_distance:.3f}" if cyl.match_distance is not None else "0.000"
        print(f"CIK: {cyl.cik} | FY: {cyl.fiscal_year} | {comp.name[:30]:<30} | Matched Pos ID: {cyl.matched_positive_id} | Dist: {dist} | 10-K: {accn}")

    print("\n==================================================")
    print(" VERIFICATION COMPLETE")
    print("==================================================")
    session.close()


if __name__ == "__main__":
    validate_phase_1()
