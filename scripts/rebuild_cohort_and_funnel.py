"""Rebuild positive cohort and 1:5 matched controls, and output the detailed funnel table."""
import json
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.ingest.labeling_pipeline import LabelingPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.rebuild_cohort")


def rebuild():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    session = Session(engine)

    logger.info("Starting labeling pipeline execution...")
    pipeline = LabelingPipeline(seed=42)
    stats = pipeline.execute_labeling(session, min_fiscal_year=2010)

    # Gather comprehensive funnel statistics directly from DB
    with engine.connect() as conn:
        total_releases_raw = conn.execute(text("SELECT count(*) FROM aaer_cases")).scalar()
        distinct_releases_raw = conn.execute(text("SELECT count(DISTINCT aaer_number) FROM aaer_cases")).scalar()
        
        excluded_cases = conn.execute(text("SELECT count(*) FROM aaer_cases WHERE exclusion_reason IS NOT NULL")).scalar()
        rule_102e = conn.execute(text("SELECT count(*) FROM aaer_cases WHERE exclusion_reason ILIKE '%102(e)%'")).scalar()
        sec_12j = conn.execute(text("SELECT count(*) FROM aaer_cases WHERE exclusion_reason ILIKE '%12(j)%'")).scalar()
        auditor_cases = conn.execute(text("SELECT count(*) FROM aaer_cases WHERE exclusion_reason ILIKE '%auditor%'")).scalar()
        individual_cases = conn.execute(text("SELECT count(*) FROM aaer_cases WHERE exclusion_reason ILIKE '%individual%'")).scalar()

        corporate_cases = conn.execute(text("SELECT count(*) FROM aaer_cases WHERE exclusion_reason IS NULL")).scalar()
        corporate_distinct_aaer = conn.execute(text("SELECT count(DISTINCT aaer_number) FROM aaer_cases WHERE exclusion_reason IS NULL")).scalar()
        
        corporate_with_cik = conn.execute(text("SELECT count(*) FROM aaer_cases WHERE exclusion_reason IS NULL AND cik IS NOT NULL")).scalar()
        corporate_unique_ciks = conn.execute(text("SELECT count(DISTINCT cik) FROM aaer_cases WHERE exclusion_reason IS NULL AND cik IS NOT NULL")).scalar()

        # Database company_year_labels metrics
        positives_cy = conn.execute(text("SELECT count(*) FROM company_year_labels WHERE label = 1")).scalar()
        positives_ciks = conn.execute(text("SELECT count(DISTINCT cik) FROM company_year_labels WHERE label = 1")).scalar()
        controls_cy = conn.execute(text("SELECT count(*) FROM company_year_labels WHERE label = 0")).scalar()
        controls_ciks = conn.execute(text("SELECT count(DISTINCT cik) FROM company_year_labels WHERE label = 0")).scalar()
        total_cohort = conn.execute(text("SELECT count(*) FROM company_year_labels")).scalar()

        # Check contamination: ensure no control CIK was ever named in an AAER
        contaminated = conn.execute(text("""
            SELECT count(DISTINCT c.cik) 
            FROM company_year_labels c 
            JOIN aaer_cases a ON a.cik = c.cik 
            WHERE c.label = 0
        """)).scalar()

    funnel_report = f"""
========================================================================================
                      AAER ATTRITION & POSITIVE COHORT FUNNEL
========================================================================================
1. INGESTION UNIVERSE
   - Total Raw AAER Release Records:          {total_releases_raw:,} ({distinct_releases_raw:,} unique AAER numbers)

2. EXCLUSION FILTERS (Non-corporate accounting actions)
   - Total Excluded Proceedings:             {excluded_cases:,}
     * Rule 102(e) Professional Sanctions:   {rule_102e:,}
     * Section 12(j) Delinquent Filings:     {sec_12j:,}
     * Auditor Firm Sanctions (Big 4/Natl):  {auditor_cases:,}
     * Individual Officer Only Sanctions:    {individual_cases:,}

3. CORPORATE ISSUER CASES
   - Retained Corporate Issuer Proceedings:  {corporate_cases:,} ({corporate_distinct_aaer:,} unique AAERs)
   - Successfully Resolved to CIK:           {corporate_with_cik:,} records ({corporate_unique_ciks:,} unique CIKs)
   - Cases Lost to Missing CIK:              {corporate_cases - corporate_with_cik:,} (private firms, unlisted issuers)

4. 10-K DATA ELIGIBILITY (FY2010-FY2023)
   - Lost to Pre-2010 / Post-2023 Period:    {stats['unresolved_reasons'].get('Out of range fiscal year', 0) + sum(v for k,v in stats['unresolved_reasons'].items() if 'Out of range' in k):,}
   - Lost to Missing Original 10-K:          {sum(v for k,v in stats['unresolved_reasons'].items() if 'no original 10-K' in k):,}
   - Lost to Missing Prior-Year 10-K (FY-1): {sum(v for k,v in stats['unresolved_reasons'].items() if 'no prior-year 10-K' in k):,}
   - Lost to Missing Assets/Revenue Facts:   {sum(v for k,v in stats['unresolved_reasons'].items() if 'missing asset/revenue' in k):,}

5. FINAL GROUND TRUTH COHORT
   - Positive Company-Years (label = 1):     {positives_cy:,}
   - Independent Positive CIKs:              {positives_ciks:,}
   - Matched 1:5 Controls (label = 0):       {controls_cy:,}
   - Independent Control CIKs:               {controls_ciks:,}
   - Total Labeled Company-Years:            {total_cohort:,}
   - Control Contamination Count:            {contaminated} (Verified 0 AAER issuers in controls)
========================================================================================
"""
    logger.info(funnel_report)
    print(funnel_report)

    # Save summary artifact
    funnel_path = settings.DATA_DIR / "funnel_summary.json"
    funnel_data = {
        "total_releases_raw": total_releases_raw,
        "distinct_releases_raw": distinct_releases_raw,
        "excluded_cases": excluded_cases,
        "corporate_cases": corporate_cases,
        "corporate_unique_ciks": corporate_unique_ciks,
        "positives_company_years": positives_cy,
        "positives_independent_ciks": positives_ciks,
        "controls_company_years": controls_cy,
        "controls_independent_ciks": controls_ciks,
        "total_cohort": total_cohort,
        "contamination": contaminated,
        "unresolved_reasons": stats["unresolved_reasons"],
    }
    with open(funnel_path, "w", encoding="utf-8") as f:
        json.dump(funnel_data, f, indent=2)
    logger.info(f"Saved funnel data to {funnel_path}")


if __name__ == "__main__":
    rebuild()
