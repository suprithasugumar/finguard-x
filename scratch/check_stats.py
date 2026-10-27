import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import create_engine, text
from backend.app.core.config import Settings

engine = create_engine(Settings().DATABASE_URL)
with engine.connect() as conn:
    print('Total filings in filing_sections:', conn.execute(text("SELECT count(DISTINCT cik) FROM filing_sections")).scalar())
    print('Total rows in filing_sections:', conn.execute(text("SELECT count(*) FROM filing_sections")).scalar())
    print('Total distinct (cik, fiscal_year) in filing_sections where section_type = \'mda\':', conn.execute(text("SELECT count(DISTINCT (cik, fiscal_year)) FROM filing_sections WHERE section_type = 'mda'")).scalar())
    print('Total distinct (cik, fiscal_year) in company_year_fncs_features:', conn.execute(text("SELECT count(*) FROM company_year_fncs_features")).scalar())
