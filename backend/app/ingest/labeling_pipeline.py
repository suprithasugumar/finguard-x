"""Ground-truth company-year labeling and matched controls generation engine."""

import csv
import logging
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.entities import (
    AAERCase,
    Company,
    CompanyYearLabel,
    Filing,
    FinancialFact,
)
from backend.app.ingest.controls import ControlsMatcher

logger = logging.getLogger("finguard.ingest.labeling_pipeline")


class LabelingPipeline:
    """Builds company-year ground truth labels (Positives and 1:5 Matched Controls) per R1-R6."""

    def __init__(self, seed: int = 42):
        self.settings = get_settings()
        self.seed = seed
        self.matcher = ControlsMatcher(ratio=5, seed=seed)
        self.review_csv_path = self.settings.GOLD_DIR / "label_review.csv"

    def load_manual_overrides(self) -> Dict[Tuple[str, int], Dict[str, Any]]:
        """Load manual review decisions from data/gold/label_review.csv if present."""
        overrides: Dict[Tuple[str, int], Dict[str, Any]] = {}
        if not self.review_csv_path.exists():
            return overrides

        try:
            with open(self.review_csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cik = row.get("cik", "").strip().zfill(10)
                    fy_str = row.get("fiscal_year", "").strip()
                    status = row.get("review_status", "").strip()
                    if cik and fy_str and status in ("approved", "rejected", "override"):
                        fy = int(fy_str)
                        overrides[(cik, fy)] = {
                            "label": int(row.get("label", 1)),
                            "confidence": row.get("confidence", "high"),
                            "review_status": "manual_override",
                            "rationale": row.get("reviewer_notes") or row.get("rationale", ""),
                        }
        except Exception as e:
            logger.warning(f"Error loading manual overrides from {self.review_csv_path}: {e}")

        return overrides

    def export_review_queue(self, review_items: List[Dict[str, Any]]) -> None:
        """Export low and medium confidence cases to data/gold/label_review.csv."""
        if not review_items and self.review_csv_path.exists():
            return
        self.settings.GOLD_DIR.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "cik",
            "company_name",
            "fiscal_year",
            "aaer_number",
            "label",
            "confidence",
            "source",
            "rationale",
            "review_status",
            "reviewer_notes",
        ]

        # Preserve existing overrides
        existing_overrides = self.load_manual_overrides()

        rows_to_write = []
        for item in review_items:
            key = (item["cik"], item["fiscal_year"])
            if key in existing_overrides:
                override = existing_overrides[key]
                rows_to_write.append(
                    {
                        "cik": item["cik"],
                        "company_name": item["company_name"],
                        "fiscal_year": item["fiscal_year"],
                        "aaer_number": item.get("aaer_number", ""),
                        "label": override["label"],
                        "confidence": override["confidence"],
                        "source": item.get("source", "aaer_release"),
                        "rationale": item["rationale"],
                        "review_status": "manual_override",
                        "reviewer_notes": override["rationale"],
                    }
                )
            else:
                rows_to_write.append(
                    {
                        "cik": item["cik"],
                        "company_name": item["company_name"],
                        "fiscal_year": item["fiscal_year"],
                        "aaer_number": item.get("aaer_number", ""),
                        "label": item.get("label", 1),
                        "confidence": item["confidence"],
                        "source": item.get("source", "aaer_release"),
                        "rationale": item["rationale"],
                        "review_status": item.get("review_status", "needs_review"),
                        "reviewer_notes": item.get("reviewer_notes", ""),
                    }
                )

        with open(self.review_csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows_to_write)
        logger.info(f"Exported {len(rows_to_write)} review items to {self.review_csv_path}")

    def execute_labeling(self, session: Session, min_fiscal_year: int = 2010) -> Dict[str, Any]:
        """Execute ground-truth positive labeling and 1:5 control matching."""
        overrides = self.load_manual_overrides()

        # 1. Fetch all company metadata
        companies = {c.cik: c for c in session.query(Company).all()}

        # 2. Fetch original filings by (cik, fiscal_year)
        filings = session.query(Filing).filter(Filing.is_amendment.is_(False)).all()
        filings_by_cik_fy = {(f.cik, f.fiscal_year): f for f in filings}

        # 3. Fetch non-null Assets and Revenues by (cik, fiscal_year)
        revenue_tags = {
            "Revenues",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueGoodsNet",
            "OperatingRevenue",
        }
        facts = (
            session.query(FinancialFact)
            .filter(
                FinancialFact.is_original_filing.is_(True),
                FinancialFact.tag.in_(revenue_tags | {"Assets"}),
            )
            .all()
        )

        assets_by_cik_fy: Dict[Tuple[str, int], float] = {}
        revenue_by_cik_fy: Dict[Tuple[str, int], float] = {}
        for fact in facts:
            key = (fact.cik, fact.fiscal_year)
            if fact.tag == "Assets":
                assets_by_cik_fy[key] = fact.value
            elif fact.tag in revenue_tags:
                revenue_by_cik_fy[key] = fact.value

        # 4. Identify Enforced Firms (any AAER ever)
        all_cases = session.query(AAERCase).all()
        enforced_ciks: Set[str] = {c.cik for c in all_cases if c.cik}
        corporate_cases = [c for c in all_cases if c.exclusion_reason is None]

        positives_to_insert: List[Dict[str, Any]] = []
        review_queue: List[Dict[str, Any]] = []
        unresolved_reasons: Dict[str, int] = defaultdict(int)

        max_fiscal_year = 2023

        # 5. Process Positive Candidates
        for case in corporate_cases:
            if not case.cik:
                unresolved_reasons["Missing CIK resolution"] += 1
                continue

            company = companies.get(case.cik)
            comp_name = company.name if company else case.company_name
            affected_years = case.affected_fiscal_years or []

            for fy in affected_years:
                if fy < min_fiscal_year or fy > max_fiscal_year:
                    unresolved_reasons[f"Out of range fiscal year ({fy})"] += 1
                    continue

                key = (case.cik, fy)
                # Check manual override
                if key in overrides:
                    ov = overrides[key]
                    if ov["label"] == 1:
                        positives_to_insert.append(
                            {
                                "cik": case.cik,
                                "company_name": comp_name,
                                "fiscal_year": fy,
                                "label": 1,
                                "label_confidence": ov["confidence"],
                                "label_rationale": f"Manual override: {ov['rationale']}",
                                "aaer_case_id": case.id,
                                "review_status": "manual_override",
                                "assets": assets_by_cik_fy.get(key, 1000000.0),
                                "revenue": revenue_by_cik_fy.get(key, 500000.0),
                                "sic": company.sic if company else "9999",
                            }
                        )
                    continue

                # Eligibility check (Approved Change 5):
                # 1. Original 10-K present
                has_orig_10k = key in filings_by_cik_fy
                # 2. Prior-year 10-K present
                has_prior_10k = (case.cik, fy - 1) in filings_by_cik_fy
                # 3. Non-null revenue and assets
                has_assets = key in assets_by_cik_fy and assets_by_cik_fy[key] > 0
                has_rev = key in revenue_by_cik_fy

                if not (has_orig_10k and has_prior_10k and has_assets and has_rev):
                    reason = []
                    if not has_orig_10k:
                        reason.append("no original 10-K")
                    if not has_prior_10k:
                        reason.append("no prior-year 10-K")
                    if not has_assets or not has_rev:
                        reason.append("missing asset/revenue facts")
                    unresolved_reasons[f"Ineligible positive ({', '.join(reason)})"] += 1
                    continue

                # Valid positive
                confidence = "high"
                rationale = f"SEC AAER {case.aaer_number} enforcement misstatement for FY{fy}"
                item = {
                    "cik": case.cik,
                    "company_name": comp_name,
                    "fiscal_year": fy,
                    "label": 1,
                    "label_confidence": confidence,
                    "label_rationale": rationale,
                    "aaer_case_id": case.id,
                    "review_status": "auto",
                    "assets": assets_by_cik_fy[key],
                    "revenue": revenue_by_cik_fy[key],
                    "sic": company.sic if company else "9999",
                }
                positives_to_insert.append(item)

        # Deduplicate positives by (cik, fiscal_year) to prevent duplicate records
        deduped_positives: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for p in positives_to_insert:
            key = (p["cik"], p["fiscal_year"])
            if key not in deduped_positives:
                deduped_positives[key] = p
            else:
                existing = deduped_positives[key]
                existing["label_rationale"] += f"; also cited in {p['label_rationale']}"
        positives_to_insert = list(deduped_positives.values())

        # Clear existing company_year_labels table before reloading
        session.query(CompanyYearLabel).delete()
        session.flush()

        # 6. Insert Positives into company_year_labels
        inserted_positives: List[Dict[str, Any]] = []
        for p in positives_to_insert:
            cyl = CompanyYearLabel(
                cik=p["cik"],
                fiscal_year=p["fiscal_year"],
                label=1,
                label_confidence=p["label_confidence"],
                label_rationale=p["label_rationale"],
                aaer_case_id=p["aaer_case_id"],
                review_status=p["review_status"],
            )
            session.add(cyl)
            session.flush()
            p["id"] = cyl.id
            inserted_positives.append(p)

        # 7. Build Pool of Eligible Control Candidates
        # Firms meeting eligibility rules: original 10-K, prior 10-K, assets > 0, revenue > 0
        eligible_control_pool: List[Dict[str, Any]] = []
        for (cik, fy), filing in filings_by_cik_fy.items():
            if cik in enforced_ciks:
                continue
            if (cik, fy - 1) not in filings_by_cik_fy:
                continue
            key = (cik, fy)
            if key not in assets_by_cik_fy or assets_by_cik_fy[key] <= 0:
                continue
            if key not in revenue_by_cik_fy:
                continue

            comp = companies.get(cik)
            eligible_control_pool.append(
                {
                    "cik": cik,
                    "fiscal_year": fy,
                    "sic": comp.sic if comp else "9999",
                    "assets": assets_by_cik_fy[key],
                    "revenue": revenue_by_cik_fy[key],
                }
            )

        # 8. Match Controls (1:5 without replacement)
        matched_controls, unmatched_positives = self.matcher.find_matched_controls(
            inserted_positives, eligible_control_pool, enforced_ciks
        )

        for c in matched_controls:
            cyl = CompanyYearLabel(
                cik=c["cik"],
                fiscal_year=c["fiscal_year"],
                label=0,
                label_confidence=c["label_confidence"],
                label_rationale=c["label_rationale"],
                matched_positive_id=c["matched_positive_id"],
                match_distance=c["match_distance"],
                review_status=c["review_status"],
            )
            session.add(cyl)

        session.commit()

        # 9. Export review queue
        self.export_review_queue(review_queue)

        unique_pos_ciks = len(set(p["cik"] for p in inserted_positives))
        unique_ctrl_ciks = len(set(c["cik"] for c in matched_controls))
        stats = {
            "positives_count": len(inserted_positives),
            "positive_independent_ciks": unique_pos_ciks,
            "matched_controls_count": len(matched_controls),
            "control_independent_ciks": unique_ctrl_ciks,
            "total_cohort_records": len(inserted_positives) + len(matched_controls),
            "unmatched_positives_count": len(unmatched_positives),
            "unresolved_reasons": dict(unresolved_reasons),
        }
        return stats
