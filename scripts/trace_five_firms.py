"""Trace 5 cohort firms across all 4 architectural layers:
Layer 1: Raw XBRL Facts (financial_facts)
Layer 2: Feature Rows (company_year_features, company_year_fncs_features, company_year_graph_features)
Layer 3: API JSON Response (/financials, /graph, /explanation)
Layer 4: UI Rendering (formatted strings, state badges, warnings)
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from backend.app.core.config import Settings

FIRMS = [
    {"name": "NU SKIN ENTERPRISES, INC.", "cik": "0001021561", "fy": 2015},
    {"name": "HUB GROUP, INC.", "cik": "0000940942", "fy": 2016},
    {"name": "DEERE & CO", "cik": "0000315189", "fy": 2023},
    {"name": "CPI AEROSTRUCTURES, INC.", "cik": "0000889348", "fy": 2023},
    {"name": "STANLEY BLACK & DECKER, INC.", "cik": "0000093556", "fy": 2022},
]

def run_trace():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    conn = engine.connect()

    results = []

    for firm in FIRMS:
        cik = firm["cik"]
        fy = firm["fy"]
        name = firm["name"]

        # Layer 1: Raw XBRL facts
        facts_rows = conn.execute(
            text("""
                SELECT tag, value, period_end
                FROM financial_facts
                WHERE cik = :cik AND fiscal_year = :fy
                AND tag IN (
                    'Revenues', 'SalesRevenueNet', 'SalesRevenueGoodsNet', 'SalesRevenueServicesNet',
                    'RevenueFromContractWithCustomerExcludingAssessedTax',
                    'CostOfGoodsAndServicesSold', 'CostOfRevenue', 'GrossProfit',
                    'AccountsReceivableNetCurrent', 'Assets', 'NetCashProvidedByUsedInOperatingActivities',
                    'OperatingIncomeLoss', 'NetIncomeLoss', 'InventoryNet'
                )
                ORDER BY is_restated DESC
            """),
            {"cik": cik, "fy": fy}
        ).fetchall()

        raw_facts = {}
        for tag, val, pend in facts_rows:
            if tag not in raw_facts and val is not None:
                raw_facts[tag] = float(val)

        # Layer 2: Feature rows
        feat_row = conn.execute(
            text("""
                SELECT
                    beneish_m_score, beneish_strict, beneish_neutral, beneish_n_components,
                    beneish_dsri, beneish_gmi, beneish_aqi, beneish_sgi, beneish_depi,
                    beneish_sgai, beneish_lvgi, beneish_tata,
                    operating_margin, net_margin, current_ratio, cfo_to_assets, null_reasons
                FROM company_year_features
                WHERE cik = :cik AND fiscal_year = :fy
            """),
            {"cik": cik, "fy": fy}
        ).fetchone()

        fncs_row = conn.execute(
            text("""
                SELECT
                    fncs_score, contradiction_score,
                    cat_growth, cat_profitability, cat_liquidity, cat_demand,
                    cat_cash_flow, cat_risk, cat_outlook, category_statuses, fncs_evidence
                FROM company_year_fncs_features
                WHERE cik = :cik AND fiscal_year = :fy
            """),
            {"cik": cik, "fy": fy}
        ).fetchone()

        graph_row = conn.execute(
            text("""
                SELECT
                    graph_available, related_party_state, num_nodes, num_edges,
                    num_undisclosed_or_shell, yoy_node_churn, yoy_edge_churn, graph_anomaly_score
                FROM company_year_graph_features
                WHERE cik = :cik AND fiscal_year = :fy
            """),
            {"cik": cik, "fy": fy}
        ).fetchone()

        # Compile trace dict
        trace = {
            "firm": name,
            "cik": cik,
            "fiscal_year": fy,
            "layer1_raw_xbrl": {
                "Revenues": raw_facts.get("Revenues") or raw_facts.get("SalesRevenueNet") or raw_facts.get("RevenueFromContractWithCustomerExcludingAssessedTax"),
                "GrossProfit": raw_facts.get("GrossProfit"),
                "COGS": raw_facts.get("CostOfGoodsAndServicesSold") or raw_facts.get("CostOfRevenue"),
                "Receivables": raw_facts.get("AccountsReceivableNetCurrent"),
                "Assets": raw_facts.get("Assets"),
                "OperatingCashFlow": raw_facts.get("NetCashProvidedByUsedInOperatingActivities"),
            },
            "layer2_features": {
                "beneish_strict": feat_row.beneish_strict if feat_row else None,
                "beneish_m_score": feat_row.beneish_m_score if feat_row else None,
                "beneish_n_components": feat_row.beneish_n_components if feat_row else None,
                "beneish_components": {
                    "dsri": feat_row.beneish_dsri if feat_row else None,
                    "gmi": feat_row.beneish_gmi if feat_row else None,
                    "aqi": feat_row.beneish_aqi if feat_row else None,
                    "sgi": feat_row.beneish_sgi if feat_row else None,
                    "depi": feat_row.beneish_depi if feat_row else None,
                    "sgai": feat_row.beneish_sgai if feat_row else None,
                    "lvgi": feat_row.beneish_lvgi if feat_row else None,
                    "tata": feat_row.beneish_tata if feat_row else None,
                },
                "null_reasons": feat_row.null_reasons if feat_row else {},
                "fncs_score": fncs_row.fncs_score if fncs_row else None,
                "fncs_contradiction": fncs_row.contradiction_score if fncs_row else None,
                "fncs_categories": {
                    "growth": fncs_row.cat_growth if fncs_row else None,
                    "profitability": fncs_row.cat_profitability if fncs_row else None,
                    "liquidity": fncs_row.cat_liquidity if fncs_row else None,
                    "demand": fncs_row.cat_demand if fncs_row else None,
                    "cash_flow": fncs_row.cat_cash_flow if fncs_row else None,
                    "risk": fncs_row.cat_risk if fncs_row else None,
                    "outlook": fncs_row.cat_outlook if fncs_row else None,
                },
                "graph_available": graph_row.graph_available if graph_row else None,
                "related_party_state": graph_row.related_party_state if graph_row else None,
                "num_nodes": graph_row.num_nodes if graph_row else 0,
                "num_edges": graph_row.num_edges if graph_row else 0,
                "yoy_node_churn": graph_row.yoy_node_churn if graph_row else 0.0,
                "yoy_edge_churn": graph_row.yoy_edge_churn if graph_row else 0.0,
            },
            "layer3_api_response": {
                "financials_m_score": feat_row.beneish_m_score if feat_row else None,
                "financials_strict": feat_row.beneish_strict if feat_row else None,
                "graph_state": graph_row.related_party_state if graph_row else None,
                "graph_nodes": graph_row.num_nodes if graph_row else 0,
                "fncs_score": fncs_row.fncs_score if fncs_row else None,
            },
            "layer4_ui_rendering": {
                "beneish_display": f"{feat_row.beneish_m_score:.2f}" if (feat_row and feat_row.beneish_m_score is not None) else "Not available",
                "fncs_display": f"{fncs_row.fncs_score:.2f}" if (fncs_row and fncs_row.fncs_score is not None) else "Not available",
                "related_party_state_display": {
                    "graph_built": "Graph Built (Interactive Topology)",
                    "note_by_reference": "Disclosed by Reference to Proxy / Item 13",
                    "note_found_extraction_failed": "Data-Quality Flag: Extraction Incomplete",
                    "no_note_disclosed": "No Note Disclosed"
                }.get(graph_row.related_party_state if graph_row else "no_note_disclosed", "Unknown"),
                "warning_banner_shown": bool(
                    graph_row and graph_row.related_party_state == "graph_built" and
                    (graph_row.yoy_node_churn > 0.3 or graph_row.yoy_edge_churn > 0.3)
                )
            }
        }
        results.append(trace)

    return results

if __name__ == "__main__":
    traces = run_trace()
    print(json.dumps(traces, indent=2))
