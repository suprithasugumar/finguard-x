import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import create_engine, text
from backend.app.core.config import Settings

engine = create_engine(Settings().DATABASE_URL)
with engine.connect() as conn:
    row = conn.execute(text("SELECT cik, fiscal_year, accession_number, primary_document FROM filings WHERE cik = '0000886171' AND fiscal_year = 2013")).fetchone()
    print("Filing:", row)
    exp = conn.execute(text("SELECT * FROM company_year_explanations WHERE cik = '0000886171' AND fiscal_year = 2013")).mappings().fetchone()
    print("Explanation plain language summary:", exp['plain_language_summary'] if exp else None)
