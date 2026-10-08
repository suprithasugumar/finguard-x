"""Resolves CIKs and affected fiscal years for all 3400 AAER releases using SEC company master."""
from collections import Counter
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

import httpx
from rapidfuzz import fuzz

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import get_settings
from backend.app.db.models.entities import AAERCase
from backend.app.db.session import get_session_factory
from backend.app.ingest.aaer_parser import (
    AAERParser,
    normalize_company_name,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.resolve_aaer")


def run_aaer_resolution():
    settings = get_settings()
    session_factory = get_session_factory()
    session = session_factory()

    # 1. Fetch SEC Company Master Directory
    logger.info("Fetching SEC company_tickers_exchange.json...")
    client = httpx.Client(
        headers={"User-Agent": settings.validate_sec_user_agent()},
        follow_redirects=True,
    )
    resp = client.get("https://www.sec.gov/files/company_tickers_exchange.json")
    sec_data = resp.json()

    company_lookup = {}
    for row in sec_data.get("data", []):
        cik_int, name, ticker, exchange = row[0], row[1], row[2], row[3]
        cik = str(cik_int).zfill(10)
        norm = normalize_company_name(name)
        company_lookup[norm] = {
            "cik": cik,
            "name": name,
            "ticker": ticker,
            "exchange": exchange,
            "former_names": [],
        }

    logger.info(f"Loaded {len(company_lookup)} SEC companies into lookup.")
    parser = AAERParser(company_lookup=company_lookup)

    # 2. Query all AAER cases from database
    cases = session.query(AAERCase).all()
    logger.info(f"Resolving {len(cases)} AAER cases...")

    resolved_count = 0
    excluded_count = 0
    unresolved_count = 0
    exclusions_counter = Counter()

    for case in cases:
        title = case.company_name or ""
        # 1. Check exclusions (Section 12(j), Rule 102(e), auditor, individual)
        exclusion = parser.is_excluded_case(title, "")
        if exclusion:
            case.exclusion_reason = exclusion
            excluded_count += 1
            exclusions_counter[exclusion] += 1
            continue

        # 2. Extract respondent name
        resp_name = parser.extract_respondent_name(title, "") or title
        cik, method, score = parser.resolve_cik(resp_name, "")

        if cik:
            case.cik = cik
            resolved_count += 1
        else:
            unresolved_count += 1

        # 3. Extract affected fiscal years
        years_tuples = parser.extract_affected_fiscal_years(title)
        if years_tuples:
            case.affected_fiscal_years = [y for y, _, _ in years_tuples]

    session.commit()
    session.close()

    logger.info("==========================================")
    logger.info(f"Total AAER Cases:        {len(cases)}")
    logger.info(f"Excluded:                {excluded_count}")
    logger.info(f"Resolved to CIK:         {resolved_count}")
    logger.info(f"Unresolved to CIK:       {unresolved_count}")
    logger.info(f"Top Exclusions:          {dict(exclusions_counter.most_common(5))}")
    logger.info("==========================================")


if __name__ == "__main__":
    run_aaer_resolution()
