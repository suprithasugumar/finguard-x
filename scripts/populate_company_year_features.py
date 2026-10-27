"""FinGuard-X Sprint A: Populate Normalized Financial Features and Beneish M-Score for Labeled Universe."""
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
import sys
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.db.session import get_session_factory
from backend.app.db.models.entities import CompanyYearLabel
from backend.app.db.models.features import CompanyYearFeatures
from backend.app.features.financial_features import FinancialFeaturesExtractor

def compute_roc_auc(y_true, y_scores):
    order = np.argsort(y_scores)
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    n_pos = np.sum(y_true == 1)
    n_neg = np.sum(y_true == 0)
    if n_pos == 0 or n_neg == 0:
        return 0.5
    rank_sum_pos = np.sum(rank[y_true == 1])
    u = rank_sum_pos - (n_pos * (n_pos - 1)) / 2.0
    return float(u / (n_pos * n_neg))

def compute_pr_auc(y_true, y_scores):
    order = np.argsort(-y_scores)
    y_sorted = y_true[order]
    n_pos = np.sum(y_true == 1)
    if n_pos == 0:
        return 0.0
    tp = np.cumsum(y_sorted == 1)
    fp = np.cumsum(y_sorted == 0)
    recall = tp / n_pos
    precision = tp / (tp + fp)
    return float(np.sum((recall[1:] - recall[:-1]) * precision[1:]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.populate_features")


def run_financial_features_population():
    session_factory = get_session_factory()
    session = session_factory()
    extractor = FinancialFeaturesExtractor(session)

    # 1. Fetch all 504 labeled company-years (84 positives + 420 controls)
    labels = session.query(CompanyYearLabel).order_by(CompanyYearLabel.id).all()
    logger.info(f"Targeting {len(labels)} labeled company-years for normalized financial feature extraction...")

    # Clear existing features
    session.query(CompanyYearFeatures).delete()
    session.commit()

    # Deduplicate unique (cik, fiscal_year) company-years for storage
    unique_targets = {}
    for lbl in labels:
        key = (lbl.cik, lbl.fiscal_year)
        if key not in unique_targets:
            unique_targets[key] = []
        unique_targets[key].append(lbl)

    logger.info(f"Identified {len(unique_targets)} unique (CIK, Fiscal Year) tuples across {len(labels)} labels.")

    features_by_key = {}
    inserted_count = 0

    for idx, (key, _) in enumerate(unique_targets.items(), 1):
        cik, fy = key
        cyf = extractor.extract_company_year_features(cik, fy)
        if cyf:
            session.add(cyf)
            features_by_key[key] = cyf
            inserted_count += 1
        if idx % 50 == 0:
            session.commit()
            logger.info(f"Processed {idx}/{len(unique_targets)} unique company-years ({inserted_count} features inserted)...")

    session.commit()
    logger.info(f"Successfully populated {inserted_count} company_year_features rows in database.")

    # Reconstruct paired list (label, cyf) for all 504 labels
    features_list = []
    for lbl in labels:
        key = (lbl.cik, lbl.fiscal_year)
        if key in features_by_key:
            features_list.append((lbl, features_by_key[key]))

    # 2. Compute Distribution Summary (min / p1 / median / p99 / max)
    feature_names = [
        "asset_turnover", "roa", "operating_margin", "net_margin",
        "current_ratio", "debt_to_equity", "cash_to_assets",
        "working_capital_to_assets", "cfo_to_assets", "sales_to_receivables",
        "receivables_to_assets", "inventory_to_assets", "capex_to_assets",
        "debt_to_assets", "cash_flow_margin", "accruals_bs_to_assets",
        "accruals_cf_to_assets", "asset_growth",
        "beneish_dsri", "beneish_gmi", "beneish_aqi", "beneish_sgi",
        "beneish_depi", "beneish_sgai", "beneish_lvgi", "beneish_tata",
        "beneish_m_score", "beneish_strict", "beneish_neutral", "beneish_n_components"
    ]

    distribution_summary = {}
    implausible_values = []

    for feat in feature_names:
        vals = [getattr(f[1], feat) for f in features_list if getattr(f[1], feat) is not None]
        if vals:
            arr = np.array(vals)
            p1 = float(np.percentile(arr, 1))
            p99 = float(np.percentile(arr, 99))
            min_v = float(np.min(arr))
            max_v = float(np.max(arr))
            median_v = float(np.median(arr))
            distribution_summary[feat] = {
                "count": len(vals),
                "min": min_v,
                "p1": p1,
                "median": median_v,
                "p99": p99,
                "max": max_v,
            }
            # List implausible outliers (> 100 or < -100 or extreme ratios)
            if min_v < -100 or max_v > 100:
                implausible_values.append({
                    "feature": feat,
                    "min": min_v,
                    "max": max_v,
                    "note": "Extreme unclipped accounting ratio (retained per R1/unclipped specification)"
                })
        else:
            distribution_summary[feat] = {"count": 0, "min": None, "p1": None, "median": None, "p99": None, "max": None}

    # 3. Compute Null Reason Counts
    null_reason_counts = Counter()
    for _, f in features_list:
        for feat, reason in (f.null_reasons or {}).items():
            null_reason_counts[f"{feat}::{reason}"] += 1

    # 4. Compute Coverage Table per Feature x Fiscal Year
    by_fy_total = Counter(f[0].fiscal_year for f in features_list)
    coverage_table = []
    fiscal_years = sorted(by_fy_total.keys())

    for feat in feature_names:
        row = {"feature": feat}
        for fy in fiscal_years:
            tot = by_fy_total[fy]
            present = sum(1 for f in features_list if f[0].fiscal_year == fy and getattr(f[1], feat) is not None)
            pct = (present / tot * 100.0) if tot > 0 else 0.0
            row[f"FY{fy}"] = f"{pct:.1f}%"
        coverage_table.append(row)

    # 5. Evaluate Beneish Baseline on Positives vs Controls (PR-AUC, ROC-AUC)
    # Labeled set with non-null Beneish M-Score
    m_eval = []
    for lbl, f in features_list:
        if f.beneish_m_score is not None:
            m_eval.append((lbl.label, f.beneish_m_score))

    beneish_metrics = {}
    if m_eval:
        y_true = np.array([m[0] for m in m_eval])
        y_scores = np.array([m[1] for m in m_eval])
        roc_auc = compute_roc_auc(y_true, y_scores)
        pr_auc = compute_pr_auc(y_true, y_scores)
        pos_count = int(np.sum(y_true))
        total_eval = len(m_eval)

        # Thresholds: -1.78 and -2.22
        pred_178 = (y_scores > -1.78).astype(int)
        pred_222 = (y_scores > -2.22).astype(int)

        def get_clf_stats(preds):
            tp = int(np.sum((preds == 1) & (y_true == 1)))
            fp = int(np.sum((preds == 1) & (y_true == 0)))
            fn = int(np.sum((preds == 0) & (y_true == 1)))
            tn = int(np.sum((preds == 0) & (y_true == 0)))
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
            return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": prec, "recall": rec, "f1": f1}

        beneish_metrics = {
            "total_evaluated": total_eval,
            "positives_evaluated": pos_count,
            "controls_evaluated": total_eval - pos_count,
            "roc_auc": roc_auc,
            "pr_auc": pr_auc,
            "threshold_178": get_clf_stats(pred_178),
            "threshold_222": get_clf_stats(pred_222),
        }
        logger.info(f"Beneish Evaluation: PR-AUC={pr_auc:.4f}, ROC-AUC={roc_auc:.4f} (Positives={pos_count}, Total={total_eval})")

    # 6. Save Summary Artifacts
    summary_path = ROOT_DIR / "data" / "processed" / "financial_features_summary.json"
    result = {
        "inserted_count": inserted_count,
        "distribution_summary": distribution_summary,
        "implausible_values": implausible_values,
        "null_reason_counts": dict(null_reason_counts.most_common(50)),
        "coverage_table": coverage_table,
        "beneish_metrics": beneish_metrics,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    logger.info(f"Summary written to {summary_path}")
    session.close()
    return result


if __name__ == "__main__":
    run_financial_features_population()
