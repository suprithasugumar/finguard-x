"""Audit the complete AAER funnel from releases to final eligible positives."""
import json
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from backend.app.core.config import Settings

def main():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        total_cases = conn.execute(text("SELECT count(*) FROM aaer_cases")).scalar()
        unique_releases = conn.execute(text("SELECT count(DISTINCT aaer_number) FROM aaer_cases")).scalar()
        
        # Reasons for exclusion
        exclusions = conn.execute(text("SELECT exclusion_reason, count(*) FROM aaer_cases WHERE exclusion_reason IS NOT NULL GROUP BY exclusion_reason")).fetchall()
        
        corporate_cases = conn.execute(text("SELECT count(*) FROM aaer_cases WHERE exclusion_reason IS NULL")).scalar()
        corporate_unique_releases = conn.execute(text("SELECT count(DISTINCT aaer_number) FROM aaer_cases WHERE exclusion_reason IS NULL")).scalar()
        
        matched_cases = conn.execute(text("SELECT count(*) FROM aaer_cases WHERE exclusion_reason IS NULL AND cik IS NOT NULL")).scalar()
        matched_unique_releases = conn.execute(text("SELECT count(DISTINCT aaer_number) FROM aaer_cases WHERE exclusion_reason IS NULL AND cik IS NOT NULL")).scalar()
        matched_unique_ciks = conn.execute(text("SELECT count(DISTINCT cik) FROM aaer_cases WHERE exclusion_reason IS NULL AND cik IS NOT NULL")).scalar()
        
        # Fetch all matched cases to check years
        cases = conn.execute(text("SELECT id, aaer_number, company_name, cik, affected_fiscal_years FROM aaer_cases WHERE exclusion_reason IS NULL AND cik IS NOT NULL")).fetchall()
        
        ciks_with_years = set()
        cik_fy_pairs = set()
        cases_with_fy = 0
        for cid, num, name, cik, years in cases:
            if years and isinstance(years, list) and len(years) > 0:
                cases_with_fy += 1
                for y in years:
                    if isinstance(y, int) and 2010 <= y <= 2023:
                        ciks_with_years.add(cik)
                        cik_fy_pairs.add((cik, y))
                        
        # Check against database filings and facts
        filings = set((r[0], r[1]) for r in conn.execute(text("SELECT cik, fiscal_year FROM filings WHERE is_amendment = false")).fetchall())
        facts_assets = set((r[0], r[1]) for r in conn.execute(text("SELECT cik, fiscal_year FROM financial_facts WHERE tag='Assets' AND is_original_filing = true AND value > 0")).fetchall())
        
        rev_tags = ("Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueGoodsNet", "OperatingRevenue")
        rev_filter = ", ".join(f"'{t}'" for t in rev_tags)
        facts_rev = set((r[0], r[1]) for r in conn.execute(text(f"SELECT cik, fiscal_year FROM financial_facts WHERE tag IN ({rev_filter}) AND is_original_filing = true")).fetchall())
        
        eligible_positives = set()
        eligible_ciks = set()
        lost_no_orig_10k = 0
        lost_no_prior_10k = 0
        lost_no_facts = 0
        
        for cik, fy in cik_fy_pairs:
            has_orig = (cik, fy) in filings
            has_prior = (cik, fy - 1) in filings
            has_data = (cik, fy) in facts_assets and (cik, fy) in facts_rev
            
            if has_orig and has_prior and has_data:
                eligible_positives.add((cik, fy))
                eligible_ciks.add(cik)
            else:
                if not has_orig:
                    lost_no_orig_10k += 1
                elif not has_prior:
                    lost_no_prior_10k += 1
                else:
                    lost_no_facts += 1

    print("=== COMPLETE AAER FUNNEL AUDIT ===")
    print(f"1. Total ingested release records in DB: {total_cases} (Distinct AAER numbers: {unique_releases})")
    print(f"2. Excluded proceedings: {total_cases - corporate_cases}")
    for reason, count in exclusions:
        print(f"   - {reason}: {count}")
    print(f"3. Corporate issuer cases remaining: {corporate_cases} (Distinct releases: {corporate_unique_releases})")
    print(f"4. Name-to-CIK successfully matched: {matched_cases} cases (Distinct releases: {matched_unique_releases}, Unique CIKs: {matched_unique_ciks})")
    print(f"5. Cases with non-empty affected FY: {cases_with_fy}")
    print(f"   - FY2010-2023 candidate company-years: {len(cik_fy_pairs)} across {len(ciks_with_years)} unique CIKs")
    print(f"6. Eligible in DB (Orig 10-K + Prior 10-K + Positive Assets + Revenue): {len(eligible_positives)} company-years across {len(eligible_ciks)} unique CIKs")
    print(f"   - Lost: no original 10-K in DB: {lost_no_orig_10k}")
    print(f"   - Lost: no prior-year 10-K in DB: {lost_no_prior_10k}")
    print(f"   - Lost: missing revenue/assets facts: {lost_no_facts}")

if __name__ == "__main__":
    main()
