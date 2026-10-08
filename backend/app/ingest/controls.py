"""Matched controls generator with strict temporal anti-leakage and asset distance matching."""

import logging
import math
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger("finguard.ingest.controls")


class ControlsMatcher:
    """Matches 1:5 controls by 2-digit SIC and nearest log total assets without replacement.

    Eligibility Rules (Approved Change 5):
    1. Must have original 10-K for (CIK, fiscal_year).
    2. Must have prior-year original 10-K for (CIK, fiscal_year - 1).
    3. Must have non-null revenue and non-null total assets.
    4. Enforced firms (any AAER ever) are strictly excluded from the control pool.
    5. Matching without replacement (control CIK used once per fiscal year).
    """

    def __init__(self, ratio: int = 5, seed: int = 42):
        self.ratio = ratio
        self.seed = seed

    def find_matched_controls(
        self,
        positives: List[Dict[str, Any]],
        eligible_candidates: List[Dict[str, Any]],
        enforced_ciks: Set[str],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Match controls without replacement for each positive company-year.

        positives items:
            {"id": int, "cik": str, "fiscal_year": int, "sic": str, "assets": float, "revenue": float}

        eligible_candidates items (pool of non-enforced firms meeting 1-3):
            {"cik": str, "fiscal_year": int, "sic": str, "assets": float, "revenue": float}

        Returns:
            (matched_controls_list, unmatched_positives_list)
        """
        # Index eligible candidates by (fiscal_year, sic_2digit)
        candidates_by_fy_sic: Dict[Tuple[int, str], List[Dict[str, Any]]] = defaultdict(list)
        for cand in eligible_candidates:
            cik = cand["cik"]
            # Enforced firms are never controls in any year
            if cik in enforced_ciks:
                continue

            fy = cand["fiscal_year"]
            sic_2d = str(cand.get("sic") or "99")[:2]
            candidates_by_fy_sic[(fy, sic_2d)].append(cand)

        matched_controls: List[Dict[str, Any]] = []
        unmatched_positives: List[Dict[str, Any]] = []
        # Track used controls per fiscal year to enforce matching without replacement
        used_ciks_by_fy: Dict[int, Set[str]] = defaultdict(set)

        for pos in positives:
            pos_id = pos.get("id")
            pos_cik = pos["cik"]
            pos_fy = pos["fiscal_year"]
            pos_sic_2d = str(pos.get("sic") or "99")[:2]
            pos_assets = max(pos.get("assets") or 1.0, 1.0)
            pos_log_assets = math.log(pos_assets)

            pool = candidates_by_fy_sic.get((pos_fy, pos_sic_2d), [])
            # Filter available candidates not yet used in this fiscal year
            available = [
                c for c in pool if c["cik"] != pos_cik and c["cik"] not in used_ciks_by_fy[pos_fy]
            ]

            if len(available) < self.ratio:
                # Fallback: search within 1-digit SIC if not enough in 2-digit
                pos_sic_1d = pos_sic_2d[:1]
                broader = []
                for (cand_fy, cand_sic), c_list in candidates_by_fy_sic.items():
                    if cand_fy == pos_fy and cand_sic.startswith(pos_sic_1d):
                        for c in c_list:
                            if c["cik"] != pos_cik and c["cik"] not in used_ciks_by_fy[pos_fy]:
                                broader.append(c)
                # Deduplicate
                seen_ciks = {c["cik"] for c in available}
                for c in broader:
                    if c["cik"] not in seen_ciks:
                        available.append(c)
                        seen_ciks.add(c["cik"])

            if not available:
                unmatched_positives.append(pos)
                continue

            # Asset distance matching: prioritize +-30% total assets on SIC2 and FY
            within_30 = []
            outside_30 = []
            for c in available:
                c_assets = max(c.get("assets") or 1.0, 1.0)
                rel_dist = abs(c_assets - pos_assets) / pos_assets
                log_dist = abs(math.log(c_assets) - pos_log_assets)
                item = (rel_dist, log_dist, c)
                if rel_dist <= 0.30:
                    within_30.append(item)
                else:
                    outside_30.append(item)

            # Sort both pools by relative distance
            within_30.sort(key=lambda x: x[0])
            outside_30.sort(key=lambda x: x[0])

            selected = within_30[: self.ratio]
            if len(selected) < self.ratio:
                # Fill remaining spots with closest available candidates
                needed = self.ratio - len(selected)
                selected.extend(outside_30[:needed])

            if not selected:
                unmatched_positives.append(pos)
                continue

            for rel_dist, log_dist, c in selected:
                used_ciks_by_fy[pos_fy].add(c["cik"])
                matched_controls.append(
                    {
                        "cik": c["cik"],
                        "fiscal_year": pos_fy,
                        "label": 0,
                        "label_confidence": "high",
                        "label_rationale": (
                            f"Matched 1:{self.ratio} control for positive CIK {pos_cik} FY {pos_fy} "
                            f"(SIC {pos_sic_2d}, asset relative distance {rel_dist:.1%}, log dist {log_dist:.3f})"
                        ),
                        "matched_positive_id": pos_id,
                        "match_distance": float(rel_dist),
                        "review_status": "auto",
                    }
                )

        return matched_controls, unmatched_positives
