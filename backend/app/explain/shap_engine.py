"""Multi-Modal TreeSHAP explanation engine, modality grouping, and plain-language risk attribution (Stage 4)."""

import logging
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.special import logit
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import StratifiedGroupKFold

from backend.app.models.train_ablation import (
    FNCS_FEATURES,
    GRAPH_FEATURES,
    NUMERIC_FEATURES,
    TEXT_FEATURES,
    InFoldPreprocessor,
    PlattCalibrator,
)

logger = logging.getLogger("finguard.explain.shap_engine")

HUMAN_FEATURE_NAMES = {
    # Numeric
    "beneish_dsri": "Days Sales in Receivables Index (DSRI)",
    "beneish_gmi": "Gross Margin Deterioration (GMI)",
    "beneish_aqi": "Asset Quality Index / Deferred Charges (AQI)",
    "beneish_sgi": "Sales Growth Index (SGI)",
    "beneish_depi": "Depreciation Slowdown (DEPI)",
    "beneish_sgai": "SGA Expense Overhead Bloat (SGAI)",
    "beneish_lvgi": "Leverage Growth Index (LVGI)",
    "beneish_tata": "Total Accruals to Total Assets (TATA)",
    "accruals_bs_to_assets": "Balance Sheet Working Capital Accruals",
    "accruals_cf_to_assets": "Cash Flow Statement Operating Accruals",
    "cfo_to_assets": "Operating Cash Flow to Assets",
    "asset_turnover": "Asset Turnover Efficiency",
    "roa": "Return on Assets (ROA)",
    "operating_margin": "Operating Profit Margin",
    "net_margin": "Net Income Margin",
    "current_ratio": "Current Liquidity Ratio",
    "debt_to_equity": "Debt-to-Equity Financial Leverage",
    "cash_to_assets": "Cash and Cash Equivalents to Assets",
    "working_capital_to_assets": "Working Capital to Assets",
    "sales_to_receivables": "Sales to Receivables Turnover",
    "receivables_to_assets": "Receivables Concentration in Assets",
    "inventory_to_assets": "Inventory Bloat to Assets",
    "capex_to_assets": "Capital Expenditures to Assets",
    "debt_to_assets": "Total Debt to Assets",
    "cash_flow_margin": "Cash Flow to Sales Margin",
    "asset_growth": "Total Asset Expansion Rate",
    # Text
    "narrative_drift_score": "MD&A Semantic Narrative Drift",
    "doc_embedding_cosine_drift": "Cosine Embedding Drift from Prior Year",
    "vocab_jaccard_distance": "Vocabulary Jaccard Turnover",
    "uncertainty_rate": "Loughran-McDonald Uncertainty Language Density",
    "negative_sentiment_rate": "Loughran-McDonald Negative Tone Density",
    "financial_uncertainty_rate": "Financial Liquidity Uncertainty Language",
    "avg_sentence_length": "Disclosure Syntactic Length",
    "readability_fog_index": "Gunning Fog Readability Obfuscation Index",
    # Graph
    "graph_available": "Related-Party Disclosure Network Presence",
    "graph_size": "Related-Party Network Size",
    "num_nodes": "Related-Party Entity Node Count",
    "num_edges": "Affiliation Transaction Edge Count",
    "density": "Related-Party Network Interconnection Density",
    "avg_degree": "Average Entity Connectivity Degree",
    "num_officers": "Officer and Director Related Connections",
    "num_entities": "Affiliated Corporate Organizations",
    "num_undisclosed_or_shell": "Undisclosed LLC / Shell Entity Count",
    "max_clique_size": "Dense Affiliation Subgroup (Clique) Size",
    "clustering_coefficient": "Network Clustering Coefficient",
    "betweenness_centrality_max": "Intermediary Entity Betweenness Centrality",
    "yoy_node_churn": "Year-over-Year Related Entity Churn Rate",
    "yoy_edge_churn": "Year-over-Year Affiliation Edge Churn Rate",
    "graph_anomaly_score": "Related-Party Network Opacity Anomaly Score",
    # FNCS
    "cat1_revenue_recognition": "Revenue Recognition Narrative Discordance",
    "cat2_inventory_valuation": "Inventory Valuation Narrative Discordance",
    "cat3_reserve_manipulation": "Reserve & Accrual Quality Narrative Discordance",
    "cat4_capitalized_expenses": "Capitalized Expense Narrative Discordance",
    "cat5_related_party": "Related-Party Opacity Narrative Discordance",
    "cat6_governance_executive": "Governance & Compensation Narrative Discordance",
    "cat7_going_concern": "Going Concern & Liquidity Discordance",
    "contradiction_score": "Composite Financial Narrative Contradiction Score",
    "fncs_score": "Financial-Narrative Consistency Index (FNCS)",
}


class MultiModalExplanationEngine:
    """Produces strictly OUT-OF-FOLD multi-modal TreeSHAP attributions, calibrated scores, and plain-language factors (Task T6)."""

    def __init__(self):
        self.all_features = NUMERIC_FEATURES + TEXT_FEATURES + GRAPH_FEATURES + FNCS_FEATURES
        self.preprocessor = InFoldPreprocessor()
        self.calibrator = PlattCalibrator()
        self.model = None

        # Modality index partitions
        self.modality_features = {
            "numeric": NUMERIC_FEATURES,
            "text": TEXT_FEATURES,
            "graph": GRAPH_FEATURES,
            "fncs": FNCS_FEATURES,
        }
        self.modality_indices = {}
        for mod, feats in self.modality_features.items():
            self.modality_indices[mod] = [self.all_features.index(f) for f in feats]

    def fit(self, df: pd.DataFrame):
        """Fit standalone Model 9 XGBoost (used only for held-out inference or inspection)."""
        X_raw = df[self.all_features].values
        y = df["label"].values

        X_scl = self.preprocessor.fit_transform(X_raw)

        n_pos = int(np.sum(y == 1))
        n_neg = int(np.sum(y == 0))
        scale_pos = float(n_neg / max(n_pos, 1))

        self.model = xgb.XGBClassifier(
            n_estimators=75,
            max_depth=3,
            learning_rate=0.06,
            subsample=0.85,
            colsample_bytree=0.85,
            scale_pos_weight=scale_pos,
            random_state=42,
            eval_metric="logloss",
            n_jobs=2,
        )
        self.model.fit(X_scl, y)

        train_raw_probs = self.model.predict_proba(X_scl)[:, 1]
        train_logits = logit(np.clip(train_raw_probs, 1e-6, 1.0 - 1e-6))
        self.calibrator.fit(train_logits, y)
        logger.info("MultiModalExplanationEngine standalone fitted successfully.")
        return self

    def explain_cohort_out_of_fold(
        self, df: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Compute strictly OUT-OF-FOLD calibrated risk scores, Brier score, calibration curve,
        and TreeSHAP attributions using 5-fold CIK-grouped cross-validation. Zero in-sample evaluation.
        """
        y = df["label"].values
        groups = df["cik"].values
        n_samples = len(df)
        X_raw = df[self.all_features].values

        # 1. Compute cohort-wide peer medians for contextual comparison
        peer_medians = {}
        for idx, f in enumerate(self.all_features):
            col_vals = df[f].dropna().values
            peer_medians[f] = float(np.median(col_vals)) if len(col_vals) > 0 else 0.0

        # 2. 5-Fold CIK-Grouped Stratified CV to guarantee out-of-fold inference
        sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
        cv_splits = list(sgkf.split(df, y, groups))

        oof_probs = np.zeros(n_samples)
        oof_shaps = np.zeros((n_samples, len(self.all_features)))
        oof_fold_id = np.zeros(n_samples, dtype=int)

        for fold_idx, (train_idx, val_idx) in enumerate(cv_splits, 1):
            df_train = df.iloc[train_idx]
            df_val = df.iloc[val_idx]
            y_train = y[train_idx]

            prep = InFoldPreprocessor()
            X_train_scl = prep.fit_transform(df_train[self.all_features].values)
            X_val_scl = prep.transform(df_val[self.all_features].values)

            n_pos = int(np.sum(y_train == 1))
            n_neg = int(np.sum(y_train == 0))
            scale_pos = float(n_neg / max(n_pos, 1))

            fold_model = xgb.XGBClassifier(
                n_estimators=75,
                max_depth=3,
                learning_rate=0.06,
                subsample=0.85,
                colsample_bytree=0.85,
                scale_pos_weight=scale_pos,
                random_state=42,
                eval_metric="logloss",
                n_jobs=2,
            )
            fold_model.fit(X_train_scl, y_train)

            train_raw_probs = fold_model.predict_proba(X_train_scl)[:, 1]
            train_logits = logit(np.clip(train_raw_probs, 1e-6, 1.0 - 1e-6))
            calibrator = PlattCalibrator()
            calibrator.fit(train_logits, y_train)

            # Predict held-out validation samples strictly out-of-fold
            val_raw_probs = fold_model.predict_proba(X_val_scl)[:, 1]
            val_logits = logit(np.clip(val_raw_probs, 1e-6, 1.0 - 1e-6))
            val_cal_probs = calibrator.calibrate(val_logits)
            oof_probs[val_idx] = val_cal_probs

            # Native XGBoost TreeSHAP contributions on held-out validation split
            booster = fold_model.get_booster()
            dmat_val = xgb.DMatrix(X_val_scl)
            shap_val = booster.predict(dmat_val, pred_contribs=True)[:, :-1]
            oof_shaps[val_idx] = shap_val
            oof_fold_id[val_idx] = fold_idx

        # 3. Calibration Diagnostics & Brier Score
        brier = float(brier_score_loss(y, oof_probs))
        prob_true, prob_pred = calibration_curve(y, oof_probs, n_bins=10)
        calibration_diagnostics = {
            "brier_score": round(brier, 4),
            "fraction_of_positives": [round(float(p), 4) for p in prob_true],
            "mean_predicted_value": [round(float(p), 4) for p in prob_pred],
            "is_out_of_fold": True,
        }

        # 4. Generate Explanations for all cohort company-years
        explanations = []

        for i in range(len(df)):
            row = df.iloc[i]
            cik = str(row["cik"]).zfill(10)
            fy = int(row["fiscal_year"])
            acc = row.get("accession_number") or ""
            prob = float(oof_probs[i])
            risk_score = int(round(100.0 * prob))
            risk_score = max(0, min(100, risk_score))

            if risk_score <= 29:
                category = "Low"
            elif risk_score <= 59:
                category = "Moderate"
            elif risk_score <= 79:
                category = "High"
            else:
                category = "Very High"

            review_label = "Fraud Risk / Review Priority"

            # Modality SHAP Aggregation (in log-odds)
            modality_breakdown = {}
            total_pos_shap = 0.0
            for mod, idxs in self.modality_indices.items():
                mod_shap_sum = float(np.sum(oof_shaps[i, idxs]))
                modality_breakdown[mod] = {
                    "shap_sum": round(mod_shap_sum, 4),
                    "positive_shap": round(
                        float(np.sum(np.maximum(oof_shaps[i, idxs], 0.0))), 4
                    ),
                }
                total_pos_shap += max(0.0, mod_shap_sum)

            for mod in modality_breakdown:
                mod_sum = modality_breakdown[mod]["shap_sum"]
                pct = (
                    (max(0.0, mod_sum) / max(total_pos_shap, 1e-6)) * 100.0
                    if total_pos_shap > 0
                    else 25.0
                )
                modality_breakdown[mod]["risk_share_pct"] = round(pct, 1)

            # Top Individual Factors (Ranked by absolute log-odds impact)
            row_shaps = oof_shaps[i]
            # Filter out inert zero factors (observed 0.00 and near-zero SHAP)
            valid_feat_indices = []
            for f_idx in range(len(self.all_features)):
                f_shap = row_shaps[f_idx]
                f_val = X_raw[i, f_idx] if not np.isnan(X_raw[i, f_idx]) else 0.0
                if abs(f_shap) > 1e-5 or abs(f_val) > 1e-5:
                    valid_feat_indices.append(f_idx)

            if not valid_feat_indices:
                valid_feat_indices = list(range(len(self.all_features)))

            # Sort by positive risk contribution first, then by absolute impact
            sorted_indices = sorted(valid_feat_indices, key=lambda idx: -row_shaps[idx])
            top_factors = []

            for rank, feat_idx in enumerate(sorted_indices[:6], 1):
                f_name = self.all_features[feat_idx]
                f_shap = float(row_shaps[feat_idx])
                f_val = float(X_raw[i, feat_idx]) if not np.isnan(X_raw[i, feat_idx]) else 0.0
                f_med = peer_medians.get(f_name, 0.0)
                h_name = HUMAN_FEATURE_NAMES.get(f_name, f_name)

                mod_belong = "numeric"
                for m, idxs in self.modality_indices.items():
                    if feat_idx in idxs:
                        mod_belong = m
                        break

                direction_text = "pushes risk up" if f_shap > 0 else "pushes risk down"
                plain_desc = (
                    f"{h_name}: observed {f_val:.2f} (peer median {f_med:.2f}), "
                    f"{direction_text} by {abs(f_shap):.2f} log-odds"
                )

                pct_contrib = (
                    (max(0.0, f_shap) / max(total_pos_shap, 1e-6)) * 100.0
                    if total_pos_shap > 0
                    else 0.0
                )

                factor_obj = {
                    "rank": rank,
                    "feature_name": f_name,
                    "human_name": h_name,
                    "modality": mod_belong,
                    "raw_value": round(f_val, 4),
                    "peer_median": round(f_med, 4),
                    "shap_value": round(f_shap, 4),
                    "shap_unit": "log-odds contribution",
                    "direction": direction_text,
                    "risk_contribution_pct": round(pct_contrib, 1),
                    "plain_language": plain_desc,
                }
                top_factors.append(factor_obj)

            top_mod = max(modality_breakdown.items(), key=lambda x: x[1]["risk_share_pct"])[0]
            top_f_desc = top_factors[0]["human_name"] if top_factors else "Financial ratios"

            summary = (
                f"Review Priority is categorized as {category} with an Out-of-Fold Calibrated Risk Score of {risk_score}/100. "
                f"The primary multi-modal risk driver is the {top_mod.upper()} modality, contributing "
                f"{modality_breakdown[top_mod]['risk_share_pct']}% of detected anomaly signal. "
                f"The highest individual risk factor is {top_f_desc}. "
                f"This assessment represents an algorithmic triage signal for forensic accounting review and is not proof of fraud."
            )

            explanations.append(
                {
                    "cik": cik,
                    "fiscal_year": fy,
                    "accession_number": acc,
                    "fraud_probability": round(prob, 4),
                    "risk_score": risk_score,
                    "risk_category": category,
                    "review_priority_label": review_label,
                    "modality_breakdown": modality_breakdown,
                    "top_factors": top_factors,
                    "plain_language_summary": summary,
                    "is_out_of_fold": True,
                    "fold_id": int(oof_fold_id[i]),
                }
            )

        return explanations, calibration_diagnostics

    def explain_cohort(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Backwards compatible wrapper redirecting to out-of-fold explanations."""
        exps, _ = self.explain_cohort_out_of_fold(df)
        return exps
