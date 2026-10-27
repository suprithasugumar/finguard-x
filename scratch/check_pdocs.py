import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import create_engine, text
from backend.app.core.config import Settings

engine = create_engine(Settings().DATABASE_URL)
with engine.connect() as conn:
    print('Filings with NULL primary_document:', conn.execute(text("SELECT count(*) FROM filings WHERE primary_document IS NULL")).scalar())
    print('Cohort filings with NULL primary_document:', conn.execute(text("SELECT count(*) FROM company_year_labels cyl JOIN filings f ON f.cik = cyl.cik AND f.fiscal_year = cyl.fiscal_year WHERE f.primary_document IS NULL")).scalar())
    print('Cohort company-years without MD&A section:', conn.execute(text("""
        SELECT count(*) FROM company_year_labels cyl 
        LEFT JOIN filing_sections fs ON fs.cik = cyl.cik AND fs.fiscal_year = cyl.fiscal_year AND fs.section_type = 'mda'
        WHERE fs.id IS NULL
    """)).scalar())
    print('Company-years in company_year_fncs_features with contradiction_score = 0 and presence_weight = 0:', conn.execute(text("""
        SELECT count(*) FROM company_year_fncs_features
        WHERE (fncs_evidence->'growth'->>'presence_weight_wc')::float = 0
    """)).scalar())
