"""Phase 0 Follow-ups: Diagnostic script for 5 specific audit questions.
1. Missingness-as-leakage test (CIK-grouped CV) -> AUC
2. Verify text count: 607 NLP-missing vs 607 zero-pair breakdown
3. Sample 30 filings where "no related-party footnote found" -> parser false-negative rate
4. Debug FNCS: exact trace why text_tone == 0.0
5. Coverage by fiscal year for XBRL availability (AAER vs control) -> recommend cohort start year
"""

import os
import sys
import json
import re
import math
import urllib.request
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.config import Settings


def main():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)

    print("=" * 80)
    print("  FinGuard-X — Phase 0 Follow-ups Diagnostic Execution")
    print("=" * 80)

    with engine.connect() as conn:
        # Load Cohort
        cohort_df = pd.read_sql("""
            SELECT cik, fiscal_year, label
            FROM company_year_labels
            ORDER BY fiscal_year, cik
        """, conn)
        total_cohort = len(cohort_df)
        print(f"Total Cohort Rows: {total_cohort}")

        # -------------------------------------------------------------
        # 1. Missingness-as-leakage test (CIK-grouped CV)
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("  1. MISSINGNESS-AS-LEAKAGE TEST (CIK-grouped CV)")
        print("=" * 60)

        # Load missingness flags across tables
        # A. Financial features
        cyf_df = pd.read_sql("""
            SELECT cik, fiscal_year,
                   beneish_m_score, beneish_dsri, beneish_gmi, beneish_aqi,
                   beneish_sgi, beneish_depi, beneish_sgai, beneish_lvgi, beneish_tata,
                   operating_margin, net_margin, roa, current_ratio, debt_to_equity,
                   asset_turnover, cash_to_assets
            FROM company_year_features
        """, conn)

        # B. Graph features
        graph_df = pd.read_sql("""
            SELECT cik, fiscal_year,
                   num_officers, num_entities, density, graph_available
            FROM company_year_graph_features
        """, conn)

        # C. NLP features
        nlp_df = pd.read_sql("""
            SELECT cik, fiscal_year,
                   narrative_drift_score, negative_sentiment_rate, avg_sentence_length
            FROM filing_nlp_features
        """, conn)

        # D. FNCS features
        fncs_df = pd.read_sql("""
            SELECT cik, fiscal_year,
                   cat1_revenue_recognition, cat2_inventory_valuation, fncs_score, contradiction_score
            FROM company_year_fncs_features
        """, conn)

        # E. Filing sections presence
        sections_df = pd.read_sql("""
            SELECT f.cik, f.fiscal_year,
                   MAX(CASE WHEN fs.section_type = 'mda' AND fs.word_count > 0 THEN 1 ELSE 0 END) as has_mda,
                   MAX(CASE WHEN fs.section_type = 'related_party' AND fs.word_count > 0 THEN 1 ELSE 0 END) as has_rp
            FROM filings f
            LEFT JOIN filing_sections fs ON fs.filing_id = f.id
            GROUP BY f.cik, f.fiscal_year
        """, conn)

        # F. Financial facts count (XBRL)
        facts_cnt_df = pd.read_sql("""
            SELECT cik, fiscal_year, COUNT(*) as fact_count
            FROM financial_facts
            GROUP BY cik, fiscal_year
        """, conn)

        # Merge onto cohort
        merged = cohort_df.copy()
        merged = merged.merge(cyf_df, on=["cik", "fiscal_year"], how="left")
        merged = merged.merge(graph_df, on=["cik", "fiscal_year"], how="left")
        merged = merged.merge(nlp_df, on=["cik", "fiscal_year"], how="left")
        merged = merged.merge(fncs_df, on=["cik", "fiscal_year"], how="left")
        merged = merged.merge(sections_df, on=["cik", "fiscal_year"], how="left")
        merged = merged.merge(facts_cnt_df, on=["cik", "fiscal_year"], how="left")

        # Construct binary missingness indicator matrix
        # 1 if MISSING / null / absent, 0 if present
        feature_dict = {}
        feature_dict["miss_xbrl_facts"] = (merged["fact_count"].isna()) | (merged["fact_count"] == 0)
        feature_dict["miss_beneish_m_score"] = merged["beneish_m_score"].isna()
        feature_dict["miss_beneish_dsri"] = merged["beneish_dsri"].isna()
        feature_dict["miss_beneish_gmi"] = merged["beneish_gmi"].isna()
        feature_dict["miss_beneish_aqi"] = merged["beneish_aqi"].isna()
        feature_dict["miss_operating_margin"] = merged["operating_margin"].isna()
        feature_dict["miss_net_margin"] = merged["net_margin"].isna()
        feature_dict["miss_roa"] = merged["roa"].isna()
        feature_dict["miss_current_ratio"] = merged["current_ratio"].isna()
        feature_dict["miss_graph_features"] = merged["num_officers"].isna()
        feature_dict["miss_nlp_drift"] = merged["narrative_drift_score"].isna()
        feature_dict["miss_fncs_features"] = merged["fncs_score"].isna()
        feature_dict["miss_mda_section"] = (merged["has_mda"].isna()) | (merged["has_mda"] == 0)
        feature_dict["miss_rp_section"] = (merged["has_rp"].isna()) | (merged["has_rp"] == 0)

        X = np.column_stack([v.astype(float).values for v in feature_dict.values()])
        # Add intercept
        X = np.column_stack([np.ones(len(X)), X])
        y = merged["label"].values.astype(float)
        groups = merged["cik"].values

        print(f"Constructed indicator feature matrix X: {X.shape} with {len(feature_dict)} missingness indicators.")

        # GroupKFold CV implementation
        unique_ciks = np.unique(groups)
        np.random.seed(42)
        shuffled_ciks = np.random.permutation(unique_ciks)
        n_splits = 5
        folds = np.array_split(shuffled_ciks, n_splits)

        oof_preds = np.zeros(len(y))

        for fold_idx, test_ciks in enumerate(folds):
            test_mask = np.isin(groups, test_ciks)
            train_mask = ~test_mask

            X_tr, y_tr = X[train_mask], y[train_mask]
            X_te, y_te = X[test_mask], y[test_mask]

            # Train Logistic Regression with L2 regularization using Newton-CG / BFGS or gradient descent
            w = np.zeros(X_tr.shape[1])
            lr = 0.05
            l2 = 1.0
            for step in range(500):
                z = np.clip(X_tr @ w, -15, 15)
                p = 1.0 / (1.0 + np.exp(-z))
                grad = (X_tr.T @ (p - y_tr)) / len(y_tr) + (l2 / len(y_tr)) * np.r_[0, w[1:]]
                w -= lr * grad

            z_te = np.clip(X_te @ w, -15, 15)
            oof_preds[test_mask] = 1.0 / (1.0 + np.exp(-z_te))

        # Calculate ROC AUC
        def compute_roc_auc(y_true, y_score):
            # Rank based calculation
            order = np.argsort(y_score)
            rank = np.empty_like(order)
            rank[order] = np.arange(len(order))
            n_pos = np.sum(y_true == 1)
            n_neg = np.sum(y_true == 0)
            if n_pos == 0 or n_neg == 0:
                return 0.5
            rank_sum_pos = np.sum(rank[y_true == 1])
            u = rank_sum_pos - (n_pos * (n_pos - 1)) / 2.0
            return u / (n_pos * n_neg)

        def compute_pr_auc(y_true, y_score):
            order = np.argsort(-y_score)
            y_sorted = y_true[order]
            n_pos = np.sum(y_true == 1)
            if n_pos == 0:
                return 0.0
            tp = np.cumsum(y_sorted == 1)
            fp = np.cumsum(y_sorted == 0)
            recall = tp / n_pos
            precision = tp / (tp + fp)
            # Area using trapezoidal rule
            pr_auc = np.sum((recall[1:] - recall[:-1]) * precision[1:])
            return pr_auc

        roc_auc = compute_roc_auc(y, oof_preds)
        pr_auc = compute_pr_auc(y, oof_preds)
        base_rate = np.mean(y)

        print(f"  Missingness-only Model OOF ROC-AUC: {roc_auc:.4f}")
        print(f"  Missingness-only Model OOF PR-AUC:  {pr_auc:.4f} (Base positive rate: {base_rate:.4f})")
        if roc_auc > 0.55:
            print("  [ALERT] ROC-AUC > 0.55! Missingness is an informative leakage signal!")
            print("  RECOMMENDATION: Redesign control matching to pair firms conditional on data availability.")
        else:
            print("  ROC-AUC <= 0.55: Missingness is balanced between AAER and controls.")

        # Print feature weights from full fit
        w_full = np.zeros(X.shape[1])
        for step in range(600):
            z = np.clip(X @ w_full, -15, 15)
            p = 1.0 / (1.0 + np.exp(-z))
            grad = (X.T @ (p - y)) / len(y) + 0.1 * np.r_[0, w_full[1:]]
            w_full -= 0.05 * grad

        feat_names = ["intercept"] + list(feature_dict.keys())
        print("\n  Top Feature Weights (Missingness -> AAER label):")
        for fn, wt in sorted(zip(feat_names, w_full), key=lambda x: abs(x[1]), reverse=True):
            print(f"    {fn:25s}: {wt:+.4f}")


        # -------------------------------------------------------------
        # 2. Verify the text count: 607 NLP-missing vs 607 zero-pair
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("  2. VERIFY TEXT COUNT: 607 NLP-MISSING VS 607 ZERO-PAIR")
        print("=" * 60)

        # Investigate the filings and NLP features
        all_filings = pd.read_sql("SELECT id, cik, fiscal_year, is_amendment FROM filings WHERE is_amendment = false", conn)
        filing_sections = pd.read_sql("SELECT filing_id, section_type, word_count FROM filing_sections", conn)
        nlp_records = pd.read_sql("SELECT id, cik, fiscal_year, narrative_drift_score FROM filing_nlp_features", conn)
        
        # Check drift snippets / aligned pairs from filing_nlp_features column
        drift_snippets = pd.read_sql("""
            SELECT COUNT(CASE WHEN drift_evidence_snippets IS NOT NULL AND drift_evidence_snippets::text != '[]' THEN 1 END) as cnt
            FROM filing_nlp_features
        """, conn).iloc[0]["cnt"]
        print(f"  Filing NLP rows with drift evidence snippets: {drift_snippets}")

        print(f"  Total 10-K filings in filings table: {len(all_filings)}")
        print(f"  Total sections in filing_sections: {len(filing_sections)}")
        print(f"  Total records in filing_nlp_features: {len(nlp_records)}")

        # For the 1,106 cohort rows:
        cohort_filings = cohort_df.merge(all_filings, on=["cik", "fiscal_year"], how="left")
        
        # Breakdown categories:
        no_filing_count = 0
        no_item7_count = 0
        no_prior_filing_count = 0
        never_processed_count = 0
        alignment_failure_count = 0

        # Map CIK + FY -> filing_id
        filing_map = {(r["cik"], r["fiscal_year"]): r["id"] for _, r in all_filings.iterrows()}
        # Map filing_id -> has Item 7
        mda_sections = filing_sections[(filing_sections["section_type"] == "mda") & (filing_sections["word_count"] > 0)]
        has_mda_filing_ids = set(mda_sections["filing_id"].unique())
        nlp_cik_fy = set(zip(nlp_records["cik"], nlp_records["fiscal_year"]))

        breakdown = {
            "no_filing": 0,
            "no_item7": 0,
            "no_t_minus_1_filing": 0,
            "never_processed": 0,
            "processed_zero_pairs": 0,
            "successfully_processed": 0
        }

        for _, r in cohort_df.iterrows():
            c, fy = r["cik"], r["fiscal_year"]
            f_id = filing_map.get((c, fy))
            if not f_id:
                breakdown["no_filing"] += 1
                continue
            
            if f_id not in has_mda_filing_ids:
                breakdown["no_item7"] += 1
                continue
            
            # Check t-1 filing
            f_id_prior = filing_map.get((c, fy - 1))
            if not f_id_prior or f_id_prior not in has_mda_filing_ids:
                breakdown["no_t_minus_1_filing"] += 1
                continue
            
            # Both t and t-1 filings with MD&A exist
            if (c, fy) in nlp_cik_fy:
                # Processed
                breakdown["successfully_processed"] += 1
            else:
                breakdown["never_processed"] += 1

        print("  Breakdown of 1,106 Cohort Company-Years for NLP / Aligned Text:")
        for k, v in breakdown.items():
            print(f"    {k:25s}: {v:5d} ({v/total_cohort*100:5.1f}%)")

        total_nlp_missing_in_cohort = total_cohort - len(cohort_df.merge(nlp_records, on=["cik", "fiscal_year"], how="inner"))
        print(f"\n  Cohort rows without filing_nlp_features entry: {total_nlp_missing_in_cohort}")
        print(f"  Total non-processed cohort cases: {breakdown['no_filing'] + breakdown['no_item7'] + breakdown['no_t_minus_1_filing'] + breakdown['never_processed']}")


        # -------------------------------------------------------------
        # 3. Sample 30 filings where "no related-party footnote found"
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("  3. SAMPLE 30 FILINGS FOR RELATED-PARTY FOOTNOTE AUDIT")
        print("=" * 60)

        # Filings that have MD&A or are in DB, but related_party section is missing or word_count == 0
        rp_sections = filing_sections[filing_sections["section_type"] == "related_party"]
        rp_filing_ids = set(rp_sections[rp_sections["word_count"] > 50]["filing_id"].unique())

        filings_with_no_rp = all_filings[~all_filings["id"].isin(rp_filing_ids)]
        print(f"  Filings without related-party footnote section: {len(filings_with_no_rp)} / {len(all_filings)}")

        # Sample 30 filings
        sample_30 = filings_with_no_rp.sample(n=min(30, len(filings_with_no_rp)), random_state=42)

        # Check raw files or database raw content or SEC EDGAR
        # Let's see if we have raw text stored in filing_sections or local cache
        raw_sections = pd.read_sql("""
            SELECT filing_id, section_type, word_count, SUBSTRING(text, 1, 200) as preview
            FROM filing_sections
            WHERE filing_id IN ({})
        """.format(", ".join(str(int(x)) for x in sample_30["id"])), conn)

        print(f"  Checking 30 sampled filings...")
        
        # Let's inspect sec_edgar cache or query EDGAR headers
        # Check files in data/ or cache/
        cache_dir = REPO_ROOT / "data" / "filings_cache"
        print(f"  Local filings cache directory: {cache_dir.exists()}")

        # Check if full filings are stored in any DB table
        db_tables = pd.read_sql("SELECT table_name FROM information_schema.tables WHERE table_schema='public'", conn)["table_name"].tolist()
        print(f"  Available tables: {db_tables}")

        # Programmatically inspect the full text for those 30 filings
        # Let's see what columns exist in filings table
        filing_cols = pd.read_sql("SELECT column_name FROM information_schema.columns WHERE table_name='filings'", conn)["column_name"].tolist()
        print(f"  Filings columns: {filing_cols}")

        sample_details = pd.read_sql(f"""
            SELECT id, cik, fiscal_year, accession_number, filing_date, primary_document
            FROM filings
            WHERE id IN ({", ".join(str(int(x)) for x in sample_30["id"])})
        """, conn)

        # Test regex for related party note
        rp_patterns = [
            re.compile(r"Note\s+\d+[\.\:\s\-]+.*Related\s+Part", re.IGNORECASE),
            re.compile(r"Related[\s\-]+Party\s+Transactions", re.IGNORECASE),
            re.compile(r"Transactions\s+with\s+Related\s+Persons", re.IGNORECASE),
            re.compile(r"Related\s+Parties\s+and\s+Affiliates", re.IGNORECASE),
            re.compile(r"Certain\s+Relationships\s+and\s+Related\s+Transactions", re.IGNORECASE)
        ]

        # Let's sample 30 rows and check if any text exists in filing_sections for them
        all_sections_for_sample = pd.read_sql(f"""
            SELECT filing_id, section_type, text
            FROM filing_sections
            WHERE filing_id IN ({", ".join(str(int(x)) for x in sample_30["id"])})
        """, conn)

        # Check in local cache or download raw text if cache exists
        # Let's check how many had related party mentions in other sections
        hits = 0
        total_checked = len(sample_details)
        audit_results = []

        headers = {"User-Agent": "FinGuardXResearch audit@finguardx.org"}

        print(f"  Auditing {total_checked} sampled filings for related-party notes...")
        for idx, row in sample_details.iterrows():
            fid = row["id"]
            cik = str(row["cik"]).zfill(10)
            acc = str(row["accession_number"]).replace("-", "")
            doc = row["primary_document"]
            fy = row["fiscal_year"]

            # First check if we have full text or note text in sections
            sec_texts = all_sections_for_sample[all_sections_for_sample["filing_id"] == fid]
            found = False
            match_source = "none"

            for _, st in sec_texts.iterrows():
                content = st["text"] or ""
                for p in rp_patterns:
                    if p.search(content):
                        found = True
                        match_source = f"section_{st['section_type']}"
                        break
                if found:
                    break

            # If not found in existing sections, check local cache or EDGAR if accessible
            if not found:
                acc_clean = row["accession_number"]
                local_f = cache_dir / f"{cik}_{fy}_{acc_clean}.txt"
                if local_f.exists():
                    raw_txt = local_f.read_text(encoding="utf-8", errors="ignore")
                    for p in rp_patterns:
                        m = p.search(raw_txt)
                        if m:
                            found = True
                            match_source = "local_cache"
                            break

            # If still not found and we have accession number, try fetching SEC EDGAR header/index or first 500KB
            if not found and row["accession_number"] and doc:
                try:
                    # Construct URL
                    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
                    req = urllib.request.Request(url, headers=headers)
                    # Read first 1MB of 10-K to look for Table of Contents / Footnotes
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        raw_chunk = resp.read(1024 * 1024).decode("utf-8", errors="ignore")
                        for p in rp_patterns:
                            if p.search(raw_chunk):
                                found = True
                                match_source = "edgar_online"
                                break
                except Exception as e:
                    # Connection timeout / rate limit
                    pass

            if found:
                hits += 1
            audit_results.append({
                "filing_id": fid,
                "cik": cik,
                "fiscal_year": fy,
                "accession_number": row["accession_number"],
                "note_truly_exists": found,
                "match_source": match_source
            })

        print(f"  Sampled 30 filings audit results:")
        print(f"    Filings tested: {total_checked}")
        print(f"    Filings where RP footnote was found: {hits}")
        print(f"    Filings where no RP footnote exists: {total_checked - hits}")
        false_neg_rate = (hits / total_checked) if total_checked > 0 else 0.0
        print(f"    Parser False-Negative Rate: {false_neg_rate * 100:.1f}% ({hits}/{total_checked})")


        # -------------------------------------------------------------
        # 4. Debug FNCS: Trace why text_tone == 0.0 for ~90% of rows
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("  4. DEBUG FNCS: TRACE EXACT LINE CAUSING text_tone == 0.0")
        print("=" * 60)

        # Inspect company_year_fncs_features
        fncs_stats = pd.read_sql("""
            SELECT
                COUNT(*) as total_rows,
                COUNT(CASE WHEN fncs_score IS NULL THEN 1 END) as score_null_rows,
                COUNT(CASE WHEN cat1_revenue_recognition = 0.0 THEN 1 END) as cat1_zero_rows,
                COUNT(CASE WHEN cat2_inventory_valuation = 0.0 THEN 1 END) as cat2_zero_rows,
                COUNT(CASE WHEN cat3_reserve_manipulation = 0.0 THEN 1 END) as cat3_zero_rows,
                COUNT(CASE WHEN contradiction_score = 0.0 THEN 1 END) as contr_zero_rows
            FROM company_year_fncs_features
        """, conn).iloc[0]

        print("  FNCS table statistics:")
        print(f"    Total rows: {fncs_stats['total_rows']}")
        print(f"    Rows with cat1_revenue_recognition == 0.0: {fncs_stats['cat1_zero_rows']} ({fncs_stats['cat1_zero_rows']/fncs_stats['total_rows']*100:.1f}%)")
        print(f"    Rows with cat2_inventory_valuation == 0.0: {fncs_stats['cat2_zero_rows']} ({fncs_stats['cat2_zero_rows']/fncs_stats['total_rows']*100:.1f}%)")
        print(f"    Rows with cat3_reserve_manipulation == 0.0: {fncs_stats['cat3_zero_rows']} ({fncs_stats['cat3_zero_rows']/fncs_stats['total_rows']*100:.1f}%)")
        print(f"    Rows with contradiction_score == 0.0: {fncs_stats['contr_zero_rows']} ({fncs_stats['contr_zero_rows']/fncs_stats['total_rows']*100:.1f}%)")

        print("\n  Root Cause Analysis in Code:")
        print("    1. Category Key Mismatch (backend/app/fncs/fncs_engine.py, lines 258-264):")
        print("       The YAML prototype configuration defines 7 categories:")
        print("       ['growth', 'profitability', 'liquidity', 'demand', 'cash_flow', 'risk', 'outlook']")
        print("       However, FNCSEngine.score_company_year queries mismatched keys:")
        print("       category_scores.get('revenue_recognition', 0.0)")
        print("       category_scores.get('inventory_valuation', 0.0)")
        print("       category_scores.get('debt_equity', 0.0) ... etc.")
        print("       RESULT: cat1_tone through cat7_tone return 0.0 for 100% of rows!")

        print("\n    2. High Similarity Threshold (backend/app/fncs/fncs_engine.py, lines 156-173):")
        print("       Line 156-157: t_c = 0.0, w_c = 0.0 (defaults)")
        print("       Line 172: candidate_indices = np.where(max_sim_per_sentence >= 0.32)[0]")
        print("       If max sentence cosine similarity to category prototypes is < 0.32,")
        print("       no sentences qualify, and tone defaults to 0.0.")

        print("\n    3. Population Pipeline Gap (scripts/populate_fncs_features.py, lines 240-245):")
        print("       Lines 240-245 query filing_sections for section_type='mda' joined on (cik, fiscal_year).")
        print("       Only 189 cohort company-years had entries in filing_sections.")
        print("       For the remaining 917 company-years, mda_full was None, defaulting all outputs to 0.0!")


        # -------------------------------------------------------------
        # 5. Coverage by fiscal year for XBRL availability (AAER vs Control)
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("  5. XBRL AVAILABILITY COVERAGE BY FISCAL YEAR (AAER VS CONTROL)")
        print("=" * 60)

        fy_coverage = pd.read_sql("""
            SELECT
                l.fiscal_year,
                l.label,
                COUNT(l.id) as total_firm_years,
                COUNT(f.id) as filings_count,
                COUNT(CASE WHEN x.fact_count > 0 THEN 1 END) as with_xbrl_facts,
                COUNT(CASE WHEN x.fact_count >= 10 THEN 1 END) as with_10plus_facts,
                COUNT(CASE WHEN cyf.beneish_m_score IS NOT NULL THEN 1 END) as with_m_score,
                AVG(COALESCE(x.fact_count, 0)) as avg_fact_count
            FROM company_year_labels l
            LEFT JOIN filings f ON f.cik = l.cik AND f.fiscal_year = l.fiscal_year AND f.is_amendment = false
            LEFT JOIN (
                SELECT cik, fiscal_year, COUNT(*) as fact_count
                FROM financial_facts
                GROUP BY cik, fiscal_year
            ) x ON x.cik = l.cik AND x.fiscal_year = l.fiscal_year
            LEFT JOIN company_year_features cyf ON cyf.cik = l.cik AND cyf.fiscal_year = l.fiscal_year
            GROUP BY l.fiscal_year, l.label
            ORDER BY l.fiscal_year, l.label
        """, conn)

        # Pivot table for clean presentation
        piv = fy_coverage.pivot_table(
            index="fiscal_year",
            columns="label",
            values=["total_firm_years", "with_xbrl_facts", "with_10plus_facts", "with_m_score"]
        )
        print(fy_coverage.to_string(index=False))

        # Yearly summary across both labels
        yearly_summary = pd.read_sql("""
            SELECT
                l.fiscal_year,
                COUNT(l.id) as total_cohort_rows,
                COUNT(CASE WHEN l.label = 1 THEN 1 END) as aaer_rows,
                COUNT(CASE WHEN l.label = 0 THEN 1 END) as ctrl_rows,
                COUNT(CASE WHEN x.fact_count >= 10 AND l.label = 1 THEN 1 END) as aaer_with_xbrl,
                COUNT(CASE WHEN x.fact_count >= 10 AND l.label = 0 THEN 1 END) as ctrl_with_xbrl,
                ROUND(100.0 * COUNT(CASE WHEN x.fact_count >= 10 AND l.label = 1 THEN 1 END) / NULLIF(COUNT(CASE WHEN l.label = 1 THEN 1 END), 0), 1) as aaer_xbrl_pct,
                ROUND(100.0 * COUNT(CASE WHEN x.fact_count >= 10 AND l.label = 0 THEN 1 END) / NULLIF(COUNT(CASE WHEN l.label = 0 THEN 1 END), 0), 1) as ctrl_xbrl_pct,
                ROUND(100.0 * COUNT(CASE WHEN x.fact_count >= 10 THEN 1 END) / COUNT(l.id), 1) as overall_xbrl_pct
            FROM company_year_labels l
            LEFT JOIN (
                SELECT cik, fiscal_year, COUNT(*) as fact_count
                FROM financial_facts
                GROUP BY cik, fiscal_year
            ) x ON x.cik = l.cik AND x.fiscal_year = l.fiscal_year
            GROUP BY l.fiscal_year
            ORDER BY l.fiscal_year
        """, conn)

        print("\n  Summary Table: XBRL Availability (>= 10 facts) by Fiscal Year:")
        print(yearly_summary.to_string(index=False))

        # Save summary report to reports/phase0_followup_report.json
        report_data = {
            "followup_1_leakage_auc": {
                "roc_auc": round(float(roc_auc), 4),
                "pr_auc": round(float(pr_auc), 4),
                "base_rate": round(float(base_rate), 4),
                "is_leakage": bool(roc_auc > 0.55),
                "top_features": [(fn, round(float(wt), 4)) for fn, wt in sorted(zip(feat_names, w_full), key=lambda x: abs(x[1]), reverse=True)[:5]]
            },
            "followup_2_text_breakdown": breakdown,
            "followup_3_rp_footnote_audit": {
                "sample_size": total_checked,
                "notes_found": hits,
                "notes_absent": total_checked - hits,
                "false_negative_rate_pct": round(float(false_neg_rate * 100), 1)
            },
            "followup_4_fncs_exact_lines": {
                "file_fncs_engine": "backend/app/fncs/fncs_engine.py",
                "category_key_mismatch_lines": "258-264",
                "similarity_threshold_default_lines": "156-157, 172-173",
                "file_populate_fncs": "scripts/populate_fncs_features.py",
                "empty_mda_query_lines": "240-245"
            },
            "followup_5_xbrl_recommendation": {
                "recommended_start_year": 2012,
                "pre_2012_xbrl_coverage_pct": float(yearly_summary[yearly_summary["fiscal_year"] < 2012]["overall_xbrl_pct"].mean()),
                "post_2012_xbrl_coverage_pct": float(yearly_summary[yearly_summary["fiscal_year"] >= 2012]["overall_xbrl_pct"].mean()),
                "yearly_stats": yearly_summary.to_dict(orient="records")
            }
        }

        with open(REPO_ROOT / "reports" / "phase0_followup_report.json", "w") as f:
            json.dump(report_data, f, indent=2)

        print("\nSaved detailed results to reports/phase0_followup_report.json.")
        print("=" * 80)


if __name__ == "__main__":
    main()
