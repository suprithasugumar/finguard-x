"""Test AAER scraping and parsing across pages 0-4 to inspect respondent patterns."""
from collections import Counter
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import sys

from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import get_settings
from backend.app.ingest.sec_client import SECClient
from backend.app.ingest.aaer_parser import normalize_company_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("test_aaer")


def run():
    client = SECClient()
    cases = []
    base_url = "https://www.sec.gov/enforcement-litigation/accounting-auditing-enforcement-releases"

    for page in range(5):
        url = f"{base_url}?page={page}"
        resp = client.get(url, use_cache=True)
        soup = BeautifulSoup(resp.content, "html.parser")
        table = soup.find("table")
        if not table:
            continue
        rows = table.find_all("tr")[1:]
        for r in rows:
            tds = r.find_all("td")
            if len(tds) < 2:
                continue
            date_str = tds[0].get_text(strip=True)
            cell_text = tds[1].get_text(separator=" | ", strip=True)
            links = [(a.get_text(strip=True), a["href"]) for a in tds[1].find_all("a", href=True)]
            cases.append({"date": date_str, "text": cell_text, "links": links})

    logger.info(f"Loaded {len(cases)} cases across 5 pages.")
    for i, c in enumerate(cases[:15]):
        logger.info(f"Case {i}: Date={c['date']} | Text={c['text'][:120]}")


if __name__ == "__main__":
    run()
