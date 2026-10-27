import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json
from sqlalchemy import create_engine, text
from backend.app.core.config import Settings

engine = create_engine(Settings().DATABASE_URL)
with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT cye.cik, c.name, cye.fiscal_year, cye.risk_score, cye.fncs_evidence
        FROM company_year_explanations cye
        JOIN companies c ON c.cik = cye.cik
    """)).fetchall()
    for r in rows:
        ev = r[4] or {}
        g = ev.get('growth', {}).get('numeric_signal_nc', 0)
        p = ev.get('profitability', {}).get('numeric_signal_nc', 0)
        l = ev.get('liquidity', {}).get('numeric_signal_nc', 0)
        d = ev.get('demand', {}).get('numeric_signal_nc', 0)
        o = ev.get('outlook', {}).get('numeric_signal_nc', 0)
        if abs(g - (-0.34)) < 0.02 and abs(l - (-0.84)) < 0.02:
            print('MATCH FOUND!')
            print('CIK:', r[0], 'Company:', r[1], 'FY:', r[2], 'Risk:', r[3])
            print('g:', g, 'p:', p, 'l:', l, 'd:', d, 'o:', o)
            print(json.dumps(ev, indent=2))
