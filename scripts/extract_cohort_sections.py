"""Extract Sections for all 1,106 Cohort Filings.

Extracts Item 7 (MD&A), Item 1A (Risk Factors), Related-Party Footnote, and Item 13 (Certain Relationships)
for every cohort company-year filing in FinGuard-X.
Uses multi-threaded fetching with thread-safe rate limiting complying with SEC EDGAR 10 req/s rules.
Reports section extraction success rate by fiscal year.
"""

import os
import sys
import json
import time
import zipfile
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Set, Tuple, Any, List, Optional

import urllib.request
import pandas as pd
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.config import Settings
from backend.app.ingest.text_extractor import FilingTextExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("finguard.extract_sections")


class RateLimiter:
    """Thread-safe rate limiter for SEC EDGAR requests (max 8 requests/second).
    Schedules request timestamps under lock, sleeps outside lock for true concurrency.
    """
    def __init__(self, max_per_second: float = 8.0):
        self.lock = threading.Lock()
        self.interval = 1.0 / max_per_second
        self.next_available_time = time.time()

    def wait(self):
        with self.lock:
            now = time.time()
            scheduled_time = max(now, self.next_available_time)
            self.next_available_time = scheduled_time + self.interval
        wait_seconds = scheduled_time - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)


def build_submissions_index(submissions_zip_path: Path, needed_ciks: Set[str]) -> Dict[str, Dict[str, str]]:
    logger.info(f"Indexing submissions.zip for {len(needed_ciks)} CIKs...")
    cik_map: Dict[str, Dict[str, str]] = {}
    with zipfile.ZipFile(submissions_zip_path, "r") as zf:
        name_list = set(zf.namelist())
        for cik in needed_ciks:
            fn = f"CIK{cik}.json"
            if fn not in name_list:
                continue
            try:
                data = json.loads(zf.read(fn))
                acc_to_doc = {}
                recent = data.get("filings", {}).get("recent", {})
                accns = recent.get("accessionNumber", [])
                pdocs = recent.get("primaryDocument", [])
                for acc, doc in zip(accns, pdocs):
                    if doc:
                        acc_to_doc[acc] = doc

                for f_meta in data.get("filings", {}).get("files", []):
                    f_name = f_meta.get("name")
                    if f_name and f_name in name_list:
                        old_d = json.loads(zf.read(f_name))
                        old_accns = old_d.get("accessionNumber", [])
                        old_pdocs = old_d.get("primaryDocument", [])
                        for acc, doc in zip(old_accns, old_pdocs):
                            if doc:
                                acc_to_doc[acc] = doc

                cik_map[cik] = acc_to_doc
            except Exception as e:
                logger.warning(f"Error reading CIK{cik}.json: {e}")
    logger.info(f"Submissions index built for {len(cik_map)} CIKs.")
    return cik_map


def fetch_and_extract(
    row: Dict[str, Any],
    rate_limiter: RateLimiter,
    extractor: FilingTextExtractor,
    headers: Dict[str, str]
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[str]]:
    fid = row["id"]
    cik = row["cik"]
    fy = row["fiscal_year"]
    acc = row["accession_number"]
    pdoc = row["primary_document"]

    if not pdoc:
        return row, None, "No primary document found"

    cik_int = int(cik)
    acc_clean = acc.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{pdoc}"

    raw_html = ""
    for attempt in range(2):
        try:
            rate_limiter.wait()
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_html = resp.read().decode("utf-8", errors="ignore")
            break
        except Exception as e:
            if attempt == 1:
                return row, None, f"Failed to fetch {url}: {e}"
            time.sleep(1.0)

    try:
        sections = extractor.extract_sections(raw_html)
        return row, sections, None
    except Exception as e:
        return row, None, f"Extraction failed: {e}"


def main():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL, pool_size=10, max_overflow=5)
    extractor = FilingTextExtractor()
    rate_limiter = RateLimiter(max_per_second=8.0)
    submissions_zip = settings.RAW_DIR / "submissions.zip"
    headers = {"User-Agent": "FinGuardX-Research audit@finguard-x.ai"}

    with engine.connect() as conn:
        cohort_filings = pd.read_sql("""
            SELECT f.id, f.cik, f.fiscal_year, f.accession_number, f.primary_document
            FROM company_year_labels l
            JOIN filings f ON f.cik = l.cik AND f.fiscal_year = l.fiscal_year AND f.is_amendment = false
            ORDER BY f.fiscal_year, f.cik
        """, conn)
        logger.info(f"Targeting {len(cohort_filings)} cohort filings for section extraction.")

        # Update primary_document if any still missing
        missing_pdoc = cohort_filings[cohort_filings["primary_document"].isna()]
        if len(missing_pdoc) > 0:
            sub_index = build_submissions_index(submissions_zip, set(missing_pdoc["cik"].unique()))
            updated_pdocs = 0
            for idx, row in missing_pdoc.iterrows():
                pdoc = sub_index.get(row["cik"], {}).get(row["accession_number"])
                if pdoc:
                    conn.execute(
                        text("UPDATE filings SET primary_document = :pdoc WHERE id = :fid"),
                        {"pdoc": pdoc, "fid": row["id"]}
                    )
                    cohort_filings.at[idx, "primary_document"] = pdoc
                    updated_pdocs += 1
            conn.commit()
            logger.info(f"Updated primary_document in filings table for {updated_pdocs} filings.")

        # Check existing complete sections
        existing_full = pd.read_sql("""
            SELECT cik, fiscal_year
            FROM filing_sections
            WHERE section_type IN ('mda', 'risk_factors', 'item_13') AND word_count > 0
            GROUP BY cik, fiscal_year
            HAVING COUNT(DISTINCT section_type) >= 3
        """, conn)
        existing_full_set = set(zip(existing_full["cik"], existing_full["fiscal_year"]))
        logger.info(f"Found {len(existing_full_set)} filings already having all major sections extracted.")

    to_process = []
    for _, row in cohort_filings.iterrows():
        if (row["cik"], row["fiscal_year"]) not in existing_full_set:
            to_process.append(row.to_dict())

    logger.info(f"Filings needing extraction: {len(to_process)}")

    # Multi-threaded execution
    max_workers = 8
    success_count = 0
    error_count = 0
    batch_records = []
    db_lock = threading.Lock()

    def save_batch(records: List[Dict[str, Any]]):
        if not records:
            return
        upsert_sql = text("""
            INSERT INTO filing_sections (
                filing_id, cik, fiscal_year, accession_number, section_type,
                text, char_count, word_count, sentence_count, source_location,
                extraction_status, created_at, updated_at
            ) VALUES (
                :filing_id, :cik, :fiscal_year, :accession_number, :section_type,
                :text, :char_count, :word_count, :sentence_count, :source_location,
                :extraction_status, NOW(), NOW()
            )
            ON CONFLICT (cik, fiscal_year, section_type)
            DO UPDATE SET
                filing_id = EXCLUDED.filing_id,
                text = EXCLUDED.text,
                char_count = EXCLUDED.char_count,
                word_count = EXCLUDED.word_count,
                sentence_count = EXCLUDED.sentence_count,
                source_location = EXCLUDED.source_location,
                extraction_status = EXCLUDED.extraction_status,
                updated_at = NOW();
        """)
        with db_lock:
            with engine.connect() as c:
                for r in records:
                    c.execute(upsert_sql, r)
                c.commit()

    logger.info(f"Launching ThreadPoolExecutor with {max_workers} workers...")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(fetch_and_extract, item, rate_limiter, extractor, headers): item
            for item in to_process
        }

        completed = 0
        total_items = len(to_process)
        for future in as_completed(future_map):
            completed += 1
            row, sections, err = future.result()
            if err or not sections:
                error_count += 1
                if completed % 25 == 0 or completed == total_items:
                    logger.info(f"Progress: [{completed}/{total_items}] | Done: {success_count} | Errors: {error_count} | Elapsed: {time.time()-start_time:.1f}s")
                continue

            success_count += 1
            fid = row["id"]
            cik = row["cik"]
            fy = row["fiscal_year"]
            acc = row["accession_number"]

            for sec_type, sec_data in sections.items():
                text_body = sec_data.get("text")
                words = text_body.split() if text_body else []
                char_cnt = len(text_body) if text_body else 0
                word_cnt = len(words)
                status = sec_data.get("status", "not_found")
                src_loc = sec_data.get("source_location")

                batch_records.append({
                    "filing_id": fid,
                    "cik": cik,
                    "fiscal_year": fy,
                    "accession_number": acc,
                    "section_type": sec_type,
                    "text": text_body,
                    "char_count": char_cnt,
                    "word_count": word_cnt,
                    "sentence_count": len(text_body.split(".")) if text_body else 0,
                    "source_location": src_loc,
                    "extraction_status": status,
                })

            if len(batch_records) >= 40:
                save_batch(batch_records)
                batch_records = []

            if completed % 25 == 0 or completed == total_items:
                logger.info(f"Progress: [{completed}/{total_items}] | Done: {success_count} | Errors: {error_count} | Elapsed: {time.time()-start_time:.1f}s")

        if batch_records:
            save_batch(batch_records)

    logger.info(f"Extraction pass finished in {time.time()-start_time:.1f}s. Saved: {success_count}, Errors: {error_count}")

    # Generate extraction success rate report
    with engine.connect() as conn:
        stats = pd.read_sql("""
            SELECT
                l.fiscal_year,
                COUNT(DISTINCT l.id) as total_cohort_firms,
                COUNT(DISTINCT CASE WHEN fs.section_type = 'mda' AND fs.word_count > 0 THEN l.id END) as with_mda,
                ROUND(100.0 * COUNT(DISTINCT CASE WHEN fs.section_type = 'mda' AND fs.word_count > 0 THEN l.id END) / COUNT(DISTINCT l.id), 1) as mda_pct,
                COUNT(DISTINCT CASE WHEN fs.section_type = 'risk_factors' AND fs.word_count > 0 THEN l.id END) as with_risk,
                ROUND(100.0 * COUNT(DISTINCT CASE WHEN fs.section_type = 'risk_factors' AND fs.word_count > 0 THEN l.id END) / COUNT(DISTINCT l.id), 1) as risk_pct,
                COUNT(DISTINCT CASE WHEN fs.section_type = 'related_party' AND fs.word_count > 0 THEN l.id END) as with_rp_note,
                ROUND(100.0 * COUNT(DISTINCT CASE WHEN fs.section_type = 'related_party' AND fs.word_count > 0 THEN l.id END) / COUNT(DISTINCT l.id), 1) as rp_pct,
                COUNT(DISTINCT CASE WHEN fs.section_type = 'item_13' AND fs.word_count > 0 THEN l.id END) as with_item13,
                ROUND(100.0 * COUNT(DISTINCT CASE WHEN fs.section_type = 'item_13' AND fs.word_count > 0 THEN l.id END) / COUNT(DISTINCT l.id), 1) as item13_pct
            FROM company_year_labels l
            LEFT JOIN filing_sections fs ON fs.cik = l.cik AND fs.fiscal_year = l.fiscal_year
            GROUP BY l.fiscal_year
            ORDER BY l.fiscal_year
        """, conn)

        print("\n" + "=" * 80)
        print("  SECTION EXTRACTION SUCCESS RATE BY FISCAL YEAR (ALL 1,106 COHORT ROWS)")
        print("=" * 80)
        print(stats.to_string(index=False))

        out_json = REPO_ROOT / "reports" / "section_extraction_report.json"
        stats.to_json(out_json, orient="records", indent=2)
        logger.info(f"Report saved to {out_json}")


if __name__ == "__main__":
    main()
