"""Populate data/gold/label_review.csv with ambiguous/low-confidence candidate matches for manual review."""
import csv
import logging
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rapidfuzz import fuzz
from sqlalchemy import create_engine, text

from backend.app.core.config import Settings
from backend.app.ingest.aaer_parser import normalize_company_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.populate_review_queue")


def populate():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        companies = conn.execute(text("SELECT cik, name FROM companies")).fetchall()
        # Find cases without CIK where company_name is present
        unmatched = conn.execute(text("""
            SELECT id, aaer_number, company_name, source_url, release_date
            FROM aaer_cases
            WHERE exclusion_reason IS NULL AND cik IS NULL AND company_name IS NOT NULL
            ORDER BY id
        """)).fetchall()

    logger.info(f"Loaded {len(companies)} companies and {len(unmatched)} unmatched corporate cases.")

    comp_dict = {normalize_company_name(name): (cik, name) for cik, name in companies if name}

    review_rows = []
    for cid, aaer_num, cname, url, rdate in unmatched:
        if not cname or len(cname.strip()) < 4:
            continue

        clean = re.sub(r"\(.*?\)", "", cname)
        clean = re.sub(r"\s+and\s+.*", "", clean, flags=re.I)
        norm = normalize_company_name(clean)
        if not norm or len(norm) < 4:
            continue

        # Check fuzzy match against company dict
        best_score = 0.0
        best_match = None
        for cnorm, (cik, db_name) in comp_dict.items():
            if cnorm[:3] == norm[:3] or cnorm[-3:] == norm[-3:]:
                score = fuzz.token_sort_ratio(norm, cnorm)
                if score > best_score:
                    best_score = score
                    best_match = (cik, db_name)

        if best_match and 78.0 <= best_score < 91.0:
            review_rows.append({
                "cik": best_match[0],
                "company_name": cname,
                "fiscal_year": rdate.year - 1 if rdate else 2020,
                "aaer_number": aaer_num,
                "label": 1,
                "confidence": "medium" if best_score >= 85.0 else "low",
                "source": url,
                "rationale": f"Candidate match to {best_match[1]} (CIK {best_match[0]}) with fuzzy similarity {best_score:.1f}%",
                "review_status": "needs_review",
                "reviewer_notes": "Never auto-accepted: ambiguous similarity below 91% threshold. Pending human adjudication.",
            })

    csv_path = settings.GOLD_DIR / "label_review.csv"
    settings.GOLD_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "cik", "company_name", "fiscal_year", "aaer_number", "label",
        "confidence", "source", "rationale", "review_status", "reviewer_notes"
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(review_rows)

    logger.info(f"Exported {len(review_rows)} ambiguous candidate cases to {csv_path}")


if __name__ == "__main__":
    populate()
