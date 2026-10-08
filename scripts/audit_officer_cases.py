"""Audit sample of 30 officer-only AAER exclusions to evaluate issuer financial misstatement links."""
import json
import logging
from pathlib import Path
import random
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
import httpx
import pypdf

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import get_settings
from backend.app.ingest.aaer_parser import (
    AAERParser,
    extract_text_from_pdf_bytes,
    normalize_company_name,
)
from backend.app.ingest.sec_client import SECClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.audit_officer_cases")


def run_officer_audit(sample_size: int = 30, seed: int = 42):
    random.seed(seed)
    settings = get_settings()
    client = SECClient()
    parser = AAERParser()

    # Load full index
    index_path = settings.PROCESSED_DIR / "aaer_full_scraped_releases.json"
    with open(index_path, "r", encoding="utf-8") as f:
        all_releases = json.load(f)

    officer_cases = [r for r in all_releases if r.get("exclusion_reason") == "Individual officer/director proceeding"]
    logger.info(f"Total officer-only exclusions available: {len(officer_cases)}")

    # Sample deterministically
    sampled = random.sample(officer_cases, min(sample_size, len(officer_cases)))

    # Load SEC directory for issuer resolution
    logger.info("Loading SEC Company Directory for issuer matching...")
    ua = settings.validate_sec_user_agent()
    r = httpx.get("https://www.sec.gov/files/company_tickers.json", headers={"User-Agent": ua})
    company_lookup = {}
    if r.status_code == 200:
        for item in r.json().values():
            cik = str(item["cik_str"]).zfill(10)
            company_lookup[normalize_company_name(item["title"])] = {
                "cik": cik,
                "name": item["title"],
            }
    parser.company_lookup = company_lookup

    results: List[Dict[str, Any]] = []
    issuer_resolvable_count = 0
    financial_fraud_count = 0

    for i, case in enumerate(sampled):
        aaer_num = case["aaer_number"]
        rel_date = case["release_date"]
        officer_name = case["raw_title"]
        url = case.get("source_url") or ""

        text_content = ""
        # Try fetching release document if URL available
        if url and url.startswith("http"):
            try:
                resp = client.get(url, use_cache=True)
                if resp.status_code == 200:
                    if url.endswith(".pdf"):
                        text_content = extract_text_from_pdf_bytes(resp.content)
                    else:
                        soup = BeautifulSoup(resp.content, "html.parser")
                        text_content = soup.get_text(separator=" ")
            except Exception as e:
                logger.warning(f"Could not fetch document for {aaer_num}: {e}")

        combined_text = f"{officer_name}\n{text_content}"

        # 1. Identify Issuer Corporate Name
        # Search patterns: "CFO of XYZ", "Chief Executive Officer of XYZ", "officer of XYZ, Inc."
        issuer_candidate = None
        role_found = None
        role_match = re.search(
            r"\b(chief executive officer|ceo|chief financial officer|cfo|controller|vice president|vp|director|treasurer)\b\s+(?:of\s+)?([A-Z][A-Za-z0-9\s,\.&]{3,50}?(?:Inc\.|Corp\.|Corporation|Company|Co\.|LLC|Ltd\.|Holdings|Group))",
            combined_text,
            re.IGNORECASE,
        )
        if role_match:
            role_found = role_match.group(1).title()
            issuer_candidate = role_match.group(2).strip().rstrip(",")
        else:
            # Broader pattern: "XYZ, Inc. ('XYZ')"
            corp_match = re.search(
                r"([A-Z][A-Za-z0-9\s,\.&]{3,40}?(?:Inc|Corp|Corporation|Company|Co|LLC|Ltd)\b)",
                combined_text,
            )
            if corp_match:
                issuer_candidate = corp_match.group(1).strip().rstrip(",")

        # 2. Check if describes financial statement misstatements
        is_fin_fraud = bool(re.search(
            r"\b(accounting fraud|financial statements|revenue recognition|fictitious|falsif|misstat|books and records|internal accounting controls|grossly overstated|10-K|10-Q)\b",
            combined_text,
            re.IGNORECASE,
        ))
        if is_fin_fraud:
            financial_fraud_count += 1

        # 3. Resolve Issuer CIK
        resolved_cik = None
        if issuer_candidate:
            resolved_cik, _, _ = parser.resolve_cik(issuer_candidate, combined_text)
            if resolved_cik:
                issuer_resolvable_count += 1

        # 4. Extract Affected Years
        fys = parser.extract_affected_fiscal_years(combined_text)
        affected_fys = [y for y, _, _ in fys] if fys else [int(rel_date[:4]) - 1]

        results.append({
            "sample_index": i + 1,
            "aaer_number": aaer_num,
            "release_date": rel_date,
            "officer_name": officer_name,
            "officer_role": role_found or "Officer/Director",
            "issuer_name": issuer_candidate or "Unidentified",
            "resolved_cik": resolved_cik,
            "describes_financial_misstatement": is_fin_fraud,
            "affected_fiscal_years": affected_fys,
            "source_url": url,
        })

    # Summary Statistics
    logger.info("================== OFFICER-ONLY AUDIT SUMMARY ==================")
    logger.info(f"Sample Size:                         {sample_size}")
    logger.info(f"Describes Financial Misstatements:   {financial_fraud_count}/{sample_size} ({financial_fraud_count/sample_size*100:.1f}%)")
    logger.info(f"Resolvable Issuer CIK:               {issuer_resolvable_count}/{sample_size} ({issuer_resolvable_count/sample_size*100:.1f}%)")
    logger.info("================================================================")

    # Save detailed audit report to JSON
    out_file = settings.PROCESSED_DIR / "officer_only_audit_sample.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Saved audit sample details to {out_file}")
    return results, financial_fraud_count, issuer_resolvable_count


if __name__ == "__main__":
    run_officer_audit(sample_size=30, seed=42)
