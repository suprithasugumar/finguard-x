"""Multi-Modal TreeSHAP explanation engine, modality grouping, and plain-language risk attribution (Stage 4)."""
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import expit, logit
import xgboost as xgb

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
    """Trains Model 9 XGBoost and produces multi-modal SHAP attributions, calibrated scores, and plain-language factors."""

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
        """Fit Model 9 XGBoost and Platt Calibrator on full training cohort."""
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
        logger.info("MultiModalExplanationEngine fitted and calibrated successfully.")
        return self

    def explain_cohort(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Compute calibrated risk score and SHAP attributions for every company-year in the cohort."""
        X_raw = df[self.all_features].values
        X_scl = self.preprocessor.transform(X_raw)

        # 1. Calibrated Risk Probabilities & Scores
        raw_probs = self.model.predict_proba(X_scl)[:, 1]
        logits = logit(np.clip(raw_probs, 1e-6, 1.0 - 1e-6))
        cal_probs = self.calibrator.calibrate(logits)

        # 2. Native XGBoost TreeSHAP contributions
        booster = self.model.get_booster()
        dmat = xgb.DMatrix(X_scl)
        # Shape: (n_samples, n_features + 1), last column is base expected value
        shap_contribs = booster.predict(dmat, pred_contribs=True)[:, :-1]

        explanations = []

        for i in range(len(df)):
            row = df.iloc[i]
            cik = row["cik"]
            fy = int(row["fiscal_year"])
            acc = row.get("accession_number") or ""
            prob = float(cal_probs[i])
            risk_score = int(round(100.0 * prob))
            risk_score = max(0, min(100, risk_score))

            # Risk Category classification
            if risk_score <= 29:
                category = "Low"
            elif risk_score <= 59:
                category = "Moderate"
            elif risk_score <= 79:
                category = "High"
            else:
                category = "Very High"

            review_label = "Fraud Risk / Review Priority"

            # 3. Modality SHAP Aggregation
            modality_breakdown = {}
            total_pos_shap = 0.0
            for mod, idxs in self.modality_indices.items():
                mod_shap_sum = float(np.sum(shap_contribs[i, idxs]))
                modality_breakdown[mod] = {
                    "shap_sum": round(mod_shap_sum, 4),
                    "positive_shap": round(float(np.sum(np.maximum(shap_contribs[i, idxs], 0.0))), 4),
                }
                total_pos_shap += max(0.0, mod_shap_sum)

            for mod in modality_breakdown:
                mod_sum = modality_breakdown[mod]["shap_sum"]
                pct = (max(0.0, mod_sum) / max(total_pos_shap, 1e-6)) * 100.0 if total_pos_shap > 0 else 25.0
                modality_breakdown[mod]["risk_share_pct"] = round(pct, 1)

            # 4. Top Individual Factors
            row_shaps = shap_contribs[i]
            sorted_indices = np.argsort(-row_shaps)  # Highest positive risk contribution first
            top_factors = []

            for rank, feat_idx in enumerate(sorted_indices[:6], 1):
                f_name = self.all_features[feat_idx]
                f_shap = float(row_shaps[feat_idx])
                f_val = float(X_raw[i, feat_idx]) if not np.isnan(X_raw[i, feat_idx]) else 0.0
                h_name = HUMAN_FEATURE_NAMES.get(f_name, f_name)

                # Determine which modality this belongs to
                mod_belong = "numeric"
                for m, idxs in self.modality_indices.items():
                    if feat_idx in idxs:
                        mod_belong = m
                        break

                pct_contrib = (max(0.0, f_shap) / max(total_pos_shap, 1e-6)) * 100.0 if total_pos_shap > 0 else 0.0

                factor_obj = {
                    "rank": rank,
                    "feature_name": f_name,
                    "human_name": h_name,
                    "modality": mod_belong,
                    "raw_value": round(f_val, 4),
                    "shap_value": round(f_shap, 4),
                    "risk_contribution_pct": round(pct_contrib, 1),
                    "plain_language": f"+{pct_contrib:.1f}% {h_name} (Observed value: {f_val:.2f})",
                }
                top_factors.append(factor_obj)

            # 5. Plain Language Executive Summary
            top_mod = max(modality_breakdown.items(), key=lambda x: x[1]["risk_share_pct"])[0]
            top_f_desc = top_factors[0]["human_name"] if top_factors else "Financial ratios"

            summary = (
                f"Review Priority is categorized as {category} with a Calibrated Fraud Risk Score of {risk_score}/100. "
                f"The primary multi-modal risk driver is the {top_mod.upper()} modality, contributing "
                f"{modality_breakdown[top_mod]['risk_share_pct']}% of total detected anomaly signal. "
                f"The highest individual risk factor is {top_f_desc}. "
                f"This assessment represents an algorithmic triage signal for forensic accounting review and is not proof of fraud."
            )

            # Packaged explanation payload
            explanations.append({
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
            })

        return explanations
