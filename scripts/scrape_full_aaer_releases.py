"""Scrape and parse full SEC AAER index (all 34 pages) with comprehensive exclusion and CIK resolution."""
from collections import Counter
from datetime import date, datetime
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from bs4 import BeautifulSoup
import httpx
from rapidfuzz import fuzz

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import get_settings
from backend.app.db.models.entities import AAERCase
from backend.app.db.session import get_session_factory
from backend.app.ingest.aaer_parser import AAERParser, normalize_company_name
from backend.app.ingest.facts_parser import parse_date
from backend.app.ingest.sec_client import SECClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.aaer_scraper")

# Common auditor firms / accounting firms
AUDITOR_NAMES = [
    "kpmg",
    "ernst & young",
    "deloitte",
    "pricewaterhousecoopers",
    "pwc",
    "bdo usa",
    "bdo seidman",
    "grant thornton",
    "crowe",
    "crowe horwath",
    "arthur andersen",
    "coopers & lybrand",
    "marcum",
    "cohnreznick",
    "anton & chia",
    "eisneramper",
    "mayer hoffman mccann",
    "malonebailey",
    "rbms",
    "friedman llp",
    "moore stephens",
    "moss adams",
    "plant & moran",
    "planta moran",
    "bakertilly",
    "baker tilly",
    "withumsmith+brown",
    "withum",
]

CORP_KEYWORDS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited",
    "llc", "lp", "plc", "sa", "nv", "bancorp", "bank", "holdings", "group", "technologies",
    "systems", "services", "energy", "pharma", "pharmaceuticals", "therapeutics", "motors",
    "capital", "financial", "properties", "trust", "realty", "communications", "international"
}


def load_sec_company_directory(user_agent: str) -> Dict[str, Dict[str, Any]]:
    """Load complete SEC company directory from SEC company_tickers.json and company_tickers_exchange.json."""
    logger.info("Loading SEC Company Directory...")
    client = httpx.Client(headers={"User-Agent": user_agent}, follow_redirects=True, timeout=30.0)

    company_lookup: Dict[str, Dict[str, Any]] = {}

    # 1. company_tickers.json (~10,400 companies)
    try:
        r1 = client.get("https://www.sec.gov/files/company_tickers.json")
        if r1.status_code == 200:
            data1 = r1.json()
            for item in data1.values():
                cik = str(item["cik_str"]).zfill(10)
                title = item["title"]
                ticker = item.get("ticker", "")
                norm = normalize_company_name(title)
                company_lookup[norm] = {
                    "cik": cik,
                    "name": title,
                    "ticker": ticker,
                    "exchange": "",
                    "former_names": [],
                }
    except Exception as e:
        logger.warning(f"Failed to fetch company_tickers.json: {e}")

    # 2. company_tickers_exchange.json (~8,000 companies with exchange info)
    try:
        r2 = client.get("https://www.sec.gov/files/company_tickers_exchange.json")
        if r2.status_code == 200:
            data2 = r2.json().get("data", [])
            for row in data2:
                cik = str(row[0]).zfill(10)
                name = row[1]
                ticker = row[2]
                exchange = row[3]
                norm = normalize_company_name(name)
                if norm not in company_lookup:
                    company_lookup[norm] = {
                        "cik": cik,
                        "name": name,
                        "ticker": ticker,
                        "exchange": exchange,
                        "former_names": [],
                    }
                else:
                    company_lookup[norm]["exchange"] = exchange
    except Exception as e:
        logger.warning(f"Failed to fetch company_tickers_exchange.json: {e}")

    logger.info(f"Loaded {len(company_lookup)} distinct normalized companies from SEC directory.")
    return company_lookup


def classify_and_clean_case(
    raw_title: str,
    full_text: str,
    company_lookup: Dict[str, Dict[str, Any]],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Classify case exclusions and extract primary corporate respondent.

    Returns: (corporate_respondent, exclusion_reason, unres_reason)
    """
    clean_title = re.sub(r"\(order.*?\)", "", raw_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r"\(corrected\)", "", clean_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r"\s+", " ", clean_title).strip()
    combined_lower = f"{clean_title} {full_text}".lower()

    # 1. Section 12(j) - delinquent periodic filings revocation
    if "12(j)" in combined_lower or "section 12(j)" in combined_lower:
        return None, "Section 12(j) delinquent filing", None

    # 2. Rule 102(e) - suspension of appearance
    if "102(e)" in combined_lower or "rule 102(e)" in combined_lower:
        return None, "Rule 102(e) professional sanction", None

    # 3. Auditor sanctions
    for aud in AUDITOR_NAMES:
        if aud in clean_title.lower():
            return None, f"Auditor firm sanction: {aud.upper()}", None

    if re.search(r"\b(llp|cpa\s+firm|public\s+accounting)\b", clean_title.lower()):
        return None, "Auditor firm sanction: Accounting Firm LLP", None

    # 4. Check for Corporate Respondent in title
    # Examples:
    # "Key Tronic Corporation, Brett R. Larsen, CPA, and Nicholas S. Fasciana"
    # "L&L Energy, Inc. and Dickson Lee, CPA"
    # "Valeant Pharmaceuticals International, Inc."
    parts = re.split(r",\s+(?:and\s+)?|\s+and\s+", clean_title)
    corp_candidate = None
    for p in parts:
        p_clean = p.strip()
        words = set(re.findall(r"[a-z]+", p_clean.lower()))
        norm = normalize_company_name(p_clean)
        if norm in company_lookup:
            corp_candidate = p_clean
            break
        if words.intersection(CORP_KEYWORDS):
            corp_candidate = p_clean
            break

    if corp_candidate:
        return corp_candidate, None, None

    # 5. If no corporate keywords and ends in CPA / CA / individual
    if re.search(r"\b(cpa|ca|esq)\b", clean_title.lower()):
        return None, "Individual accountant/attorney proceeding", None

    # 6. Check if title looks like a person's name (2 or 3 capitalized words, no corporate keyword)
    words = clean_title.split()
    if 2 <= len(words) <= 4 and not any(w.lower() in CORP_KEYWORDS for w in words):
        return None, "Individual officer/director proceeding", None

    # Otherwise treat as respondent
    return clean_title, None, None


def run_full_aaer_pipeline(max_pages: int = 34):
    """Run full scraping and parsing pipeline across all SEC AAER index pages."""
    settings = get_settings()
    client = SECClient()
    user_agent = settings.validate_sec_user_agent()

    company_lookup = load_sec_company_directory(user_agent)
    parser = AAERParser(company_lookup=company_lookup)

    base_url = "https://www.sec.gov/enforcement-litigation/accounting-auditing-enforcement-releases"
    all_releases = []

    logger.info(f"Starting AAER index scraping across {max_pages} pages...")

    total_scraped = 0
    exclusion_reasons = Counter()
    unresolved_reasons = Counter()
    resolved_count = 0
    excluded_count = 0
    unresolved_count = 0

    for page in range(max_pages):
        url = f"{base_url}?page={page}"
        try:
            resp = client.get(url, use_cache=True)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch page {page}: HTTP {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.content, "html.parser")
            table = soup.find("table")
            if not table:
                logger.warning(f"No table on page {page}")
                continue

            rows = table.find_all("tr")[1:]
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue

                total_scraped += 1
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
                aaer_num = f"AAER-{aaer_match.group(1)}" if aaer_match else f"REL-{date_text}-{total_scraped}"

                # Title before Release No.
                title_match = re.split(r"Release No\.", full_text, flags=re.IGNORECASE)[0].strip()
                title = title_match if title_match else full_text

                # Classify case and clean respondent
                corp_resp, exclusion, _ = classify_and_clean_case(title, full_text, company_lookup)

                cik = None
                match_method = "excluded"
                match_score = 0.0
                unres_reason = None
                affected_fys_tuples = []

                if exclusion:
                    excluded_count += 1
                    exclusion_reasons[exclusion] += 1
                else:
                    # Attempt CIK resolution
                    cik, match_method, match_score = parser.resolve_cik(corp_resp or title, full_text)
                    if cik:
                        resolved_count += 1
                    else:
                        unresolved_count += 1
                        unres_reason = "No matching issuer in SEC directory" if corp_resp else "Unidentified respondent"
                        unresolved_reasons[unres_reason] += 1

                    # Extract affected fiscal years
                    affected_fys_tuples = parser.extract_affected_fiscal_years(full_text)
                    # If none in short summary, check year from release date as medium/low confidence candidate
                    if not affected_fys_tuples and rel_date:
                        inferred_yr = rel_date.year - 1
                        if 2000 <= inferred_yr <= 2026:
                            affected_fys_tuples = [(inferred_yr, "medium", f"Inferred from enforcement release year {rel_date.year}")]

                all_releases.append({
                    "aaer_number": aaer_num,
                    "release_date": rel_date.isoformat(),
                    "company_name": (corp_resp or title)[:255],
                    "raw_title": title,
                    "full_text": full_text[:500],
                    "cik": cik,
                    "match_method": match_method,
                    "match_score": match_score,
                    "exclusion_reason": exclusion,
                    "unresolved_reason": unres_reason,
                    "affected_fiscal_years": [y for y, _, _ in affected_fys_tuples],
                    "affected_year_details": affected_fys_tuples,
                    "source_url": doc_link,
                })

            logger.info(f"Scraped page {page}/{max_pages-1}: {len(all_releases)} releases cumulative.")
        except Exception as e:
            logger.error(f"Error scraping page {page}: {e}")

    # Save to JSON
    out_json = settings.PROCESSED_DIR / "aaer_full_scraped_releases.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(all_releases, f, indent=2)

    logger.info(f"Saved {len(all_releases)} releases to {out_json}")

    # Upsert into PostgreSQL aaer_cases table
    session_factory = get_session_factory()
    session = session_factory()

    # Determine earliest enforcement date per CIK / company
    earliest_dates = {}
    for r in all_releases:
        key = r["cik"] or r["company_name"]
        d = r["release_date"]
        if key not in earliest_dates or d < earliest_dates[key]:
            earliest_dates[key] = d

    inserted = 0
    updated = 0
    for r in all_releases:
        key = r["cik"] or r["company_name"]
        enf_date = parse_date(earliest_dates[key])
        rel_date = parse_date(r["release_date"])

        existing = session.query(AAERCase).filter(AAERCase.aaer_number == r["aaer_number"]).first()
        if not existing:
            case = AAERCase(
                aaer_number=r["aaer_number"],
                release_date=rel_date,
                enforcement_date=enf_date,
                company_name=r["company_name"],
                cik=r["cik"],
                affected_fiscal_years=r["affected_fiscal_years"],
                source_url=r["source_url"][:1000] if r["source_url"] else "",
                raw_text_path=None,
                exclusion_reason=r["exclusion_reason"],
            )
            session.add(case)
            inserted += 1
        else:
            existing.company_name = r["company_name"]
            existing.cik = r["cik"] or existing.cik
            existing.affected_fiscal_years = r["affected_fiscal_years"]
            existing.exclusion_reason = r["exclusion_reason"]
            existing.enforcement_date = enf_date
            updated += 1

    session.commit()
    session.close()

    logger.info(f"Database Upsert: {inserted} inserted, {updated} updated.")

    # Compute Positive Company-Years Breakdown
    pos_by_conf = Counter()
    pos_by_fy = Counter()

    for r in all_releases:
        if r["cik"] and not r["exclusion_reason"]:
            for yr, conf, rat in r["affected_year_details"]:
                pos_by_conf[conf] += 1
                pos_by_fy[yr] += 1

    # Report Summary
    print("\n================== FULL AAER SCRAPE & AUDIT REPORT ==================")
    print(f"Total AAERs Scraped:             {total_scraped}")
    print(f"Total AAERs Parsed:              {len(all_releases)}")
    print(f"Excluded Releases:               {excluded_count}")
    print(f"Resolved to CIK:                 {resolved_count}")
    print(f"Unresolved to CIK:               {unresolved_count}")
    print("\n--- Exclusions by Reason ---")
    for reason, count in exclusion_reasons.most_common():
        print(f"  {reason:<45}: {count}")
    print("\n--- Unresolved by Reason ---")
    for reason, count in unresolved_reasons.most_common():
        print(f"  {reason:<45}: {count}")
    print("\n--- Positive Company-Years by Confidence ---")
    for conf, count in pos_by_conf.most_common():
        print(f"  {conf:<15}: {count}")
    print("\n--- Positive Company-Years by Fiscal Year (FY2010+) ---")
    for yr in sorted(pos_by_fy.keys()):
        if yr >= 2010:
            print(f"  FY{yr}: {pos_by_fy[yr]}")
    print("=====================================================================\n")

    return all_releases


if __name__ == "__main__":
    run_full_aaer_pipeline(max_pages=34)

