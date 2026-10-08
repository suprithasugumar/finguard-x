"""Enrich AAER corporate cases with authentic misstatement fiscal years from SEC PDF text."""
import io
import json
import logging
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pypdf
from sqlalchemy import create_engine, text
from backend.app.core.config import Settings
from backend.app.ingest.aaer_parser import AAERParser
from backend.app.ingest.sec_client import SECClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.enrich_aaer_pdfs")


def enrich_cases():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    client = SECClient()
    parser = AAERParser()

    with engine.connect() as conn:
        cases = conn.execute(text("""
            SELECT id, aaer_number, company_name, cik, source_url, affected_fiscal_years::text
            FROM aaer_cases
            WHERE exclusion_reason IS NULL AND cik IS NOT NULL AND source_url LIKE '%.pdf'
            AND (json_array_length(affected_fiscal_years) <= 1 OR affected_fiscal_years IS NULL)
            ORDER BY id
        """)).fetchall()

    logger.info(f"Found {len(cases)} corporate AAER cases to extract.")
    
    updated_count = 0
    total_years_extracted = 0
    all_extracted_years = Counter()
    multi_year_cases = 0

    for idx, (cid, aaer_num, comp_name, cik, url, current_years_json) in enumerate(cases):
        try:
            resp = client.get(url, use_cache=True)
            if resp.status_code != 200:
                logger.warning(f"[{idx+1}/{len(cases)}] Failed to download {url}: HTTP {resp.status_code}")
                continue

            # Read PDF text
            reader = pypdf.PdfReader(io.BytesIO(resp.content))
            # Extract first 8 pages (findings are typically in pages 1-6)
            pages_to_read = min(len(reader.pages), 8)
            full_text = "\n".join([reader.pages[p].extract_text() or "" for p in range(pages_to_read)])

            # Parse fiscal years
            extracted = parser.extract_affected_fiscal_years(full_text)
            years = [yr for yr, conf, rat in extracted if 2000 <= yr <= 2026]

            if years:
                # Update case in DB
                with engine.connect() as conn:
                    conn.execute(
                        text("UPDATE aaer_cases SET affected_fiscal_years = :years WHERE id = :cid"),
                        {"years": json.dumps(years), "cid": cid}
                    )
                    conn.commit()
                updated_count += 1
                total_years_extracted += len(years)
                for y in years:
                    all_extracted_years[y] += 1
                if len(years) > 1:
                    multi_year_cases += 1
                if (idx + 1) % 15 == 0 or len(years) > 1:
                    logger.info(f"[{idx+1}/{len(cases)}] {aaer_num} ({comp_name[:25]}): Extracted FYs {years}")
            else:
                logger.info(f"[{idx+1}/{len(cases)}] {aaer_num} ({comp_name[:25]}): No explicit FYs found in findings")

        except Exception as e:
            logger.warning(f"[{idx+1}/{len(cases)}] Error processing {aaer_num} ({url}): {e}")

    logger.info("==========================================")
    logger.info(f"Enrichment Complete!")
    logger.info(f"Cases updated with authentic PDF years: {updated_count}/{len(cases)}")
    logger.info(f"Cases with multiple misstated years:   {multi_year_cases}")
    logger.info(f"Total authentic misstatement years:     {total_years_extracted}")
    logger.info("Fiscal Year Breakdown:")
    for yr in sorted(all_extracted_years.keys()):
        logger.info(f"  FY{yr}: {all_extracted_years[yr]}")
    logger.info("==========================================")


if __name__ == "__main__":
    enrich_cases()
