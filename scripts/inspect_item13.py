import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import re, urllib.request, time, pandas as pd, sqlalchemy as sa
from backend.app.ingest.text_extractor import FilingTextExtractor
from backend.app.core.config import Settings

e = sa.create_engine(Settings().DATABASE_URL)
df = pd.read_sql("""
    SELECT f.id, f.cik, f.fiscal_year, f.accession_number, f.primary_document
    FROM filings f
    JOIN company_year_labels l ON l.cik = f.cik AND l.fiscal_year = f.fiscal_year
    LEFT JOIN filing_sections fs ON fs.filing_id = f.id AND fs.section_type = 'related_party' AND fs.word_count > 50
    WHERE f.is_amendment = false AND fs.id IS NULL AND f.primary_document IS NOT NULL
    ORDER BY f.fiscal_year DESC, f.id
    LIMIT 10
""", e)

headers = {'User-Agent': 'FinGuardX audit@finguard-x.ai'}
extractor = FilingTextExtractor()

for idx, r in df.iterrows():
    cik = r['cik']
    fy = r['fiscal_year']
    acc = r['accession_number'].replace('-', '')
    pdoc = r['primary_document']
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{pdoc}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        txt = extractor.html_to_clean_text(resp.read().decode('utf-8', errors='ignore'))
    
    matches = list(re.finditer(r"(?:ITEM|Item)\s+13[\.\:\s\–\—]", txt))
    print(f"\n=== CIK {cik} FY{fy} (acc: {r['accession_number']}) ===")
    if not matches:
        print("  No Item 13 header found")
    for m in matches:
        snippet = txt[m.start():m.start() + 450].replace('\n', ' ')
        print("  Snippet:", snippet[:350])
    time.sleep(0.15)
