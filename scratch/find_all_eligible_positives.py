import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from backend.app.core.config import Settings

def main():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        cases = conn.execute(text("""
            SELECT ac.id, ac.aaer_number, ac.company_name, ac.cik, ac.affected_fiscal_years::text, ac.enforcement_date, ac.source_url
            FROM aaer_cases ac
            WHERE ac.exclusion_reason IS NULL AND ac.cik IS NOT NULL
        """)).fetchall()
        
        filings = set((r[0], r[1]) for r in conn.execute(text("SELECT cik, fiscal_year FROM filings WHERE is_amendment = false")).fetchall())
        facts_assets = set((r[0], r[1]) for r in conn.execute(text("SELECT cik, fiscal_year FROM financial_facts WHERE tag='Assets' AND is_original_filing = true AND value > 0")).fetchall())
        rev_tags = ("Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueGoodsNet", "OperatingRevenue")
        rev_filter = ", ".join(f"'{t}'" for t in rev_tags)
        facts_rev = set((r[0], r[1]) for r in conn.execute(text(f"SELECT cik, fiscal_year FROM financial_facts WHERE tag IN ({rev_filter}) AND is_original_filing = true")).fetchall())
        
        eligible = {}
        for cid, aaer_num, comp_name, cik, years_json, enf_date, url in cases:
            try:
                years = json.loads(years_json)
            except:
                years = []
            if not years or not isinstance(years, list):
                continue
            for y in years:
                if isinstance(y, int) and 2010 <= y <= 2023:
                    has_orig = (cik, y) in filings
                    has_prior = (cik, y - 1) in filings
                    has_facts = (cik, y) in facts_assets and (cik, y) in facts_rev
                    if has_orig and has_prior and has_facts:
                        key = (cik, y)
                        if key not in eligible:
                            eligible[key] = {
                                "cik": cik,
                                "fiscal_year": y,
                                "company_name": comp_name,
                                "aaer_number": aaer_num,
                                "aaer_case_id": cid,
                                "enforcement_date": str(enf_date),
                                "source_url": url,
                            }
                            
        print(f"Total eligible positive company-years found in AAER cases: {len(eligible)}")
        unique_ciks = set(k[0] for k in eligible.keys())
        print(f"Total unique independent positive CIKs: {len(unique_ciks)}")
        print("\nSample 10 eligible positives:")
        for k in list(eligible.keys())[:10]:
            print(" ", eligible[k])

if __name__ == "__main__":
    main()
