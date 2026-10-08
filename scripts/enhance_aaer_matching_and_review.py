"""Enhance AAER corporate case matching and export ambiguous review cases."""
import csv
import io
import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pypdf
from rapidfuzz import fuzz
from sqlalchemy import create_engine, text

from backend.app.core.config import Settings
from backend.app.ingest.aaer_parser import AAERParser, normalize_company_name
from backend.app.ingest.sec_client import SECClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.enhance_aaer_matching")

CLEAN_SUB_PATTERNS = [
    re.compile(r"\(f/k/a\s+([^)]+)\)", re.IGNORECASE),
    re.compile(r"\(formerly\s+([^)]+)\)", re.IGNORECASE),
    re.compile(r"\(n/k/a\s+([^)]+)\)", re.IGNORECASE),
    re.compile(r"\(d/b/a\s+([^)]+)\)", re.IGNORECASE),
]

def extract_names_to_try(raw_name: str) -> List[Tuple[str, str]]:
    """Return list of (cleaned_name, source_type)."""
    candidates = []
    if not raw_name:
        return candidates

    # 1. Check parenthetical former names
    for pat in CLEAN_SUB_PATTERNS:
        match = pat.search(raw_name)
        if match:
            candidates.append((match.group(1).strip(), "former_name_parenthetical"))

    # 2. Main name with all parentheticals stripped
    main = re.sub(r"\(.*?\)", "", raw_name)
    # Strip 'and [Person/Entity]...'
    main = re.sub(r"\s+and\s+.*", "", main, flags=re.IGNORECASE)
    # Strip ', respondent.*' or 'defendants.*'
    main = re.sub(r",\s*(?:respondent|defendants?).*", "", main, flags=re.IGNORECASE)
    cleaned_main = main.strip()
    if cleaned_main:
        candidates.append((cleaned_main, "main_name"))

    return candidates


def run_enhancement():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    client = SECClient()
    parser = AAERParser()

    with engine.connect() as conn:
        companies = conn.execute(text("SELECT cik, name, ticker FROM companies")).fetchall()
        unmatched_cases = conn.execute(text("""
            SELECT id, aaer_number, company_name, source_url, release_date
            FROM aaer_cases
            WHERE exclusion_reason IS NULL AND cik IS NULL
            ORDER BY id
        """)).fetchall()

    logger.info(f"Loaded {len(companies)} companies. {len(unmatched_cases)} unmatched corporate cases.")

    # Build company lookup by normalized name
    comp_by_norm: Dict[str, Tuple[str, str, Optional[str]]] = {}
    ticker_to_cik: Dict[str, Tuple[str, str]] = {}
    for cik, name, ticker in companies:
        norm = normalize_company_name(name)
        if norm and norm not in comp_by_norm:
            comp_by_norm[norm] = (cik, name, ticker)
        if ticker:
            ticker_to_cik[ticker.upper().strip()] = (cik, name)

    matched_exact = 0
    matched_fuzzy_high = 0
    review_queue: List[Dict] = []
    newly_resolved_cases: List[Tuple[int, str, str, str]] = []  # (case_id, cik, match_type, matched_name)

    for cid, aaer_num, cname, url, rdate in unmatched_cases:
        candidates = extract_names_to_try(cname)
        found_cik = None
        match_type = ""
        matched_comp_name = ""

        # Try exact normalized match
        for cand_name, cand_type in candidates:
            norm = normalize_company_name(cand_name)
            if norm in comp_by_norm:
                cik, db_name, _ = comp_by_norm[norm]
                found_cik = cik
                match_type = f"exact_{cand_type}"
                matched_comp_name = db_name
                matched_exact += 1
                break

        # If not found, try ticker match if present in name
        if not found_cik:
            ticker_match = re.search(r"\b(?:NASDAQ|NYSE|AMEX|OTC):\s*([A-Z]{1,5})\b", cname or "", re.IGNORECASE)
            if ticker_match:
                tk = ticker_match.group(1).upper()
                if tk in ticker_to_cik:
                    cik, db_name = ticker_to_cik[tk]
                    found_cik = cik
                    match_type = "ticker_match"
                    matched_comp_name = db_name
                    matched_exact += 1

        # If not found, try fuzzy match on primary cleaned name
        if not found_cik and candidates:
            primary_norm = normalize_company_name(candidates[-1][0])
            if len(primary_norm) >= 5:
                best_score = 0.0
                best_match = None
                for norm_key, (cik, db_name, _) in comp_by_norm.items():
                    # Quick prefix check before full ratio for speed
                    if norm_key[:4] == primary_norm[:4] or norm_key[-4:] == primary_norm[-4:]:
                        score = fuzz.token_sort_ratio(primary_norm, norm_key)
                        if score > best_score:
                            best_score = score
                            best_match = (cik, db_name)

                if best_match and best_score >= 92.0:
                    found_cik, matched_comp_name = best_match
                    match_type = f"fuzzy_high_{best_score:.1f}"
                    matched_fuzzy_high += 1
                elif best_match and 80.0 <= best_score < 92.0:
                    # Low/medium confidence -> send to manual review queue, DO NOT auto-accept
                    review_queue.append({
                        "cik": best_match[0],
                        "company_name": cname,
                        "fiscal_year": rdate.year - 1 if rdate else "",
                        "aaer_number": aaer_num,
                        "label": 1,
                        "confidence": "medium" if best_score >= 85.0 else "low",
                        "source": "enhanced_fuzzy_match",
                        "rationale": f"Ambiguous fuzzy match ({best_score:.1f}%) to {best_match[1]} (CIK {best_match[0]})",
                        "review_status": "needs_review",
                        "reviewer_notes": f"Requires manual confirmation: candidate={best_match[1]}",
                    })

        if found_cik:
            newly_resolved_cases.append((cid, found_cik, match_type, matched_comp_name))

    logger.info(f"Resolved {len(newly_resolved_cases)} new corporate cases to CIK (exact: {matched_exact}, fuzzy >=92: {matched_fuzzy_high}).")
    logger.info(f"Sent {len(review_queue)} ambiguous cases to review queue.")

    # Update resolved cases in DB
    with engine.connect() as conn:
        for cid, cik, mtype, mname in newly_resolved_cases:
            conn.execute(text("UPDATE aaer_cases SET cik = :cik WHERE id = :cid"), {"cik": cik, "cid": cid})
        conn.commit()

    # Now extract PDF years for any newly resolved cases that have PDF URLs
    logger.info("Extracting PDF misstatement fiscal years for newly resolved cases...")
    enriched_new = 0
    for cid, cik, mtype, mname in newly_resolved_cases:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT source_url, aaer_number FROM aaer_cases WHERE id = :cid"), {"cid": cid}).fetchone()
        if not row or not row[0] or not row[0].endswith(".pdf"):
            continue

        url, aaer_num = row[0], row[1]
        try:
            resp = client.get(url, use_cache=True)
            if resp.status_code == 200:
                reader = pypdf.PdfReader(io.BytesIO(resp.content))
                pages_to_read = min(len(reader.pages), 8)
                full_text = "\n".join([reader.pages[p].extract_text() or "" for p in range(pages_to_read)])
                extracted = parser.extract_affected_fiscal_years(full_text)
                years = [yr for yr, conf, rat in extracted if 2000 <= yr <= 2026]
                if years:
                    with engine.connect() as conn:
                        conn.execute(text("UPDATE aaer_cases SET affected_fiscal_years = :years WHERE id = :cid"),
                                     {"years": json.dumps(years), "cid": cid})
                        conn.commit()
                    enriched_new += 1
        except Exception as e:
            logger.warning(f"Error enriching {aaer_num}: {e}")

    logger.info(f"Enriched {enriched_new} newly resolved cases with authentic PDF fiscal years.")

    # Export review queue to data/gold/label_review.csv
    review_csv_path = settings.GOLD_DIR / "label_review.csv"
    settings.GOLD_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "cik", "company_name", "fiscal_year", "aaer_number", "label",
        "confidence", "source", "rationale", "review_status", "reviewer_notes"
    ]
    with open(review_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(review_queue)
    logger.info(f"Saved {len(review_queue)} ambiguous cases to {review_csv_path}")

if __name__ == "__main__":
    run_enhancement()
