"""SEC AAER Index and release document scraper with local disk caching."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.entities import AAERCase
from backend.app.ingest.aaer_parser import AAERParser, extract_text_from_pdf_bytes, parse_date
from backend.app.ingest.sec_client import SECClient

logger = logging.getLogger("finguard.ingest.aaer_scraper")


class AAERScraper:
    """Scrapes and parses SEC Accounting and Auditing Enforcement Releases (AAER)."""

    def __init__(
        self,
        sec_client: Optional[SECClient] = None,
        cache_dir: Optional[Path] = None,
        company_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        settings = get_settings()
        self.client = sec_client or SECClient()
        self.cache_dir = cache_dir or (settings.CACHE_DIR / "aaer")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.parser = AAERParser(company_lookup=company_lookup)

    def scrape_release(
        self, release_url: str, aaer_number: str, release_date_str: str, title: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch and parse an individual AAER release document (PDF or HTML)."""
        rel_date = parse_date(release_date_str) or datetime.utcnow().date()
        doc_cache_path = self.cache_dir / f"{aaer_number}.txt"

        # Check local text cache
        if doc_cache_path.exists():
            with open(doc_cache_path, "r", encoding="utf-8", errors="ignore") as f:
                raw_text = f.read()
        else:
            try:
                resp = self.client.get(release_url, use_cache=True)
                content_type = resp.headers.get("content-type", "").lower()

                if "pdf" in content_type or release_url.lower().endswith(".pdf"):
                    raw_text = extract_text_from_pdf_bytes(resp.content)
                else:
                    soup = BeautifulSoup(resp.content, "lxml")
                    raw_text = soup.get_text(separator="\n")

                with open(doc_cache_path, "w", encoding="utf-8") as f:
                    f.write(raw_text)
            except Exception as e:
                logger.warning(f"Failed to fetch AAER release from {release_url}: {e}")
                raw_text = title  # Fallback to title if document fetch fails

        # Check exclusion criteria (Section 12(j), Rule 102(e), auditor, individual-only)
        exclusion_reason = self.parser.is_excluded_case(title, raw_text)
        respondent_name = self.parser.extract_respondent_name(title, raw_text) or title

        cik, match_method, match_score = self.parser.resolve_cik(respondent_name, raw_text)
        extracted_years = self.parser.extract_affected_fiscal_years(raw_text)
        affected_fys = [y for y, conf, rat in extracted_years]

        return {
            "aaer_number": aaer_number,
            "release_date": rel_date,
            "enforcement_date": rel_date,  # Will be adjusted to earliest AAER date across cases
            "company_name": respondent_name,
            "cik": cik,
            "affected_fiscal_years": affected_fys,
            "extracted_details": extracted_years,
            "source_url": release_url,
            "raw_text_path": str(doc_cache_path),
            "exclusion_reason": exclusion_reason,
            "match_method": match_method,
            "match_score": match_score,
        }

    def process_and_store_cases(
        self, raw_releases: List[Dict[str, Any]], session: Session
    ) -> List[AAERCase]:
        """Aggregate AAER releases, enforce earliest enforcement date per company, and store."""
        # Group by resolved CIK or company_name to find earliest enforcement date
        earliest_dates: Dict[str, Any] = {}
        for r in raw_releases:
            key = r["cik"] or r["company_name"]
            r_date = r["release_date"]
            if key not in earliest_dates or r_date < earliest_dates[key]:
                earliest_dates[key] = r_date

        stored_cases: List[AAERCase] = []
        for r in raw_releases:
            key = r["cik"] or r["company_name"]
            enf_date = earliest_dates[key]

            # Check if case exists
            existing = (
                session.query(AAERCase).filter(AAERCase.aaer_number == r["aaer_number"]).first()
            )
            if not existing:
                case = AAERCase(
                    aaer_number=r["aaer_number"],
                    release_date=r["release_date"],
                    enforcement_date=enf_date,
                    company_name=r["company_name"],
                    cik=r["cik"],
                    affected_fiscal_years=r["affected_fiscal_years"],
                    source_url=r["source_url"],
                    raw_text_path=r["raw_text_path"],
                    exclusion_reason=r["exclusion_reason"],
                )
                session.add(case)
                stored_cases.append(case)
            else:
                existing.enforcement_date = enf_date
                existing.affected_fiscal_years = r["affected_fiscal_years"]
                existing.exclusion_reason = r["exclusion_reason"]
                stored_cases.append(existing)

        session.commit()
        return stored_cases
