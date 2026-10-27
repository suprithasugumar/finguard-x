"""Fast C++ rapidfuzz matcher against 14,841 DB companies + SEC submissions."""
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rapidfuzz import process, fuzz
from sqlalchemy import create_engine, text
from backend.app.core.config import Settings
from backend.app.ingest.aaer_parser import AAERParser, normalize_company_name

def extract_cand_names(title, body_text):
    cands = []
    if not title:
        return cands
    
    # 1. In the Matter of X
    m = re.search(r"in the matter of\s+([A-Za-z0-9\.,\s&\'\-]+?)(?:,\s*respondent|,\s*defendant|\s+respondent|\s+defendant|\.|$)", title, re.IGNORECASE)
    if m:
        c = m.group(1).strip()
        if len(c) > 3 and not c.lower().startswith("sec v"):
            cands.append(c)
            
    # 2. SEC v. X
    m = re.search(r"sec\s+v\.?\s+([A-Za-z0-9\.,\s&\'\-]+?)(?:,\s*et al|\s+et al|,\s*defendant|\.|$)", title, re.IGNORECASE)
    if m:
        c = m.group(1).strip()
        if len(c) > 3:
            cands.append(c)
            
    # 3. SEC Charges X
    m = re.search(r"sec charges\s+([A-Za-z0-9\.,\s&\'\-]+?)(?:\s+with|\s+for|\s+in|\.|$)", title, re.IGNORECASE)
    if m:
        c = m.group(1).strip()
        if len(c) > 3:
            cands.append(c)
            
    # 4. Raw title itself if short and looks like corporate name
    clean_title = re.sub(r"^in the matter of\s+", "", title, flags=re.IGNORECASE)
    clean_title = re.sub(r"^sec (?:v\.?|charges)\s+", "", clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r",?\s*(?:respondent|defendant|et al\.?).*$", "", clean_title, flags=re.IGNORECASE).strip()
    if clean_title and clean_title not in cands:
        cands.append(clean_title)
        
    return cands

def main():
    with open("data/processed/aaer_full_scraped_releases.json", "r", encoding="utf-8") as f:
        releases = json.load(f)
    print("Total scraped releases:", len(releases))

    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        db_companies = conn.execute(text("SELECT cik, name, ticker, sic FROM companies")).fetchall()
        filings = set((r[0], r[1]) for r in conn.execute(text("SELECT cik, fiscal_year FROM filings WHERE is_amendment = false")).fetchall())
        facts_assets = set((r[0], r[1]) for r in conn.execute(text("SELECT cik, fiscal_year FROM financial_facts WHERE tag='Assets' AND is_original_filing = true AND value > 0")).fetchall())
        rev_tags = ("Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueGoodsNet", "OperatingRevenue")
        rev_filter = ", ".join(f"'{t}'" for t in rev_tags)
        facts_rev = set((r[0], r[1]) for r in conn.execute(text(f"SELECT cik, fiscal_year FROM financial_facts WHERE tag IN ({rev_filter}) AND is_original_filing = true")).fetchall())

    name_to_cik = {}
    norm_names_list = []
    for cik, name, ticker, sic in db_companies:
        norm = normalize_company_name(name)
        if norm and norm not in name_to_cik:
            name_to_cik[norm] = cik
            norm_names_list.append(norm)

    parser = AAERParser()
    matched_cases = []
    ambiguous_matches = []
    
    for idx, r in enumerate(releases):
        title = r.get("raw_title") or r.get("company_name") or ""
        body_text = r.get("full_text") or ""
        aaer_num = r.get("aaer_number")
        
        # Check exclusion
        excl = parser.is_excluded_case(title, body_text[:500])
        if excl:
            continue
            
        cands = extract_cand_names(title, body_text)
        found_cik = None
        match_type = None
        match_score = 0.0
        
        # 1. Exact match on any candidate
        for c in cands:
            norm_c = normalize_company_name(c)
            if norm_c in name_to_cik:
                found_cik = name_to_cik[norm_c]
                match_type = "exact_name"
                match_score = 100.0
                break
                
        # 2. Fast C++ fuzzy match using process.extractOne
        if not found_cik:
            for c in cands:
                norm_c = normalize_company_name(c)
                if len(norm_c) < 6:
                    continue
                res = process.extractOne(norm_c, norm_names_list, scorer=fuzz.token_sort_ratio, score_cutoff=85.0)
                if res:
                    match_str, sc, _ = res
                    if sc >= 92.0:
                        found_cik = name_to_cik[match_str]
                        match_type = "fuzzy_name"
                        match_score = sc
                        break
                    elif sc >= 85.0:
                        ambiguous_matches.append({
                            "aaer_number": aaer_num,
                            "title": title,
                            "candidate": c,
                            "matched_cik": name_to_cik[match_str],
                            "matched_name": match_str,
                            "score": sc,
                        })

        if found_cik:
            # Extract affected years from full text
            years_tuples = parser.extract_affected_fiscal_years(body_text)
            years = [y for y, conf, rat in years_tuples if 2010 <= y <= 2023]
            matched_cases.append({
                "aaer_number": aaer_num,
                "cik": found_cik,
                "title": title,
                "match_type": match_type,
                "score": match_score,
                "years": years,
            })

    unique_matched_ciks = set(m["cik"] for m in matched_cases)
    print(f"Matched non-excluded corporate cases: {len(matched_cases)}")
    print(f"Unique corporate CIKs: {len(unique_matched_ciks)}")
    print(f"Ambiguous matches flagged for manual review: {len(ambiguous_matches)}")
    
    # Check candidate company-years
    cand_pairs = set()
    eligible_pairs = set()
    eligible_ciks = set()
    for m in matched_cases:
        for y in m["years"]:
            cand_pairs.add((m["cik"], y))
            if (m["cik"], y) in filings and (m["cik"], y - 1) in filings and (m["cik"], y) in facts_assets and (m["cik"], y) in facts_rev:
                eligible_pairs.add((m["cik"], y))
                eligible_ciks.add(m["cik"])

    print(f"Candidate (CIK, FY) pairs in FY2010-2023: {len(cand_pairs)}")
    print(f"Eligible (CIK, FY) pairs in DB with 10-K & facts: {len(eligible_pairs)} across {len(eligible_ciks)} unique CIKs")

if __name__ == "__main__":
    main()
