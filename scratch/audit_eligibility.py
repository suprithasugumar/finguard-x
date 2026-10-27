import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from backend.app.core.config import Settings

engine = create_engine(Settings().DATABASE_URL)
with engine.connect() as conn:
    filings = set((r[0], r[1]) for r in conn.execute(text('SELECT cik, fiscal_year FROM filings WHERE is_amendment = false')).fetchall())
    facts = set((r[0], r[1]) for r in conn.execute(text("SELECT cik, fiscal_year FROM financial_facts WHERE tag = 'Assets' AND value > 0")).fetchall())
    rev_facts = set((r[0], r[1]) for r in conn.execute(text("SELECT cik, fiscal_year FROM financial_facts WHERE tag IN ('Revenues', 'SalesRevenueNet', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueGoodsNet', 'OperatingRevenue')")).fetchall())
    cases = conn.execute(text('SELECT cik, company_name, affected_fiscal_years FROM aaer_cases WHERE exclusion_reason IS NULL AND cik IS NOT NULL')).fetchall()

eligible_positives = set()
lost_reasons = {}
for cik, cname, fys in cases:
    if isinstance(fys, str):
        fys = json.loads(fys)
    for y in (fys or []):
        if not (2010 <= y <= 2023):
            continue
        k = (cik, y)
        if k not in filings:
            lost_reasons['no_original_10k'] = lost_reasons.get('no_original_10k', 0) + 1
        elif (cik, y - 1) not in filings:
            lost_reasons['no_prior_10k'] = lost_reasons.get('no_prior_10k', 0) + 1
        elif k not in facts:
            lost_reasons['no_assets_fact'] = lost_reasons.get('no_assets_fact', 0) + 1
        elif k not in rev_facts:
            lost_reasons['no_revenue_fact'] = lost_reasons.get('no_revenue_fact', 0) + 1
        else:
            eligible_positives.add((cik, y))

unique_ciks = set(p[0] for p in eligible_positives)
print(f"Eligible positive company-years: {len(eligible_positives)}")
print(f"Eligible independent positive CIKs: {len(unique_ciks)}")
print(f"Lost reasons breakdown: {lost_reasons}")
