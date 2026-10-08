"""Scrapes the complete SEC AAER index (all pages 0-33) from SEC.gov and extracts full cases."""
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from bs4 import BeautifulSoup

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
from backend.app.ingest.facts_parser import parse_date
from backend.app.ingest.sec_client import SECClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.aaer_full")


def scrape_full_aaer_index(max_pages: int = 34) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Scrape all paginated tables from SEC AAER index."""
    settings = get_settings()
    client = SECClient()
    parser = AAERParser()

    all_raw_releases: List[Dict[str, Any]] = []
    exclusion_counts: Dict[str, int] = {}
    resolved_count = 0
    unresolved_count = 0

    base_url = "https://www.sec.gov/divisions/enforce/friactions.shtml"

    logger.info(f"Scraping SEC AAER index across {max_pages} pages...")
    for page in range(max_pages):
        page_url = f"{base_url}?page={page}"
        try:
            resp = client.get(page_url, use_cache=True)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch page {page}: HTTP {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.content, "html.parser")
            table = soup.find("table")
            if not table:
                logger.warning(f"No table found on page {page}")
                continue

            rows = table.find_all("tr")[1:]  # Skip header
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue

                date_text = cells[0].text.strip()
                rel_date = parse_date(date_text) or datetime.utcnow().date()

                resp_cell = cells[1]
                full_text = resp_cell.text.strip().replace("\n", " ")
                links = [a["href"] for a in resp_cell.find_all("a", href=True)]
                doc_link = links[0] if links else ""
                if doc_link and not doc_link.startswith("http"):
                    doc_link = f"https://www.sec.gov{doc_link}"

                # Extract AAER number
                aaer_match = re.search(r"AAER-(\d+)", full_text, re.IGNORECASE)
                aaer_num = f"AAER-{aaer_match.group(1)}" if aaer_match else f"REL-{date_text}"

                # Extract title/respondent
                title_match = re.split(r"Release No\.", full_text, flags=re.IGNORECASE)[0].strip()
                title = title_match if title_match else full_text

                # Check exclusion criteria (Section 12(j), Rule 102(e), auditor, individual)
                exclusion = parser.is_excluded_case(title, full_text)
                if exclusion:
                    exclusion_counts[exclusion] = exclusion_counts.get(exclusion, 0) + 1

                # Extract respondent corporate name
                resp_name = parser.extract_respondent_name(title, full_text) or title

                # Resolve CIK & affected years
                cik, match_method, score = parser.resolve_cik(resp_name, full_text)
                affected_years_tuples = parser.extract_affected_fiscal_years(full_text)
                affected_fys = [y for y, conf, rat in affected_years_tuples]

                if cik:
                    resolved_count += 1
                else:
                    unresolved_count += 1

                all_raw_releases.append({
                    "aaer_number": aaer_num,
                    "release_date": rel_date.isoformat(),
                    "company_name": resp_name,
                    "title": title,
                    "cik": cik,
                    "match_method": match_method,
                    "match_score": score,
                    "affected_fiscal_years": affected_fys,
                    "extracted_years": affected_years_tuples,
                    "source_url": doc_link,
                    "exclusion_reason": exclusion,
                })

            logger.info(f"Scraped page {page}/{max_pages-1} ({len(all_raw_releases)} total releases parsed so far)")
        except Exception as e:
            logger.error(f"Error scraping AAER page {page}: {e}")

    # Save to disk
    out_path = settings.PROCESSED_DIR / "aaer_full_index.json"
    settings.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_raw_releases, f, indent=2)

    logger.info(f"Saved full AAER index to {out_path} ({len(all_raw_releases)} total releases)")
    return all_raw_releases, exclusion_counts


def upsert_full_aaer_cases(raw_releases: List[Dict[str, Any]]):
    """Store all scraped AAER releases in aaer_cases table with earliest enforcement date."""
    session_factory = get_session_factory()
    session = session_factory()

    # Determine earliest enforcement date per company
    earliest_dates: Dict[str, str] = {}
    for r in raw_releases:
        key = r["cik"] or r["company_name"]
        rel_date = r["release_date"]
        if key not in earliest_dates or rel_date < earliest_dates[key]:
            earliest_dates[key] = rel_date

    inserted = 0
    updated = 0

    for r in raw_releases:
        key = r["cik"] or r["company_name"]
        enf_date_str = earliest_dates[key]
        enf_date = parse_date(enf_date_str)
        rel_date = parse_date(r["release_date"])

        existing = session.query(AAERCase).filter(AAERCase.aaer_number == r["aaer_number"]).first()
        if not existing:
            case = AAERCase(
                aaer_number=r["aaer_number"],
                release_date=rel_date,
                enforcement_date=enf_date,
                company_name=r["company_name"][:255],
                cik=r["cik"],
                affected_fiscal_years=r["affected_fiscal_years"],
                source_url=r["source_url"][:1000] if r["source_url"] else "",
                raw_text_path=None,
                exclusion_reason=r["exclusion_reason"],
            )
            session.add(case)
            inserted += 1
        else:
            existing.company_name = r["company_name"][:255]
            existing.cik = r["cik"] or existing.cik
            existing.affected_fiscal_years = r["affected_fiscal_years"]
            existing.exclusion_reason = r["exclusion_reason"]
            existing.enforcement_date = enf_date
            updated += 1

    session.commit()
    session.close()
    logger.info(f"AAER Database Upsert: {inserted} inserted, {updated} updated.")


if __name__ == "__main__":
    releases, exclusions = scrape_full_aaer_index(max_pages=34)
    upsert_full_aaer_cases(releases)
