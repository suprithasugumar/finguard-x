"""XBRL financial facts extraction, R3 anti-leakage selection, and restatement tracking."""

import logging
import math
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml
from psycopg2.extras import execute_values
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.ingest.fiscal_year import derive_fiscal_year

logger = logging.getLogger("finguard.ingest.facts_parser")


def load_curated_tags(yaml_path: Optional[Path] = None) -> Set[str]:
    """Load curated us-gaap tags from tags.yaml."""
    if yaml_path is None:
        settings = get_settings()
        yaml_path = settings.BASE_DIR / "backend" / "app" / "ingest" / "tags.yaml"

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    curated = set()
    for cat_data in data.get("categories", {}).values():
        for tag in cat_data.get("tags", []):
            curated.add(tag)
    return curated


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse date string (YYYY-MM-DD or textual like 'Sept. 30, 2023') to date object."""
    if not date_str or not isinstance(date_str, str):
        return None
    s = date_str.strip()
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    try:
        from dateutil import parser as dt_parser

        clean_s = s.replace("Sept.", "Sep.").replace("July", "Jul").replace("June", "Jun")
        return dt_parser.parse(clean_s).date()
    except Exception:
        return None


class FactsParser:
    """Parses raw SEC company facts JSON, enforces duration validity and R3 anti-leakage."""

    def __init__(self, tags_yaml_path: Optional[Path] = None):
        self.curated_tags = load_curated_tags(tags_yaml_path)

    def extract_raw_facts(
        self,
        company_facts_json: Dict[str, Any],
        fiscal_year_end_mmdd: Optional[str] = None,
        min_fiscal_year: int = 2008,
    ) -> List[Dict[str, Any]]:
        """Parse raw facts from JSON, filtering for curated tags, 10-K forms, and full-year durations."""
        cik_raw = str(company_facts_json.get("cik", ""))
        cik = cik_raw.zfill(10)
        facts_node = company_facts_json.get("facts", {}).get("us-gaap", {})

        raw_candidates: List[Dict[str, Any]] = []

        for tag in self.curated_tags:
            tag_info = facts_node.get(tag)
            if not tag_info:
                continue

            units = tag_info.get("units", {})
            # Look inside USD units (or shares/pure if needed)
            usd_facts = units.get("USD", [])
            for item in usd_facts:
                form = item.get("form", "")
                if form not in ("10-K", "10-K/A", "10-KT", "10-KT/A"):
                    continue

                end_date = parse_date(item.get("end"))
                if not end_date:
                    continue

                start_date = parse_date(item.get("start"))

                # Duration validation (R3 / Section D):
                # Full-year income statement / cash flow facts must cover ~365 days (330-390).
                # Quarterly (~90 days) and YTD facts are strictly rejected.
                if start_date is not None:
                    duration_days = (end_date - start_date).days
                    if not (330 <= duration_days <= 390):
                        continue

                val = item.get("val")
                if (
                    val is None
                    or not isinstance(val, (int, float))
                    or math.isnan(val)
                    or math.isinf(val)
                ):
                    continue

                accession = str(item.get("accn", "")).strip()
                filed_date = parse_date(item.get("filed")) or end_date
                fiscal_year = derive_fiscal_year(end_date, fiscal_year_end_mmdd)

                if fiscal_year < min_fiscal_year:
                    continue

                raw_candidates.append(
                    {
                        "cik": cik,
                        "tag": tag,
                        "unit": "USD",
                        "value": float(val),
                        "period_start": start_date,
                        "period_end": end_date,
                        "fiscal_year": fiscal_year,
                        "fiscal_period": item.get("fp") or "FY",
                        "form_type": form,
                        "accession_number": accession,
                        "filed_date": filed_date,
                    }
                )

        # Apply R3 Anti-Leakage & Restatement Tracking
        processed_facts = self._resolve_original_and_restatements(raw_candidates)
        return processed_facts

    def _resolve_original_and_restatements(
        self, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Identify original reported value (earliest filing) and flag subsequent restatements.

        Rule (approved change 1):
        - Original value = value from the earliest filing reporting that (CIK, tag, period_end).
        - is_restated = True only if a later filing reports a different value.
        - Both original and subsequent values are preserved.
        """
        # Group by (cik, tag, period_end)
        groups = defaultdict(list)
        for cand in candidates:
            key = (cand["cik"], cand["tag"], cand["period_end"])
            groups[key].append(cand)

        output: List[Dict[str, Any]] = []

        for key, facts_list in groups.items():
            # Sort by filed_date ascending, then accession ascending
            facts_list.sort(key=lambda x: (x["filed_date"], x["accession_number"]))

            earliest = facts_list[0]
            earliest_val = earliest["value"]

            # First filing is always original, not restated
            earliest["is_original_filing"] = True
            earliest["is_restated"] = False
            output.append(earliest)

            # Subsequent filings reporting on this period_end
            for subsequent in facts_list[1:]:
                subsequent["is_original_filing"] = False
                # Differs if value changed by more than floating point epsilon (0.01)
                differs = abs(subsequent["value"] - earliest_val) > 0.01
                subsequent["is_restated"] = differs
                output.append(subsequent)

        return output

    def bulk_insert_facts(
        self, facts: List[Dict[str, Any]], session: Session, batch_size: int = 5000
    ) -> int:
        """Batch insert financial facts using execute_values for high performance."""
        if not facts:
            return 0

        insert_sql = """
            INSERT INTO financial_facts (
                cik, tag, unit, value, period_start, period_end,
                fiscal_year, fiscal_period, form_type, accession_number,
                filed_date, is_original_filing, is_restated, created_at, updated_at
            ) VALUES %s
        """

        connection = session.connection()
        raw_conn = connection.connection.dbapi_connection  # psycopg2 connection

        total_inserted = 0
        now = datetime.utcnow()

        for i in range(0, len(facts), batch_size):
            batch = facts[i : i + batch_size]
            tuples = [
                (
                    f["cik"],
                    f["tag"],
                    f["unit"],
                    f["value"],
                    f["period_start"],
                    f["period_end"],
                    f["fiscal_year"],
                    f["fiscal_period"],
                    f["form_type"],
                    f["accession_number"],
                    f["filed_date"],
                    f["is_original_filing"],
                    f["is_restated"],
                    now,
                    now,
                )
                for f in batch
            ]

            with raw_conn.cursor() as cursor:
                execute_values(cursor, insert_sql, tuples, page_size=batch_size)
            total_inserted += len(batch)
            logger.info(f"Inserted facts batch {total_inserted}/{len(facts)}")

        session.commit()
        return total_inserted
