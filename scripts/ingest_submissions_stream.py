"""Stream ingestion of companies and 10-K filings from data/raw/submissions.zip."""
from datetime import date, datetime
import io
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import zipfile

import psycopg2
from psycopg2.extras import execute_values

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import get_settings
from backend.app.ingest.facts_parser import parse_date
from backend.app.ingest.fiscal_year import derive_fiscal_year

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.ingest_submissions")


def parse_submission_data(
    raw_json: Dict[str, Any],
    min_fiscal_year: int = 2008,
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Parse company info and 10-K filings from a submissions JSON."""
    cik_raw = str(raw_json.get("cik", "")).strip()
    if not cik_raw:
        return None
    cik = cik_raw.zfill(10)

    recent = raw_json.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    if not forms:
        return None

    # Check for 10-K presence
    has_10k = False
    for f in forms:
        if f in ("10-K", "10-K/A", "10-KT", "10-KT/A"):
            has_10k = True
            break
    if not has_10k:
        return None

    name = str(raw_json.get("name", "")).strip()
    tickers = raw_json.get("tickers", [])
    ticker = tickers[0] if tickers else None
    exchanges = raw_json.get("exchanges", [])
    exchange = exchanges[0] if exchanges else None
    sic = str(raw_json.get("sic", "")).strip() or None
    sic_desc = str(raw_json.get("sicDescription", "")).strip() or None
    fye = str(raw_json.get("fiscalYearEnd", "1231")).strip().zfill(4)
    state = str(raw_json.get("stateOfIncorporation", "")).strip() or None

    company = {
        "cik": cik,
        "name": name[:255] if name else f"CIK-{cik}",
        "ticker": ticker[:20] if ticker else None,
        "exchange": exchange[:20] if exchange else None,
        "sic": sic[:10] if sic else None,
        "sic_description": sic_desc[:255] if sic_desc else None,
        "fiscal_year_end": fye[:4],
        "state_location": state[:10] if state else None,
    }

    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accessions = recent.get("accessionNumber", [])
    is_xbrls = recent.get("isXBRL", [])
    acts = recent.get("act", [])

    filings = []
    has_target_year = False

    for i, form in enumerate(forms):
        if form not in ("10-K", "10-K/A", "10-KT", "10-KT/A"):
            continue

        f_date_str = filing_dates[i] if i < len(filing_dates) else None
        r_date_str = report_dates[i] if i < len(report_dates) else None
        accn = accessions[i] if i < len(accessions) else None
        if not accn:
            continue

        f_date = parse_date(f_date_str)
        r_date = parse_date(r_date_str) or f_date
        if not r_date:
            continue

        fy = derive_fiscal_year(r_date, fye)
        if fy >= min_fiscal_year:
            if fy >= 2010:
                has_target_year = True

            filings.append({
                "accession_number": str(accn).strip()[:50],
                "cik": cik,
                "form": form[:20],
                "filing_date": f_date,
                "report_date": r_date,
                "fiscal_year": fy,
                "fiscal_period": "FY",
                "act": str(acts[i])[:10] if i < len(acts) and acts[i] else "34",
                "is_xbrl": bool(is_xbrls[i]) if i < len(is_xbrls) else True,
            })

    if not has_target_year or not filings:
        return None

    return company, filings
