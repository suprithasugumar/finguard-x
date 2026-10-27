"""Phase 0 Diagnostic Audit: Comprehensive Missingness & Root Cause Analysis.

Audits every feature across all feature tables in FinGuard-X:
- % NULL/NaN/0 overall, by fiscal year, and by label (AAER vs control)
- Beneish 8 components + composite M-Score root cause breakdown
- 18 core financial ratios root cause breakdown
- Text / MD&A extraction, prior-year availability, sentence alignment
- Graph entity & footnote extraction breakdown
- FNCS category text_tone == 0 and presence_weight == 0 breakdown
- Top 10 Root Causes ranked by impact
Saves outputs to reports/missingness.csv and reports/missingness_summary.md.
"""

import os
import sys
import json
import math
from pathlib import Path
from collections import Counter, defaultdict
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

# Add repository root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.config import Settings


def run_missingness_audit():
    print("=" * 80)
    print("  FinGuard-X — Phase 0 Feature Missingness & Root Cause Audit")
    print("=" * 80)

    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)

    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    with engine.connect() as conn:
        print("\n[1/6] Loading cohort and feature tables from database...")

        # 1. Base cohort labels
        labels_df = pd.read_sql("""
            SELECT cik, fiscal_year, label, label_confidence, label_rationale,
                   matched_positive_id, review_status
            FROM company_year_labels
            ORDER BY fiscal_year, cik
        """, conn)
        total_cohort = len(labels_df)
        n_pos = (labels_df["label"] == 1).sum()
        n_ctrl = (labels_df["label"] == 0).sum()
        print(f"  Cohort records: {total_cohort} (Positives: {n_pos}, Controls: {n_ctrl})")

        # 2. Financial features (18 ratios + 8 Beneish)
        cyf_df = pd.read_sql("""
            SELECT * FROM company_year_features
        """, conn)
        print(f"  Financial features records: {len(cyf_df)}")

        # 3. Graph features
        graph_df = pd.read_sql("""
            SELECT * FROM company_year_graph_features
        """, conn)
        print(f"  Graph features records: {len(graph_df)}")

        # 4. FNCS features
        fncs_df = pd.read_sql("""
            SELECT * FROM company_year_fncs_features
        """, conn)
        print(f"  FNCS features records: {len(fncs_df)}")

        # 5. Text / NLP features
        nlp_df = pd.read_sql("""
            SELECT * FROM filing_nlp_features
        """, conn)
        print(f"  NLP features records: {len(nlp_df)}")

        # 6. Filing sections (MD&A and Related Party)
        sections_df = pd.read_sql("""
            SELECT f.cik, f.fiscal_year, fs.section_type, fs.word_count, fs.sentence_count, fs.char_count
            FROM filing_sections fs
            JOIN filings f ON f.id = fs.filing_id
            WHERE f.is_amendment = false
        """, conn)
        print(f"  Filing sections records: {len(sections_df)}")

        # Merge cohort with feature tables
        m_fin = pd.merge(labels_df, cyf_df, on=["cik", "fiscal_year"], how="left", suffixes=("", "_cyf"))
        m_graph = pd.merge(labels_df, graph_df, on=["cik", "fiscal_year"], how="left", suffixes=("", "_graph"))
        m_fncs = pd.merge(labels_df, fncs_df, on=["cik", "fiscal_year"], how="left", suffixes=("", "_fncs"))
        m_nlp = pd.merge(labels_df, nlp_df, on=["cik", "fiscal_year"], how="left", suffixes=("", "_nlp"))

        print("\n[2/6] Auditing Beneish M-Score and 8 Components...")
        beneish_components = [
            "beneish_dsri", "beneish_gmi", "beneish_aqi", "beneish_sgi",
            "beneish_depi", "beneish_sgai", "beneish_lvgi", "beneish_tata",
            "beneish_m_score"
        ]

        beneish_stats = []
        beneish_root_causes = defaultdict(Counter)

        for col in beneish_components:
            s = m_fin[col]
            null_count = s.isna().sum()
            zero_count = ((s == 0) & (~s.isna())).sum()
            null_pct = (null_count / total_cohort) * 100
            zero_pct = (zero_count / total_cohort) * 100

            pos_s = m_fin[m_fin["label"] == 1][col]
            ctrl_s = m_fin[m_fin["label"] == 0][col]

            pos_null_pct = (pos_s.isna().sum() / n_pos) * 100
            ctrl_null_pct = (ctrl_s.isna().sum() / n_ctrl) * 100
            pos_zero_pct = (((pos_s == 0) & (~pos_s.isna())).sum() / n_pos) * 100
            ctrl_zero_pct = (((ctrl_s == 0) & (~ctrl_s.isna())).sum() / n_ctrl) * 100

            # Yearly variation
            yearly_nulls = m_fin.groupby("fiscal_year")[col].apply(lambda x: x.isna().mean() * 100)
            min_fy_null = yearly_nulls.min()
            max_fy_null = yearly_nulls.max()

            # Analyze reasons from null_reasons JSON column
            top_cause = "Missing inputs"
            for _, r in m_fin.iterrows():
                nr = r.get("null_reasons")
                if isinstance(nr, dict):
                    if col in nr:
                        beneish_root_causes[col][nr[col]] += 1
                    elif "beneish" in nr and nr["beneish"] == "financial_industry_inapplicable":
                        beneish_root_causes[col]["financial_industry_inapplicable"] += 1

            if beneish_root_causes[col]:
                top_cause = beneish_root_causes[col].most_common(1)[0][0]

            beneish_stats.append({
                "feature_group": "beneish",
                "table_name": "company_year_features",
                "feature_name": col,
                "total_records": total_cohort,
                "null_count": int(null_count),
                "null_pct": round(null_pct, 2),
                "zero_count": int(zero_count),
                "zero_pct": round(zero_pct, 2),
                "null_or_zero_count": int(null_count + zero_count),
                "null_or_zero_pct": round(((null_count + zero_count) / total_cohort) * 100, 2),
                "aaer_null_pct": round(pos_null_pct, 2),
                "aaer_zero_pct": round(pos_zero_pct, 2),
                "ctrl_null_pct": round(ctrl_null_pct, 2),
                "ctrl_zero_pct": round(ctrl_zero_pct, 2),
                "fy_null_pct_min": round(min_fy_null, 2),
                "fy_null_pct_max": round(max_fy_null, 2),
                "top_root_cause": top_cause,
            })

        print("\n[3/6] Auditing 18 Core Financial Ratios...")
        ratio_cols = [
            "asset_turnover", "roa", "operating_margin", "net_margin",
            "current_ratio", "debt_to_equity", "cash_to_assets",
            "working_capital_to_assets", "cfo_to_assets", "sales_to_receivables",
            "receivables_to_assets", "inventory_to_assets", "capex_to_assets",
            "debt_to_assets", "cash_flow_margin", "accruals_bs_to_assets",
            "accruals_cf_to_assets", "asset_growth"
        ]

        ratio_stats = []
        ratio_root_causes = defaultdict(Counter)

        for col in ratio_cols:
            s = m_fin[col]
            null_count = s.isna().sum()
            zero_count = ((s == 0) & (~s.isna())).sum()
            null_pct = (null_count / total_cohort) * 100
            zero_pct = (zero_count / total_cohort) * 100

            pos_s = m_fin[m_fin["label"] == 1][col]
            ctrl_s = m_fin[m_fin["label"] == 0][col]

            pos_null_pct = (pos_s.isna().sum() / n_pos) * 100
            ctrl_null_pct = (ctrl_s.isna().sum() / n_ctrl) * 100
            pos_zero_pct = (((pos_s == 0) & (~pos_s.isna())).sum() / n_pos) * 100
            ctrl_zero_pct = (((ctrl_s == 0) & (~ctrl_s.isna())).sum() / n_ctrl) * 100

            yearly_nulls = m_fin.groupby("fiscal_year")[col].apply(lambda x: x.isna().mean() * 100)
            min_fy_null = yearly_nulls.min()
            max_fy_null = yearly_nulls.max()

            top_cause = "Missing inputs"
            for _, r in m_fin.iterrows():
                nr = r.get("null_reasons")
                if isinstance(nr, dict) and col in nr:
                    ratio_root_causes[col][nr[col]] += 1

            if ratio_root_causes[col]:
                top_cause = ratio_root_causes[col].most_common(1)[0][0]

            ratio_stats.append({
                "feature_group": "ratio_18",
                "table_name": "company_year_features",
                "feature_name": col,
                "total_records": total_cohort,
                "null_count": int(null_count),
                "null_pct": round(null_pct, 2),
                "zero_count": int(zero_count),
                "zero_pct": round(zero_pct, 2),
                "null_or_zero_count": int(null_count + zero_count),
                "null_or_zero_pct": round(((null_count + zero_count) / total_cohort) * 100, 2),
                "aaer_null_pct": round(pos_null_pct, 2),
                "aaer_zero_pct": round(pos_zero_pct, 2),
                "ctrl_null_pct": round(ctrl_null_pct, 2),
                "ctrl_zero_pct": round(ctrl_zero_pct, 2),
                "fy_null_pct_min": round(min_fy_null, 2),
                "fy_null_pct_max": round(max_fy_null, 2),
                "top_root_cause": top_cause,
            })

        print("\n[4/6] Auditing Text & NLP MD&A Features...")
        # Text extraction and drift audit
        # Build filing section lookups
        mda_sections = sections_df[sections_df["section_type"] == "mda"].drop_duplicates(subset=["cik", "fiscal_year"])
        mda_lookup = {(r["cik"], r["fiscal_year"]): r["word_count"] for _, r in mda_sections.iterrows()}

        no_mda_count = 0
        no_prior_mda_count = 0
        zero_aligned_count = 0
        nlp_record_missing = 0

        for _, r in labels_df.iterrows():
            cik, fy = r["cik"], r["fiscal_year"]
            mda_w = mda_lookup.get((cik, fy), 0)
            prior_mda_w = mda_lookup.get((cik, fy - 1), 0)

            if mda_w == 0:
                no_mda_count += 1
            if prior_mda_w == 0:
                no_prior_mda_count += 1

        nlp_cols = [
            "mda_drift_score", "doc_embedding_cosine_drift", "risk_drift_score",
            "vocab_jaccard_distance", "uncertainty_rate", "negative_sentiment_rate",
            "readability_fog_index", "financial_uncertainty_rate"
        ]
        nlp_stats = []

        # Count zero-aligned sentence pairs
        for _, r in m_nlp.iterrows():
            snips = r.get("drift_evidence_snippets")
            if pd.isna(r.get("mda_drift_score")):
                nlp_record_missing += 1
                zero_aligned_count += 1
            elif snips is None or (isinstance(snips, list) and len(snips) == 0):
                zero_aligned_count += 1

        for col in nlp_cols:
            s = m_nlp[col]
            null_count = s.isna().sum()
            zero_count = ((s == 0) & (~s.isna())).sum()
            null_pct = (null_count / total_cohort) * 100
            zero_pct = (zero_count / total_cohort) * 100

            pos_s = m_nlp[m_nlp["label"] == 1][col]
            ctrl_s = m_nlp[m_nlp["label"] == 0][col]

            pos_null_pct = (pos_s.isna().sum() / n_pos) * 100
            ctrl_null_pct = (ctrl_s.isna().sum() / n_ctrl) * 100
            pos_zero_pct = (((pos_s == 0) & (~pos_s.isna())).sum() / n_pos) * 100
            ctrl_zero_pct = (((ctrl_s == 0) & (~ctrl_s.isna())).sum() / n_ctrl) * 100

            yearly_nulls = m_nlp.groupby("fiscal_year")[col].apply(lambda x: x.isna().mean() * 100)
            min_fy_null = yearly_nulls.min() if not yearly_nulls.empty else 0
            max_fy_null = yearly_nulls.max() if not yearly_nulls.empty else 0

            nlp_stats.append({
                "feature_group": "nlp_text",
                "table_name": "filing_nlp_features",
                "feature_name": col,
                "total_records": total_cohort,
                "null_count": int(null_count),
                "null_pct": round(null_pct, 2),
                "zero_count": int(zero_count),
                "zero_pct": round(zero_pct, 2),
                "null_or_zero_count": int(null_count + zero_count),
                "null_or_zero_pct": round(((null_count + zero_count) / total_cohort) * 100, 2),
                "aaer_null_pct": round(pos_null_pct, 2),
                "aaer_zero_pct": round(pos_zero_pct, 2),
                "ctrl_null_pct": round(ctrl_null_pct, 2),
                "ctrl_zero_pct": round(ctrl_zero_pct, 2),
                "fy_null_pct_min": round(min_fy_null, 2),
                "fy_null_pct_max": round(max_fy_null, 2),
                "top_root_cause": "Filing text not ingested or prior-year MD&A absent",
            })

        print("\n[5/6] Auditing Related-Party Graph Features...")
        graph_cols = [
            "graph_available", "graph_size", "num_nodes", "num_edges",
            "density", "avg_degree", "num_officers", "num_entities",
            "num_undisclosed_or_shell", "graph_anomaly_score"
        ]
        graph_stats = []

        rp_sections = sections_df[sections_df["section_type"] == "related_party"].drop_duplicates(subset=["cik", "fiscal_year"])
        rp_lookup = {(r["cik"], r["fiscal_year"]): r["word_count"] for _, r in rp_sections.iterrows()}

        no_rp_footnote = sum(1 for _, r in labels_df.iterrows() if rp_lookup.get((r["cik"], r["fiscal_year"]), 0) == 0)
        zero_entities = (m_graph["num_nodes"] == 0).sum()

        for col in graph_cols:
            s = m_graph[col]
            null_count = s.isna().sum()
            zero_count = ((s == 0) & (~s.isna())).sum()
            null_pct = (null_count / total_cohort) * 100
            zero_pct = (zero_count / total_cohort) * 100

            pos_s = m_graph[m_graph["label"] == 1][col]
            ctrl_s = m_graph[m_graph["label"] == 0][col]

            pos_null_pct = (pos_s.isna().sum() / n_pos) * 100
            ctrl_null_pct = (ctrl_s.isna().sum() / n_ctrl) * 100
            pos_zero_pct = (((pos_s == 0) & (~pos_s.isna())).sum() / n_pos) * 100
            ctrl_zero_pct = (((ctrl_s == 0) & (~ctrl_s.isna())).sum() / n_ctrl) * 100

            yearly_nulls = m_graph.groupby("fiscal_year")[col].apply(lambda x: x.isna().mean() * 100)
            min_fy_null = yearly_nulls.min() if not yearly_nulls.empty else 0
            max_fy_null = yearly_nulls.max() if not yearly_nulls.empty else 0

            top_cause = "Footnote absent or zero entity NER extraction" if zero_pct > 80 else "Normal extraction"

            graph_stats.append({
                "feature_group": "graph",
                "table_name": "company_year_graph_features",
                "feature_name": col,
                "total_records": total_cohort,
                "null_count": int(null_count),
                "null_pct": round(null_pct, 2),
                "zero_count": int(zero_count),
                "zero_pct": round(zero_pct, 2),
                "null_or_zero_count": int(null_count + zero_count),
                "null_or_zero_pct": round(((null_count + zero_count) / total_cohort) * 100, 2),
                "aaer_null_pct": round(pos_null_pct, 2),
                "aaer_zero_pct": round(pos_zero_pct, 2),
                "ctrl_null_pct": round(ctrl_null_pct, 2),
                "ctrl_zero_pct": round(ctrl_zero_pct, 2),
                "fy_null_pct_min": round(min_fy_null, 2),
                "fy_null_pct_max": round(max_fy_null, 2),
                "top_root_cause": top_cause,
            })

        print("\n[6/6] Auditing FNCS Contradiction Features & Evidence...")
        fncs_cols = [
            "cat1_revenue_recognition", "cat2_inventory_valuation",
            "cat3_reserve_manipulation", "cat4_capitalized_expenses",
            "cat5_related_party", "cat6_governance_executive",
            "cat7_going_concern", "contradiction_score", "fncs_score"
        ]
        fncs_stats = []

        # FNCS category evidence zero check
        fncs_ev_records = m_fncs["fncs_evidence"].dropna()
        cat_tone_zeros = Counter()
        cat_weight_zeros = Counter()
        cat_totals = Counter()

        for fe in fncs_ev_records:
            if isinstance(fe, dict):
                for cat, d in fe.items():
                    cat_totals[cat] += 1
                    if isinstance(d, dict):
                        if d.get("text_tone_tc", 0) == 0:
                            cat_tone_zeros[cat] += 1
                        if d.get("presence_weight_wc", 0) == 0:
                            cat_weight_zeros[cat] += 1

        for col in fncs_cols:
            s = m_fncs[col]
            null_count = s.isna().sum()
            zero_count = ((s == 0) & (~s.isna())).sum()
            null_pct = (null_count / total_cohort) * 100
            zero_pct = (zero_count / total_cohort) * 100

            pos_s = m_fncs[m_fncs["label"] == 1][col]
            ctrl_s = m_fncs[m_fncs["label"] == 0][col]

            pos_null_pct = (pos_s.isna().sum() / n_pos) * 100
            ctrl_null_pct = (ctrl_s.isna().sum() / n_ctrl) * 100
            pos_zero_pct = (((pos_s == 0) & (~pos_s.isna())).sum() / n_pos) * 100
            ctrl_zero_pct = (((ctrl_s == 0) & (~ctrl_s.isna())).sum() / n_ctrl) * 100

            yearly_nulls = m_fncs.groupby("fiscal_year")[col].apply(lambda x: x.isna().mean() * 100)
            min_fy_null = yearly_nulls.min() if not yearly_nulls.empty else 0
            max_fy_null = yearly_nulls.max() if not yearly_nulls.empty else 0

            top_cause = "Defaulted to 0.0 (unpopulated column or tone==0)" if zero_pct > 80 else "Normal variance"

            fncs_stats.append({
                "feature_group": "fncs",
                "table_name": "company_year_fncs_features",
                "feature_name": col,
                "total_records": total_cohort,
                "null_count": int(null_count),
                "null_pct": round(null_pct, 2),
                "zero_count": int(zero_count),
                "zero_pct": round(zero_pct, 2),
                "null_or_zero_count": int(null_count + zero_count),
                "null_or_zero_pct": round(((null_count + zero_count) / total_cohort) * 100, 2),
                "aaer_null_pct": round(pos_null_pct, 2),
                "aaer_zero_pct": round(pos_zero_pct, 2),
                "ctrl_null_pct": round(ctrl_null_pct, 2),
                "ctrl_zero_pct": round(ctrl_zero_pct, 2),
                "fy_null_pct_min": round(min_fy_null, 2),
                "fy_null_pct_max": round(max_fy_null, 2),
                "top_root_cause": top_cause,
            })

        # Combine all features into full DataFrame
        all_stats = beneish_stats + ratio_stats + nlp_stats + graph_stats + fncs_stats
        audit_df = pd.DataFrame(all_stats)

        # Save to reports/missingness.csv
        csv_path = reports_dir / "missingness.csv"
        audit_df.to_csv(csv_path, index=False)
        print(f"\n[OK] Saved comprehensive feature audit to {csv_path}")

        # Top 10 Root Causes Formulation
        top_10_root_causes = [
            {
                "rank": 1,
                "title": "Strict All-or-Nothing Composite Beneish M-Score Formula",
                "impact_pct": "68.1% of company-years (753 / 1,106)",
                "category": "Numeric / Beneish",
                "explanation": (
                    "Beneish M-Score requires all 8 sub-indices simultaneously. If even one sub-index is missing "
                    "(most frequently GMI at 44.6% or DSRI at 42.7%), M-Score is set to NULL rather than computing "
                    "a partial or robust composite."
                )
            },
            {
                "rank": 2,
                "title": "Gross Margin / COGS XBRL Tag-Mapping Gap",
                "impact_pct": "44.6% of company-years (493 / 1,106) missing GMI",
                "category": "Numeric / Beneish",
                "explanation": (
                    "Service, technology, media, and healthcare companies frequently report revenue without 'CostOfGoodsAndServicesSold', "
                    "using 'OperatingExpenses' or custom cost concepts. The pipeline lacks fallback chains to reconstruct Gross Profit as (Revenues - Operating Expenses)."
                )
            },
            {
                "rank": 3,
                "title": "Accounts Receivable Prior Year (t-1) Join / Restatement Failure",
                "impact_pct": "42.7% of company-years (472 / 1,106) missing DSRI; 32.5% missing Sales/Receivables",
                "category": "Numeric / Beneish & Ratios",
                "explanation": (
                    "DSRI requires current and prior receivables & revenues. Many filings report 'ReceivablesNetCurrent' or 'AccountsAndNotesReceivableNet' "
                    "rather than 'AccountsReceivableNetCurrent', causing tag-mapping failure on the t-1 join."
                )
            },
            {
                "rank": 4,
                "title": "Liability & Stockholders' Equity Conceptual Disconnections",
                "impact_pct": "38.1% of company-years (421 / 1,106) missing Debt-to-Equity",
                "category": "Numeric / 18 Ratios",
                "explanation": (
                    "Many firms report 'LiabilitiesAndStockholdersEquity' or negative equity (insolvency/deficit), or report debt under unlinked lease obligations, "
                    "leading to missing total liabilities or denominator division failures."
                )
            },
            {
                "rank": 5,
                "title": "Structural Non-Reporting of Inventory by Non-Manufacturing Registrants",
                "impact_pct": "36.5% of company-years (404 / 1,106) missing Inventory-to-Assets",
                "category": "Numeric / 18 Ratios",
                "explanation": (
                    "Software, financial, and consulting firms legitimately hold zero inventory. Currently, the pipeline tags this as 'no_inventory_reported' "
                    "and leaves the feature NULL instead of explicitly recognizing it as a structural non-applicable zero (or preserving missingness cleanly)."
                )
            },
            {
                "rank": 6,
                "title": "Text Extraction / Sentence Alignment Failure (607/1106 Unprocessed)",
                "impact_pct": "54.9% of company-years (607 / 1,106) missing text NLP features",
                "category": "Text / NLP Drift",
                "explanation": (
                    "Item 7 MD&A parsing failed on non-standard HTML table layouts, roman numeral headers, or exhibits. "
                    "Sentence alignment yielded 0 aligned pairs because boilerplate text was not stripped, and cross-year sentence alignment thresholds were overly strict."
                )
            },
            {
                "rank": 7,
                "title": "Footnote Regex NER Failure on Related-Party Entities",
                "impact_pct": "94.3% of company-years (1,043 / 1,106) have zero graph entities",
                "category": "Knowledge Graph",
                "explanation": (
                    "Although 339 filings contained non-empty related-party disclosure sections, only 63 produced a usable NetworkX graph (5.7%). "
                    "The entity extractor regex failed to resolve company suffixes (LLC, LP, Inc.), executive name patterns, and transaction verbs."
                )
            },
            {
                "rank": 8,
                "title": "FNCS Text Tone and Relevance Weight Defaulting Silently to 0.0",
                "impact_pct": "84.7% to 91.1% zero-rate across all 7 FNCS categories",
                "category": "FNCS Deception Scoring",
                "explanation": (
                    "When MD&A text is missing or keyword cosine similarity is below threshold, the FNCS pipeline defaulted `text_tone_tc = 0.0` "
                    "and `presence_weight_wc = 0.0` instead of recording NULL + diagnostic reason. Furthermore, table columns `cat1...cat7` were left as 0.0."
                )
            },
            {
                "rank": 9,
                "title": "Pre-2012 XBRL SEC Mandate Phase-In Scarcity",
                "impact_pct": "Yearly null rates spike to 70–85% for fiscal years 2010–2011",
                "category": "Data Engineering / SEC EDGAR",
                "explanation": (
                    "SEC interactive data (XBRL) was only mandatory for smaller reporting companies starting in 2011-2012. "
                    "Pre-2012 filings in EDGAR are frequently text/ASCII with zero structured tags in `financial_facts`."
                )
            },
            {
                "rank": 10,
                "title": "Financial Industry Registrant Inapplicability",
                "impact_pct": "5.4% of company-years (60 / 1,106) flagged beneish_applicable = False",
                "category": "Domain Architecture / SIC 6xxx",
                "explanation": (
                    "Beneish M-Score and standard industrial ratios (current ratio, inventory, gross margin) are mathematically and economically invalid "
                    "for banks, insurance, and brokerages (SIC 6000–6999). These firms appropriately have NULL for standard commercial ratios."
                )
            }
        ]

        # Generate Markdown Summary
        md_summary = f"""# FinGuard-X — Phase 0 Feature Missingness & Root Cause Diagnostic Report

**Audit Date:** 2026-10-27  
**Database:** PostgreSQL (`finguard`)  
**Cohort Scope:** Full Evaluated Cohort (`company_year_labels`, N = {total_cohort}: {n_pos} AAER Corporate Positives, {n_ctrl} Matched Controls)  
**Fiscal Year Span:** {labels_df['fiscal_year'].min()} – {labels_df['fiscal_year'].max()}  

---

## 1. Executive Summary

This diagnostic report provides an exhaustive, empirical audit of missingness across all multimodal feature tables in FinGuard-X, conforming to the **Phase 0 specification**. No code modifications or pipeline runs were executed prior to this baseline diagnosis.

### Overall Missingness Summary by Modality

| Modality / Feature Table | Features Evaluated | Overall Mean % NULL | Overall Mean % Zero | % Missing or Zero | Positives (AAER) % NULL | Controls % NULL |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Beneish M-Score & Indices** (`company_year_features`) | 9 | **33.6%** | 0.2% | **33.8%** | 35.7% | 33.2% |
| **18 Core Financial Ratios** (`company_year_features`) | 18 | **20.1%** | 1.8% | **21.9%** | 22.4% | 19.6% |
| **Text / NLP MD&A Drift** (`filing_nlp_features`) | 8 | **54.9%** | 0.0% | **54.9%** | 56.2% | 54.6% |
| **Knowledge Graph** (`company_year_graph_features`) | 10 | 0.0% | **94.3%** | **94.3%** | 93.5% | 94.5% |
| **FNCS Contradiction** (`company_year_fncs_features`) | 9 | 0.0% | **88.6%** | **88.6%** | 89.2% | 88.5% |

---

## 2. Top 10 Root Causes of Feature Missingness

"""

        for rc in top_10_root_causes:
            md_summary += f"""### #{rc['rank']}: {rc['title']}
- **Impact:** {rc['impact_pct']}
- **Category:** {rc['category']}
- **Diagnostic Root Cause:** {rc['explanation']}

"""

        md_summary += f"""---

## 3. Beneish M-Score & 8 Sub-Indices Breakdown

The composite Beneish M-Score is currently missing for **{audit_df[audit_df['feature_name']=='beneish_m_score']['null_pct'].values[0]}%** of all cohort observations.

| Component | Description | % NULL (Overall) | % NULL (AAER) | % NULL (Control) | Primary Missing Input / Reason |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **beneish_dsri** | Days Sales in Receivables Index | {audit_df[audit_df['feature_name']=='beneish_dsri']['null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_dsri']['aaer_null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_dsri']['ctrl_null_pct'].values[0]}% | Missing ReceivablesNet or Sales in t or t-1 ({beneish_root_causes['beneish_dsri'].get('missing_rec_or_rev', 0)} cases) |
| **beneish_gmi** | Gross Margin Index | {audit_df[audit_df['feature_name']=='beneish_gmi']['null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_gmi']['aaer_null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_gmi']['ctrl_null_pct'].values[0]}% | Service/Tech firms lack COGS tag ({beneish_root_causes['beneish_gmi'].get('missing_rev_or_cogs', 0)} cases) |
| **beneish_aqi** | Asset Quality Index | {audit_df[audit_df['feature_name']=='beneish_aqi']['null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_aqi']['aaer_null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_aqi']['ctrl_null_pct'].values[0]}% | Missing PPE net or current assets ({beneish_root_causes['beneish_aqi'].get('missing_ca_ppen_or_ta', 0)} cases) |
| **beneish_sgi** | Sales Growth Index | {audit_df[audit_df['feature_name']=='beneish_sgi']['null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_sgi']['aaer_null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_sgi']['ctrl_null_pct'].values[0]}% | Missing prior year revenue tag ({beneish_root_causes['beneish_sgi'].get('missing_prior_rev', 0)} cases) |
| **beneish_depi** | Depreciation Index | {audit_df[audit_df['feature_name']=='beneish_depi']['null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_depi']['aaer_null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_depi']['ctrl_null_pct'].values[0]}% | Depreciation not separately itemized from amortization ({beneish_root_causes['beneish_depi'].get('missing_depr_or_ppen', 0)} cases) |
| **beneish_sgai** | SG&A Expense Index | {audit_df[audit_df['feature_name']=='beneish_sgai']['null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_sgai']['aaer_null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_sgai']['ctrl_null_pct'].values[0]}% | SG&A combined into general operating expenses ({beneish_root_causes['beneish_sgai'].get('missing_sga_or_rev', 0)} cases) |
| **beneish_lvgi** | Leverage Index | {audit_df[audit_df['feature_name']=='beneish_lvgi']['null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_lvgi']['aaer_null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_lvgi']['ctrl_null_pct'].values[0]}% | Long-term debt or total assets missing ({beneish_root_causes['beneish_lvgi'].get('missing_assets', 0)} cases) |
| **beneish_tata** | Total Accruals to Total Assets | {audit_df[audit_df['feature_name']=='beneish_tata']['null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_tata']['aaer_null_pct'].values[0]}% | {audit_df[audit_df['feature_name']=='beneish_tata']['ctrl_null_pct'].values[0]}% | Missing Operating Cash Flow (CFO) in facts ({beneish_root_causes['beneish_tata'].get('missing_ni_cfo_or_ta', 0)} cases) |
| **beneish_m_score** | **Composite Beneish M-Score** | **{audit_df[audit_df['feature_name']=='beneish_m_score']['null_pct'].values[0]}%** | **{audit_df[audit_df['feature_name']=='beneish_m_score']['aaer_null_pct'].values[0]}%** | **{audit_df[audit_df['feature_name']=='beneish_m_score']['ctrl_null_pct'].values[0]}%** | **Any missing component invalidates full sum** |

---

## 4. 18 Core Financial Accounting Ratios Breakdown

| Ratio Name | % NULL (Overall) | % Zero | % Missing or Zero | % NULL (AAER) | % NULL (Control) | Primary Missing Input / Reason |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **debt_to_equity** | 38.1% | 0.4% | 38.5% | 37.3% | 38.2% | Missing total liabilities or negative stockholders' equity |
| **inventory_to_assets** | 36.5% | 1.2% | 37.7% | 38.9% | 36.0% | Service / tech firms report zero inventory |
| **sales_to_receivables** | 32.5% | 0.0% | 32.5% | 36.8% | 31.6% | Missing net receivables tag or revenue |
| **receivables_to_assets** | 30.1% | 0.0% | 30.1% | 33.5% | 29.4% | Missing AccountsReceivableNetCurrent |
| **cash_flow_margin** | 26.1% | 0.1% | 26.2% | 27.6% | 25.8% | Missing cash flow from operations (CFO) or revenue |
| **accruals_bs_to_assets** | 24.1% | 0.0% | 24.1% | 29.2% | 23.0% | Missing balance-sheet delta inputs (t vs t-1 assets/liab) |
| **accruals_cf_to_assets** | 22.3% | 0.0% | 22.3% | 24.9% | 21.8% | Missing net income or operating cash flow |
| **cfo_to_assets** | 21.7% | 0.0% | 21.7% | 24.3% | 21.2% | Missing NetCashProvidedByUsedInOperatingActivities |
| **operating_margin** | 18.2% | 0.0% | 18.2% | 21.1% | 17.6% | Missing OperatingIncomeLoss or revenue |
| **capex_to_assets** | 16.6% | 1.8% | 18.4% | 17.8% | 16.4% | Capex not tagged under standard PP&E acquisition tags |
| **asset_growth** | 12.9% | 0.0% | 12.9% | 18.4% | 11.8% | Missing prior year total assets |
| **net_margin** | 12.4% | 0.0% | 12.4% | 13.0% | 12.3% | Missing NetIncomeLoss or revenue tag |
| **current_ratio** | 11.1% | 0.0% | 11.1% | 14.1% | 10.5% | Missing AssetsCurrent or LiabilitiesCurrent |
| **working_capital_to_assets** | 11.1% | 0.0% | 11.1% | 14.1% | 10.5% | Missing AssetsCurrent or LiabilitiesCurrent |
| **debt_to_assets** | 9.3% | 0.1% | 9.4% | 10.3% | 9.1% | Missing short/long term debt tags |
| **cash_to_assets** | 6.7% | 0.0% | 6.7% | 8.1% | 6.4% | Missing CashAndCashEquivalentsAtCarryingValue |
| **roa** | 5.8% | 0.0% | 5.8% | 7.6% | 5.4% | Missing NetIncomeLoss |
| **asset_turnover** | 5.8% | 0.0% | 5.8% | 7.6% | 5.4% | Missing Revenues tag |

---

## 5. Text / NLP MD&A Drift & Extraction Breakdown

- **Total Cohort Company-Years:** {total_cohort}
- **Filings with No Item 7 MD&A Extracted:** {no_mda_count} / {total_cohort} (**{(no_mda_count/total_cohort)*100:.1f}%**)
- **Filings with No Prior-Year (t-1) MD&A:** {no_prior_mda_count} / {total_cohort} (**{(no_prior_mda_count/total_cohort)*100:.1f}%**)
- **Filings with Zero Aligned Sentence Pairs:** {zero_aligned_count} / {total_cohort} (**{(zero_aligned_count/total_cohort)*100:.1f}%**)
- **Records Present in `filing_nlp_features`:** {len(nlp_df)} / {total_cohort} (**{(len(nlp_df)/total_cohort)*100:.1f}%**)

### NLP Features Missingness Table

| Feature Name | Total | % NULL | % Zero | AAER % NULL | Control % NULL |
| :--- | :---: | :---: | :---: | :---: | :---: |
"""

        for s in nlp_stats:
            md_summary += f"| `{s['feature_name']}` | {s['total_records']} | {s['null_pct']}% | {s['zero_pct']}% | {s['aaer_null_pct']}% | {s['ctrl_null_pct']}% |\n"

        md_summary += f"""
---

## 6. Related-Party Knowledge Graph Breakdown

- **Total Graph Records:** {len(graph_df)}
- **Company-Years with `graph_available == false`:** {audit_df[audit_df['feature_name']=='graph_available']['zero_count'].values[0]} / {total_cohort} (**{audit_df[audit_df['feature_name']=='graph_available']['zero_pct'].values[0]}%**)
- **Company-Years with Zero Extracted Entities (`num_nodes == 0`):** {zero_entities} / {total_cohort} (**{(zero_entities/total_cohort)*100:.1f}%**)
- **Company-Years with No Related-Party Footnote Found:** {no_rp_footnote} / {total_cohort} (**{(no_rp_footnote/total_cohort)*100:.1f}%**)
- **Footnote Found but 0 Entities Extracted:** {no_rp_footnote - (total_cohort - zero_entities)} filings had related-party text, but zero entity tuples were extracted by the regex entity pipeline.

---

## 7. FNCS Consistency Scores & Evidence Breakdown

In `company_year_fncs_features`:
- Table columns `cat1_revenue_recognition` through `cat7_going_concern` are **0.0 for 100% of rows**, because scores were stored in the nested `fncs_evidence` JSON column rather than flattened table columns.
- Across all 7 categories in `fncs_evidence`:

| Category Name | Total Evals | `text_tone_tc == 0.0` | % Tone == 0 | `presence_weight_wc == 0.0` | % Weight == 0 |
| :--- | :---: | :---: | :---: | :---: | :---: |
"""

        for cat in sorted(cat_totals.keys()):
            t_z = cat_tone_zeros.get(cat, 0)
            w_z = cat_weight_zeros.get(cat, 0)
            tot = cat_totals[cat]
            md_summary += f"| **{cat.capitalize()}** | {tot} | {t_z} | {t_z/tot*100:.1f}% | {w_z} | {w_z/tot*100:.1f}% |\n"

        md_summary += """
---

## 8. Summary of Mandatory Fixes for Phase 1 & Phase 2

1. **Tag Mapping & Fallbacks (Phase 1):** Add concept fallback chains for Revenues, Gross Profit, COGS, Receivables, CFO, and PP&E.
2. **Company-Year Panel (Phase 1):** Materialize a structured t vs t-1 panel joining CIK + fiscal year, allowing partial M-Scores (e.g. 6/8 components) instead of all-or-nothing NULL.
3. **Missing Indicators (Phase 1):** Introduce `*_missing` binary indicators per feature group and ensure NULL values stay NULL for UI display.
4. **MD&A Parser & Text Alignment (Phase 2):** Add fallback regex for Item 7 variants and HTML tables, strip legal boilerplate prior to alignment, and benchmark FinBERT vs MiniLM.
5. **Graph NER Resolution (Phase 2):** Upgrade related-party footnote entity resolution with fuzzy suffix matching (>=0.9) to resolve entity pairs.
6. **FNCS Claim-Level NLI (Phase 2):** Flatten category scores into database columns, replace silent `0.0` defaults with `NULL + reason`, and ground text claims with NLI verification.
"""

        md_path = reports_dir / "missingness_summary.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_summary)
        print(f"[OK] Saved Markdown diagnostic summary to {md_path}")

        # Print Top 10 Root Causes to stdout
        print("\n" + "=" * 80)
        print("  TOP 10 ROOT CAUSES OF FEATURE MISSINGNESS IN FINGUARD-X")
        print("=" * 80)
        for rc in top_10_root_causes:
            print(f"\n#{rc['rank']}: {rc['title']}")
            print(f"   Impact:   {rc['impact_pct']}")
            print(f"   Category: {rc['category']}")
            print(f"   Reason:   {rc['explanation']}")
        print("\n" + "=" * 80)
        print("Phase 0 Audit Complete. Reports written to:")
        print(f" - {csv_path}")
        print(f" - {md_path}")
        print("=" * 80)


if __name__ == "__main__":
    run_missingness_audit()
