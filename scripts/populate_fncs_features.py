"""Populate Financial-Narrative Contradiction Scores (FNCS) for all 1,106 cohort company-years.

Uses the 7 real spec categories:
- growth
- profitability
- liquidity
- demand
- cash_flow
- risk
- outlook

Missing MD&A or below-similarity threshold returns NULL (None) with an explicit reason code in category_statuses.
Uses pure NumPy for evaluation metrics (ROC AUC, PR AUC) to prevent DLL load issues.
"""

import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.config import Settings
from backend.app.db.models.fncs import CompanyYearFNCSFeatures
from backend.app.fncs.fncs_engine import FNCSEngine
from backend.app.nlp.narrative_drift import EmbeddingCache, clean_sentences

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("finguard.stage2.fncs")

CATEGORY_KEYWORDS = {
    "growth": ["growth", "revenue", "sales", "expand", "market share", "volume", "increase in sales"],
    "profitability": ["margin", "profit", "operating income", "gross profit", "earnings", "cost of sales"],
    "liquidity": ["liquidity", "working capital", "credit facility", "cash balance", "short term", "debt"],
    "demand": ["demand", "orders", "backlog", "customer demand", "shipments", "pricing pressure"],
    "cash_flow": ["cash flow", "operating cash", "capital resources", "free cash", "cfo", "cash generated"],
    "risk": ["risk", "uncertainty", "contingency", "credit risk", "volatility", "adverse", "default"],
    "outlook": ["outlook", "guidance", "future", "expect", "anticipate", "projected", "capex"],
}


def filter_candidate_sentences(text: str, max_per_category: int = 6) -> List[str]:
    """Extract most relevant candidate sentences across categories for targeted embedding."""
    if not text:
        return []
    all_sentences = clean_sentences(text, max_sentences=250)
    selected_set = set()
    selected_list = []

    for cat, kws in CATEGORY_KEYWORDS.items():
        cat_matches = []
        for s in all_sentences:
            s_lower = s.lower()
            if any(kw in s_lower for kw in kws):
                cat_matches.append(s)
        for s in cat_matches[:max_per_category]:
            if s not in selected_set:
                selected_set.add(s)
                selected_list.append(s)

    for s in all_sentences[:10]:
        if s not in selected_set:
            selected_set.add(s)
            selected_list.append(s)

    return selected_list[:50]


def compute_industry_year_z_scores(cohort_data: List[dict]) -> Dict[tuple, Dict[str, float]]:
    """Compute industry-year winsorized z-scores and tanh values for numeric signals per category."""
    groups = defaultdict(list)
    for row in cohort_data:
        sic_prefix = str(row.get("sic") or "99")[:2]
        fy = row.get("fiscal_year")
        groups[(sic_prefix, fy)].append(row)

    cat_indicators = {
        "growth": [("beneish_sgi", 1.0), ("sales_to_receivables", 1.0)],
        "profitability": [("operating_margin", 1.0), ("beneish_gmi", -1.0)],
        "liquidity": [("current_ratio", 1.0)],
        "demand": [("asset_turnover", 1.0), ("sales_to_receivables", 1.0)],
        "cash_flow": [("cfo_to_assets", 1.0), ("beneish_tata", -1.0)],
        "risk": [("debt_to_equity", -1.0), ("graph_anomaly_score", -1.0)],
        "outlook": [("capex_to_assets", 1.0)],
    }

    all_values = defaultdict(list)
    for row in cohort_data:
        for cat, ind_list in cat_indicators.items():
            for ind_name, _ in ind_list:
                val = row.get(ind_name)
                if val is not None and not np.isnan(val):
                    all_values[ind_name].append(val)

    p1_p99 = {}
    for ind_name, vals in all_values.items():
        if vals:
            p1_p99[ind_name] = (np.percentile(vals, 1), np.percentile(vals, 99))
        else:
            p1_p99[ind_name] = (0.0, 1.0)

    result_z_scores = {}
    for row in cohort_data:
        cik = row["cik"]
        fy = row["fiscal_year"]
        sic_prefix = str(row.get("sic") or "99")[:2]
        group_rows = groups[(sic_prefix, fy)]
        if len(group_rows) < 3:
            group_rows = [r for r in cohort_data if r.get("fiscal_year") == fy]

        cat_z = {}
        for cat, ind_list in cat_indicators.items():
            z_parts = []
            for ind_name, direction in ind_list:
                val = row.get(ind_name)
                if val is None or np.isnan(val):
                    continue
                lo, hi = p1_p99.get(ind_name, (0.0, 1.0))
                val_clamped = max(lo, min(hi, val))
                grp_vals = [
                    max(lo, min(hi, r.get(ind_name)))
                    for r in group_rows
                    if r.get(ind_name) is not None and not np.isnan(r.get(ind_name))
                ]
                if len(grp_vals) >= 2:
                    mean = float(np.mean(grp_vals))
                    std = float(np.std(grp_vals)) + 1e-5
                    z = (val_clamped - mean) / std
                else:
                    z = 0.0
                z_parts.append(z * direction)

            cat_z[cat] = float(np.mean(z_parts)) if z_parts else 0.0

        result_z_scores[(cik, fy)] = cat_z

    return result_z_scores


def compute_roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Compute ROC-AUC without external library dependencies."""
    if len(np.unique(y_true)) < 2:
        return 0.5
    desc_score_indices = np.argsort(y_score)[::-1]
    y_score_sorted = y_score[desc_score_indices]
    y_true_sorted = y_true[desc_score_indices]
    distinct_value_indices = np.where(np.diff(y_score_sorted))[0]
    threshold_idxs = np.r_[distinct_value_indices, y_true_sorted.size - 1]
    tps = np.cumsum(y_true_sorted)[threshold_idxs]
    fps = 1 + threshold_idxs - tps
    tps = np.r_[0, tps]
    fps = np.r_[0, fps]
    if fps[-1] == 0 or tps[-1] == 0:
        return 0.5
    fpr = fps / fps[-1]
    tpr = tps / tps[-1]
    return float(np.trapz(tpr, fpr))


def compute_pr_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Compute PR-AUC without external library dependencies."""
    if len(np.unique(y_true)) < 2:
        return float(np.mean(y_true))
    desc_score_indices = np.argsort(y_score)[::-1]
    y_score_sorted = y_score[desc_score_indices]
    y_true_sorted = y_true[desc_score_indices]
    distinct_value_indices = np.where(np.diff(y_score_sorted))[0]
    threshold_idxs = np.r_[distinct_value_indices, y_true_sorted.size - 1]
    tps = np.cumsum(y_true_sorted)[threshold_idxs]
    fps = 1 + threshold_idxs - tps
    precision = tps / (tps + fps)
    recall = tps / tps[-1] if tps[-1] > 0 else np.zeros_like(tps)
    precision = np.r_[1.0, precision]
    recall = np.r_[0.0, recall]
    return float(np.sum((recall[1:] - recall[:-1]) * precision[1:]))


def populate_fncs():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    embedding_cache = EmbeddingCache()
    fncs_engine = FNCSEngine(embedding_cache=embedding_cache)

    logger.info("Initializing Stage 2: FNCS Population for 7 real categories...")

    with Session(engine) as session:
        cohort_rows = session.execute(
            text("""
                SELECT DISTINCT ON (cyl.cik, cyl.fiscal_year)
                    cyl.cik,
                    cyl.fiscal_year,
                    c.name as company_name,
                    c.sic,
                    cyl.label,
                    f.id as filing_id,
                    f.accession_number,
                    cyf.beneish_dsri,
                    cyf.beneish_sgi,
                    cyf.beneish_gmi,
                    cyf.sales_to_receivables,
                    cyf.inventory_to_assets,
                    cyf.asset_turnover,
                    cyf.beneish_tata,
                    cyf.accruals_bs_to_assets,
                    cyf.beneish_aqi,
                    cyf.beneish_depi,
                    cyf.capex_to_assets,
                    cyf.beneish_sgai,
                    cyf.operating_margin,
                    cyf.cfo_to_assets,
                    cyf.current_ratio,
                    cyf.debt_to_equity,
                    COALESCE(cyg.graph_anomaly_score, 0.0) as graph_anomaly_score,
                    COALESCE(cyg.num_entities, 0) as num_entities
                FROM company_year_labels cyl
                JOIN companies c ON c.cik = cyl.cik
                LEFT JOIN filings f ON f.cik = cyl.cik AND f.fiscal_year = cyl.fiscal_year AND f.form_type = '10-K'
                LEFT JOIN company_year_features cyf ON cyf.cik = cyl.cik AND cyf.fiscal_year = cyl.fiscal_year
                LEFT JOIN company_year_graph_features cyg ON cyg.cik = cyl.cik AND cyg.fiscal_year = cyl.fiscal_year
                ORDER BY cyl.cik, cyl.fiscal_year ASC
            """)
        ).fetchall()

        total_cohort = len(cohort_rows)
        logger.info(f"Loaded {total_cohort} cohort company-years with numeric & graph attributes.")

        cohort_dicts = []
        for r in cohort_rows:
            cohort_dicts.append({
                "cik": r.cik,
                "fiscal_year": r.fiscal_year,
                "company_name": r.company_name,
                "sic": r.sic,
                "label": r.label,
                "filing_id": r.filing_id,
                "accession_number": r.accession_number or "",
                "beneish_dsri": r.beneish_dsri,
                "beneish_sgi": r.beneish_sgi,
                "beneish_gmi": r.beneish_gmi,
                "sales_to_receivables": r.sales_to_receivables,
                "inventory_to_assets": r.inventory_to_assets,
                "asset_turnover": r.asset_turnover,
                "beneish_tata": r.beneish_tata,
                "accruals_bs_to_assets": r.accruals_bs_to_assets,
                "beneish_aqi": r.beneish_aqi,
                "beneish_depi": r.beneish_depi,
                "capex_to_assets": r.capex_to_assets,
                "beneish_sgai": r.beneish_sgai,
                "operating_margin": r.operating_margin,
                "cfo_to_assets": r.cfo_to_assets,
                "current_ratio": r.current_ratio,
                "debt_to_equity": r.debt_to_equity,
                "graph_anomaly_score": r.graph_anomaly_score,
                "num_entities": r.num_entities,
            })

        z_score_map = compute_industry_year_z_scores(cohort_dicts)
        logger.info("Computed industry-year winsorized z-scores across 7 real categories.")

        # Load MD&A text from filing_sections
        mda_rows = session.execute(
            text("""
                SELECT cik, fiscal_year, text
                FROM filing_sections
                WHERE section_type = 'mda' AND text IS NOT NULL AND length(text) > 100
            """)
        ).fetchall()
        mda_map = {(r[0], r[1]): r[2] for r in mda_rows}
        logger.info(f"Loaded {len(mda_map)} MD&A section texts from filing_sections.")

        # Clean existing rows in company_year_fncs_features
        session.execute(text("TRUNCATE TABLE company_year_fncs_features CASCADE"))
        session.commit()

        batch_to_insert = []
        pos_scores = []
        ctrl_scores = []
        real_explanations = []
        seen_keys = set()

        for idx, row in enumerate(cohort_dicts, 1):
            cik = row["cik"]
            fy = row["fiscal_year"]
            if (cik, fy) in seen_keys:
                continue
            seen_keys.add((cik, fy))
            mda_full = mda_map.get((cik, fy))
            candidates = filter_candidate_sentences(mda_full) if mda_full else []
            candidate_text = " ".join(candidates) if candidates else None

            cat_z = z_score_map.get((cik, fy), {})

            scores = fncs_engine.score_company_year(
                numeric_signals=row,
                mda_text=candidate_text,
                category_z_scores=cat_z,
            )

            is_pos = row["label"] == 1
            if scores["fncs_score"] is not None:
                if is_pos:
                    pos_scores.append(scores["fncs_score"])
                else:
                    ctrl_scores.append(scores["fncs_score"])

            if scores.get("contradiction_score") and scores["contradiction_score"] > 0.15 and len(real_explanations) < 5:
                real_explanations.append({
                    "cik": cik,
                    "company": row["company_name"],
                    "fiscal_year": fy,
                    "label": row["label"],
                    "fncs_score": scores["fncs_score"],
                    "contradiction_score": scores["contradiction_score"],
                    "explanations": scores.get("explanation_sentences", []),
                })

            rec = CompanyYearFNCSFeatures(
                filing_id=row["filing_id"],
                cik=cik,
                fiscal_year=fy,
                accession_number=row["accession_number"],
                cat_growth=scores.get("cat_growth"),
                cat_profitability=scores.get("cat_profitability"),
                cat_liquidity=scores.get("cat_liquidity"),
                cat_demand=scores.get("cat_demand"),
                cat_cash_flow=scores.get("cat_cash_flow"),
                cat_risk=scores.get("cat_risk"),
                cat_outlook=scores.get("cat_outlook"),
                category_statuses=scores.get("category_statuses", {}),
                contradiction_score=scores.get("contradiction_score"),
                fncs_score=scores.get("fncs_score"),
                fncs_evidence=scores.get("fncs_evidence", {}),
                explanation_sentences=scores.get("explanation_sentences", []),
            )
            batch_to_insert.append(rec)

            if len(batch_to_insert) >= 50:
                session.add_all(batch_to_insert)
                session.commit()
                batch_to_insert = []
                logger.info(f"Processed {idx}/{total_cohort} FNCS records...")

        if batch_to_insert:
            session.add_all(batch_to_insert)
            session.commit()

        mean_pos_fncs = float(np.mean(pos_scores)) if pos_scores else None
        mean_ctrl_fncs = float(np.mean(ctrl_scores)) if ctrl_scores else None

        logger.info("Stage 2 FNCS Population Complete!")
        logger.info(f"Total Cohort: {total_cohort}")
        logger.info(f"Mean FNCS Score: Positives = {mean_pos_fncs} vs Controls = {mean_ctrl_fncs}")

        summary = {
            "total_cohort": total_cohort,
            "mean_pos_fncs": mean_pos_fncs,
            "mean_ctrl_fncs": mean_ctrl_fncs,
            "examples": real_explanations[:3],
        }
        out_summary = Path("data/processed/stage2_fncs_summary.json")
        out_summary.parent.mkdir(parents=True, exist_ok=True)
        with open(out_summary, "w") as f:
            json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    populate_fncs()
