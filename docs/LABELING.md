# FinGuard-X Ground-Truth Labeling & Matched Controls Methodology

**Document:** `docs/LABELING.md`  
**Version:** Phase 1 (SEC Ingestion + Labels)  
**Rules Reference:** R1 (No Fake Data), R2 (Honest Reporting), R3 (No Leakage), R5 (Language Standards)

---

## 1. Ground-Truth Positive Labels (SEC AAER Releases)

### 1.1 Source & Scope
Positive labels ($y = 1$) are derived from official SEC **Accounting and Auditing Enforcement Releases (AAER)** index and litigation documents. 
- A positive label represents a **company-year** $(CIK, FY)$ whose financial statements for that specific fiscal period were materially misstated, manipulated, or the explicit subject of the SEC fraud enforcement proceeding.
- The unit of analysis is strictly **company-year** $(CIK, FY, \text{Accession})$.
- Temporal bounds: **FY2010 to latest available** (prior years have sparse XBRL coverage).

### 1.2 Exclusion Criteria
An AAER release does NOT result in a positive issuer label if any of the following apply:
1. **Section 12(j) Proceedings:** Administrative proceedings for revocation of registration solely due to delinquent periodic filings (non-reporting, empty shells) are excluded (`exclusion_reason = "Section 12(j) delinquent filing"`).
2. **Rule 102(e) Proceedings:** Actions solely against individual CPAs, auditors, or legal counsel suspending their right to practice before the Commission are excluded (`exclusion_reason = "Rule 102(e) professional sanction"`).
3. **Auditor Sanctions:** Sanctions against auditing firms (e.g., KPMG, PwC, EY, Deloitte, BDO) for audit deficiencies rather than issuer fraud are excluded.
4. **Individual-Only Cases:** Civil or criminal actions naming only individual officers without identifying corporate financial statement misstatements.
5. **Third-Party / Unrelated Mentions:** Third parties referenced in passing are excluded or assigned `low` confidence.

### 1.3 CIK Resolution & Former Names
Issuer identity is resolved via:
- Explicit CIK printed in the release text.
- Exact match on current corporate name (normalized: lowercased, legal entity suffixes removed).
- Match on historical `formerNames` recorded in SEC `submissions` records (critical for issuers that changed names or rebranded after fraud revelations).
- High-threshold fuzzy matching (Rapidfuzz score $\ge 90\%$), flagged as `medium` confidence for human review.

### 1.4 Affected Fiscal Years & Enforcement Date
- Explicit year mentions (`fiscal year 2014`, `for the year ended ...`) are mapped to the corresponding fiscal year at `high` confidence.
- Year ranges (`fiscal years 2013 through 2015`) are expanded into all constituent annual periods $[2013, 2014, 2015]$.
- Quarter-only allegations (`third quarter of 2016`) are mapped to the containing fiscal year at `medium` confidence, with rationale recording quarterly origin.
- The **enforcement date** is defined as the date of the **earliest AAER release** citing the issuer, ensuring no look-ahead bias.

---

## 2. Eligibility Requirements (Both Positives and Controls)

To ensure comparability and prevent feature extraction failures during ML modeling (Phase 2):
1. **Original 10-K Filing:** Must have an original, unamended 10-K filing in the database for $(CIK, FY)$.
2. **Prior-Year 10-K Filing:** Must have an original 10-K filing for the preceding fiscal year $(CIK, FY - 1)$ (mandatory for computing YoY growth, accruals, and Beneish M-Score components).
3. **Fundamental Non-Null Financials:** Must report non-null, positive Total Assets (`Assets`) and non-null Revenues (`Revenues` or approved us-gaap variants).

Company-years failing any of these criteria are excluded with explicit reason codes logged in the database and gate reports.

---

## 3. Matched Controls ($y = 0$)

### 3.1 Contamination & Leakage Prevention (R3)
- **Zero-Enforcement Lifetime Exclusion:** Any firm that has EVER received an SEC AAER release is permanently excluded from serving as a control firm in ANY fiscal year.
- **Post-Enforcement Exclusion:** All fiscal years at or after a company's earliest AAER enforcement date are excluded from both positive training and controls (contaminated post-fraud period).

### 3.2 Matching Algorithm (1:5 Ratio Without Replacement)
For each eligible positive company-year $(CIK_p, FY_p)$:
1. Candidate Pool:
   - Same fiscal year ($FY_c = FY_p$).
   - Same 2-digit SIC industry group ($\text{SIC}_{c, 2d} = \text{SIC}_{p, 2d}$).
   - Company has 0 AAER enforcement actions over its entire history.
   - Candidate firm has not already been used as a control in fiscal year $FY_p$ (matching **without replacement**).
2. Distance Metric:
   $$\text{Distance} = \left| \ln(\text{Assets}_c) - \ln(\text{Assets}_p) \right|$$
3. Selection:
   - Sort candidates by distance ascending.
   - Select the 5 nearest candidates.
   - If $< 5$ candidates exist within the 2-digit SIC, fall back to 1-digit SIC before taking the nearest available.
   - Record `match_distance` and `matched_positive_id` in `company_year_labels`.

---

## 4. Manual Review & Override Workflow

Cases flagged with `medium` or `low` confidence (e.g. fuzzy entity matches, quarter-derived fiscal years) are exported to `data/gold/label_review.csv`.

### Review Protocol:
1. Reviewer inspects the AAER PDF and 10-K filing.
2. Updates `review_status` to `approved`, `rejected`, or `override`, and records rationale in `reviewer_notes`.
3. Subsequent pipeline runs load `label_review.csv` and apply manual overrides on top of automated rules without data loss.

---

## 5. Limitations & Expansion Scope
- **Current Pilot Scope:** 12 positive company-years across 5 major corporate fraud cases, matched with 58 industry-size controls (approx 1:5 ratio without replacement).
- **Expansion Roadmap for Full Scale (50+ positives):**
  - Download complete SEC historical AAER archive from 2010–2024.
  - Ingest top 300 SEC filers and all cited issuers from SEC `companyfacts.zip`.
  - Maintain the exact same matching criteria and verification rules without changing the methodology.
