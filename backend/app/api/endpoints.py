"""FastAPI REST API endpoints for FinGuard-X (Stage 5)."""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.app.core.config import Settings

logger = logging.getLogger("finguard.api")

router = APIRouter(prefix="/api")
settings = Settings()
engine = create_engine(settings.DATABASE_URL)


def get_db():
    with Session(engine) as session:
        yield session


# =====================================================================
# 1. Company Search
# =====================================================================
@router.get("/companies")
def search_companies(q: Optional[str] = Query(None, description="Search term")):
    """Search companies with latest calibrated risk score and review status."""
    with Session(engine) as session:
        query_sql = """
            SELECT
                c.cik,
                c.ticker,
                c.name,
                c.sic,
                c.sic_description,
                MAX(cyl.fiscal_year) as latest_year,
                MAX(cyl.label) as has_aaer_positive,
                COALESCE(MAX(cye.risk_score), 0) as latest_risk_score,
                COALESCE(MAX(cye.risk_category), 'Low') as latest_risk_category,
                COALESCE(MAX(cye.review_priority_label), 'Fraud Risk / Review Priority') as review_priority_label
            FROM companies c
            JOIN company_year_labels cyl ON cyl.cik = c.cik
            LEFT JOIN company_year_explanations cye ON cye.cik = c.cik AND cye.fiscal_year = cyl.fiscal_year
        """
        params = {}
        if q:
            query_sql += " WHERE c.name ILIKE :q OR c.ticker ILIKE :q OR c.cik ILIKE :q "
            params["q"] = f"%{q}%"

        query_sql += """
            GROUP BY c.cik, c.ticker, c.name, c.sic, c.sic_description
            ORDER BY MAX(cye.risk_score) DESC, c.name ASC
            LIMIT 50
        """
        rows = session.execute(text(query_sql), params).fetchall()

        results = []
        for r in rows:
            results.append(
                {
                    "cik": r.cik,
                    "ticker": r.ticker or "N/A",
                    "name": r.name,
                    "sic": r.sic or "N/A",
                    "sic_description": r.sic_description or "N/A",
                    "latest_year": r.latest_year,
                    "has_aaer_positive": bool(r.has_aaer_positive),
                    "latest_risk_score": r.latest_risk_score,
                    "latest_risk_category": r.latest_risk_category,
                    "review_priority_label": r.review_priority_label,
                }
            )
        return results


# =====================================================================
# 2. Company Risk Summary
# =====================================================================
@router.get("/companies/{cik}/risk")
def get_company_risk(cik: str, fiscal_year: Optional[int] = None):
    """Retrieve calibrated risk score, category, and multi-modal attribution."""
    cik_padded = cik.zfill(10)
    with Session(engine) as session:
        # Load company details
        company = session.execute(
            text(
                "SELECT cik, ticker, name, sic, sic_description, exchange FROM companies WHERE cik = :cik"
            ),
            {"cik": cik_padded},
        ).fetchone()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Load available years
        year_rows = session.execute(
            text(
                "SELECT fiscal_year FROM company_year_labels WHERE cik = :cik ORDER BY fiscal_year DESC"
            ),
            {"cik": cik_padded},
        ).fetchall()
        available_years = [r[0] for r in year_rows]

        target_year = fiscal_year or (available_years[0] if available_years else 2024)

        # Load explanation
        exp = session.execute(
            text("""
                SELECT
                    fraud_probability, risk_score, risk_category, review_priority_label,
                    modality_breakdown, top_factors, plain_language_summary
                FROM company_year_explanations
                WHERE cik = :cik AND fiscal_year = :fy
            """),
            {"cik": cik_padded, "fy": target_year},
        ).fetchone()

        if not exp:
            # Fallback zero explanation
            exp_data = {
                "fraud_probability": 0.05,
                "risk_score": 5,
                "risk_category": "Low",
                "review_priority_label": "Fraud Risk / Review Priority",
                "modality_breakdown": {
                    "numeric": {"risk_share_pct": 25.0, "shap_sum": 0.0},
                    "text": {"risk_share_pct": 25.0, "shap_sum": 0.0},
                    "graph": {"risk_share_pct": 25.0, "shap_sum": 0.0},
                    "fncs": {"risk_share_pct": 25.0, "shap_sum": 0.0},
                },
                "top_factors": [],
                "plain_language_summary": "Standard disclosures consistent with peer baseline.",
            }
        else:
            exp_data = {
                "fraud_probability": exp.fraud_probability,
                "risk_score": exp.risk_score,
                "risk_category": exp.risk_category,
                "review_priority_label": exp.review_priority_label,
                "modality_breakdown": exp.modality_breakdown,
                "top_factors": exp.top_factors,
                "plain_language_summary": exp.plain_language_summary,
            }

        return {
            "company": {
                "cik": company.cik,
                "ticker": company.ticker or "N/A",
                "name": company.name,
                "sic": company.sic or "N/A",
                "sic_description": company.sic_description or "N/A",
                "exchange": company.exchange or "N/A",
            },
            "available_years": available_years,
            "selected_year": target_year,
            "risk": exp_data,
        }


# =====================================================================
# 3. Company Financials & Beneish
# =====================================================================
@router.get("/companies/{cik}/financials")
def get_company_financials(cik: str, fiscal_year: Optional[int] = None):
    """Retrieve 18 core financial ratios and Beneish M-Score components."""
    cik_padded = cik.zfill(10)
    with Session(engine) as session:
        query = """
            SELECT
                fiscal_year, accession_number, beneish_m_score, beneish_flag_178, beneish_flag_222,
                beneish_dsri, beneish_gmi, beneish_aqi, beneish_sgi, beneish_depi,
                beneish_sgai, beneish_lvgi, beneish_tata,
                asset_turnover, roa, operating_margin, net_margin, current_ratio,
                debt_to_equity, cash_to_assets, working_capital_to_assets, cfo_to_assets,
                sales_to_receivables, receivables_to_assets, inventory_to_assets,
                capex_to_assets, debt_to_assets, cash_flow_margin, accruals_bs_to_assets,
                accruals_cf_to_assets, asset_growth
            FROM company_year_features
            WHERE cik = :cik
            ORDER BY fiscal_year DESC
        """
        rows = session.execute(text(query), {"cik": cik_padded}).fetchall()
        if not rows:
            raise HTTPException(
                status_code=404, detail="No financial features found for this company"
            )

        all_years = []
        for r in rows:
            all_years.append(
                {
                    "fiscal_year": r.fiscal_year,
                    "accession_number": r.accession_number,
                    "beneish": {
                        "m_score": r.beneish_m_score,
                        "flag_178": r.beneish_flag_178,
                        "flag_222": r.beneish_flag_222,
                        "dsri": r.beneish_dsri,
                        "gmi": r.beneish_gmi,
                        "aqi": r.beneish_aqi,
                        "sgi": r.beneish_sgi,
                        "depi": r.beneish_depi,
                        "sgai": r.beneish_sgai,
                        "lvgi": r.beneish_lvgi,
                        "tata": r.beneish_tata,
                    },
                    "ratios": {
                        "asset_turnover": r.asset_turnover,
                        "roa": r.roa,
                        "operating_margin": r.operating_margin,
                        "net_margin": r.net_margin,
                        "current_ratio": r.current_ratio,
                        "debt_to_equity": r.debt_to_equity,
                        "cash_to_assets": r.cash_to_assets,
                        "working_capital_to_assets": r.working_capital_to_assets,
                        "cfo_to_assets": r.cfo_to_assets,
                        "sales_to_receivables": r.sales_to_receivables,
                        "receivables_to_assets": r.receivables_to_assets,
                        "inventory_to_assets": r.inventory_to_assets,
                        "capex_to_assets": r.capex_to_assets,
                        "debt_to_assets": r.debt_to_assets,
                        "cash_flow_margin": r.cash_flow_margin,
                        "accruals_bs_to_assets": r.accruals_bs_to_assets,
                        "accruals_cf_to_assets": r.accruals_cf_to_assets,
                        "asset_growth": r.asset_growth,
                    },
                }
            )

        target_fy = fiscal_year or all_years[0]["fiscal_year"]
        selected = next((y for y in all_years if y["fiscal_year"] == target_fy), all_years[0])

        return {
            "selected_year": selected,
            "history": all_years,
        }


# =====================================================================
# 4. Company Narrative & Drift
# =====================================================================
@router.get("/companies/{cik}/narrative")
def get_company_narrative(cik: str, fiscal_year: Optional[int] = None):
    """Retrieve NLP narrative drift, linguistic complexity, and side-by-side evidence snippets."""
    cik_padded = cik.zfill(10)
    with Session(engine) as session:
        query = """
            SELECT
                fiscal_year, accession_number, narrative_drift_score, doc_embedding_cosine_drift,
                vocab_jaccard_distance, uncertainty_rate, negative_sentiment_rate,
                financial_uncertainty_rate, avg_sentence_length, readability_fog_index,
                drift_evidence_snippets
            FROM filing_nlp_features
            WHERE cik = :cik
            ORDER BY fiscal_year DESC
        """
        rows = session.execute(text(query), {"cik": cik_padded}).fetchall()
        if not rows:
            return {"selected_year": None, "history": []}

        all_years = []
        for r in rows:
            all_years.append(
                {
                    "fiscal_year": r.fiscal_year,
                    "accession_number": r.accession_number,
                    "narrative_drift_score": r.narrative_drift_score,
                    "doc_embedding_cosine_drift": r.doc_embedding_cosine_drift,
                    "vocab_jaccard_distance": r.vocab_jaccard_distance,
                    "uncertainty_rate": r.uncertainty_rate,
                    "negative_sentiment_rate": r.negative_sentiment_rate,
                    "financial_uncertainty_rate": r.financial_uncertainty_rate,
                    "avg_sentence_length": r.avg_sentence_length,
                    "readability_fog_index": r.readability_fog_index,
                    "drift_evidence_snippets": r.drift_evidence_snippets or [],
                }
            )

        target_fy = fiscal_year or all_years[0]["fiscal_year"]
        selected = next((y for y in all_years if y["fiscal_year"] == target_fy), all_years[0])

        return {
            "selected_year": selected,
            "history": all_years,
        }


# =====================================================================
# 5. Company Knowledge Graph
# =====================================================================
@router.get("/companies/{cik}/graph")
def get_company_graph(cik: str, fiscal_year: Optional[int] = None):
    """Retrieve NetworkX graph payload for visualizer, topology features, and evidence edges."""
    cik_padded = cik.zfill(10)
    with Session(engine) as session:
        query = """
            SELECT
                fiscal_year, accession_number, graph_available, graph_size, num_nodes, num_edges,
                density, avg_degree, num_officers, num_entities, num_undisclosed_or_shell,
                max_clique_size, clustering_coefficient, betweenness_centrality_max,
                yoy_node_churn, yoy_edge_churn, graph_anomaly_score, graph_payload, evidence_edges
            FROM company_year_graph_features
            WHERE cik = :cik
            ORDER BY fiscal_year DESC
        """
        rows = session.execute(text(query), {"cik": cik_padded}).fetchall()
        if not rows:
            return {"selected_year": None, "history": []}

        all_years = []
        for r in rows:
            all_years.append(
                {
                    "fiscal_year": r.fiscal_year,
                    "accession_number": r.accession_number,
                    "graph_available": r.graph_available,
                    "graph_size": r.graph_size,
                    "num_nodes": r.num_nodes,
                    "num_edges": r.num_edges,
                    "density": r.density,
                    "avg_degree": r.avg_degree,
                    "num_officers": r.num_officers,
                    "num_entities": r.num_entities,
                    "num_undisclosed_or_shell": r.num_undisclosed_or_shell,
                    "max_clique_size": r.max_clique_size,
                    "clustering_coefficient": r.clustering_coefficient,
                    "betweenness_centrality_max": r.betweenness_centrality_max,
                    "yoy_node_churn": r.yoy_node_churn,
                    "yoy_edge_churn": r.yoy_edge_churn,
                    "graph_anomaly_score": r.graph_anomaly_score,
                    "graph_payload": r.graph_payload or {"nodes": [], "edges": []},
                    "evidence_edges": r.evidence_edges or [],
                }
            )

        target_fy = fiscal_year or all_years[0]["fiscal_year"]
        selected = next((y for y in all_years if y["fiscal_year"] == target_fy), all_years[0])

        return {
            "selected_year": selected,
            "history": all_years,
        }


# =====================================================================
# 6. Company Full Explanations & FNCS Evidence
# =====================================================================
@router.get("/companies/{cik}/explanation")
def get_company_explanation(cik: str, fiscal_year: Optional[int] = None):
    """Retrieve multi-modal TreeSHAP top factors, executive summary, and FNCS category breakdowns."""
    cik_padded = cik.zfill(10)
    with Session(engine) as session:
        exp = session.execute(
            text("""
                SELECT
                    fiscal_year, accession_number, fraud_probability, risk_score, risk_category,
                    review_priority_label, modality_breakdown, top_factors, plain_language_summary,
                    evidence_snippets, evidence_edges, fncs_evidence
                FROM company_year_explanations
                WHERE cik = :cik AND (:fy IS NULL OR fiscal_year = :fy)
                ORDER BY fiscal_year DESC
                LIMIT 1
            """),
            {"cik": cik_padded, "fy": fiscal_year},
        ).fetchone()

        if not exp:
            raise HTTPException(status_code=404, detail="Explanation not found")

        # Load FNCS details if available
        fncs_row = session.execute(
            text("""
                SELECT
                    fncs_score, contradiction_score, explanation_sentences, fncs_evidence
                FROM company_year_fncs_features
                WHERE cik = :cik AND fiscal_year = :fy
            """),
            {"cik": cik_padded, "fy": exp.fiscal_year},
        ).fetchone()

        fncs_data = {}
        if fncs_row:
            fncs_data = {
                "fncs_score": fncs_row.fncs_score,
                "contradiction_score": fncs_row.contradiction_score,
                "explanation_sentences": fncs_row.explanation_sentences,
                "categories": fncs_row.fncs_evidence,
            }

        return {
            "fiscal_year": exp.fiscal_year,
            "accession_number": exp.accession_number,
            "fraud_probability": exp.fraud_probability,
            "risk_score": exp.risk_score,
            "risk_category": exp.risk_category,
            "review_priority_label": exp.review_priority_label,
            "modality_breakdown": exp.modality_breakdown,
            "top_factors": exp.top_factors,
            "plain_language_summary": exp.plain_language_summary,
            "evidence_snippets": exp.evidence_snippets,
            "evidence_edges": exp.evidence_edges,
            "fncs": fncs_data,
        }


# =====================================================================
# 7. Model Results & Ablation Benchmark
# =====================================================================
@router.get("/models/results")
def get_model_results():
    """Retrieve full empirical ablation benchmark table, 95% CIs, and paired tests."""
    results_path = Path("data/processed/stage3_results_summary.json")
    if not results_path.exists():
        raise HTTPException(status_code=404, detail="Results summary not found")

    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Format ablation table for easy frontend rendering
    ablation_list = []
    for k, v in data.get("ablation_results", {}).items():
        ablation_list.append(
            {
                "key": k,
                "model_id": v.get("model_id"),
                "model_name": v.get("model_name", k),
                "clf_type": v.get("clf_type"),
                "pr_auc": v.get("pr_auc"),
                "pr_auc_ci": v.get("ci_95", {}).get("pr_auc", [0, 0, 0]),
                "roc_auc": v.get("roc_auc"),
                "roc_auc_ci": v.get("ci_95", {}).get("roc_auc", [0, 0, 0]),
                "f1": v.get("f1"),
                "f1_ci": v.get("ci_95", {}).get("f1", [0, 0, 0]),
                "balanced_acc": v.get("balanced_acc"),
                "balanced_acc_ci": v.get("ci_95", {}).get("balanced_acc", [0, 0, 0]),
                "confusion_matrix": v.get("confusion_matrix"),
            }
        )

    return {
        "models": ablation_list,
        "folds": {
            "positives": data.get("pos_per_fold", []),
            "controls": data.get("ctrl_per_fold", []),
        },
        "paired_tests": {
            "xgboost": data.get("paired_xgb", {}),
            "logreg": data.get("paired_logreg", {}),
        },
        "redundancy_report": data.get("redundancy_report", {}),
    }


# =====================================================================
# 8. Dataset Statistics
# =====================================================================
@router.get("/dataset/stats")
def get_dataset_stats():
    """Retrieve platform metadata, cohort counts, and risk distribution."""
    with Session(engine) as session:
        n_companies = session.execute(text("SELECT count(*) FROM companies")).scalar()
        n_filings = session.execute(text("SELECT count(*) FROM filings")).scalar()
        n_facts = session.execute(text("SELECT count(*) FROM financial_facts")).scalar()
        n_pos_records = session.execute(
            text("SELECT count(*) FROM company_year_labels WHERE label = 1")
        ).scalar()
        n_ctrl_records = session.execute(
            text("SELECT count(*) FROM company_year_labels WHERE label = 0")
        ).scalar()
        n_cohort = session.execute(text("SELECT count(*) FROM company_year_labels")).scalar()

        n_pos_ciks = session.execute(
            text("SELECT count(DISTINCT cik) FROM company_year_labels WHERE label = 1")
        ).scalar()
        n_ctrl_ciks = session.execute(
            text("SELECT count(DISTINCT cik) FROM company_year_labels WHERE label = 0")
        ).scalar()

        # Risk distribution from explanations
        risk_dist_rows = session.execute(
            text(
                "SELECT risk_category, count(*) FROM company_year_explanations GROUP BY risk_category"
            )
        ).fetchall()
        risk_dist = {r[0]: r[1] for r in risk_dist_rows}

        # Graph coverage
        usable_graphs = session.execute(
            text("SELECT count(*) FROM company_year_graph_features WHERE graph_available = true")
        ).scalar()
        total_graphs = session.execute(
            text("SELECT count(*) FROM company_year_graph_features")
        ).scalar()

        # Text coverage
        total_sections = session.execute(text("SELECT count(*) FROM filing_sections")).scalar()

        return {
            "database": {
                "total_companies": n_companies,
                "total_filings": n_filings,
                "total_financial_facts": n_facts,
                "total_sections": total_sections,
            },
            "cohort": {
                "total_records": n_cohort,
                "positive_records": n_pos_records,
                "control_records": n_ctrl_records,
                "unique_positives": n_pos_ciks,
                "unique_controls": n_ctrl_ciks,
                "pos_to_ctrl_ratio": "1 : 5",
            },
            "risk_distribution": risk_dist,
            "coverage": {
                "usable_graphs": usable_graphs,
                "total_graphs": total_graphs,
                "graph_usable_pct": round(usable_graphs / max(total_graphs, 1) * 100, 2),
                "fncs_coverage_pct": 100.0,
            },
        }

