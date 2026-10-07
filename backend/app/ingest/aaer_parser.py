"""SEC Accounting and Auditing Enforcement Releases (AAER) parser and label builder."""

import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import pypdf
from rapidfuzz import fuzz

logger = logging.getLogger("finguard.ingest.aaer_parser")

# Standard entity suffix cleaner
SUFFIX_REGEX = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|llc|lp|ltd|limited|plc|sa|nv)\b",
    re.IGNORECASE,
)


def normalize_company_name(name: str) -> str:
    """Normalize company name by lowering, stripping punctuation and legal suffixes."""
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r"[^\w\s]", " ", name)
    name = SUFFIX_REGEX.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract text from PDF file in memory."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages_text)
    except Exception as e:
        logger.warning(f"Failed to extract PDF text: {e}")
        return ""


class AAERParser:
    """Extracts enforcement respondents, affected fiscal years, and CIKs from AAER text."""

    def __init__(self, company_lookup: Optional[Dict[str, Dict[str, Any]]] = None):
        """Initialize parser with optional SEC company directory (including formerNames).

        company_lookup maps normalized name -> {cik, name, ticker, former_names}
        """
        self.company_lookup = company_lookup or {}

    def is_excluded_case(self, title: str, text: str) -> Optional[str]:
        """Check exclusion criteria: Section 12(j), Rule 102(e), individual-only, and auditors."""
        combined = f"{title}\n{text}".lower()

        # 1. Section 12(j) - Administrative revocation for delinquent filings
        if "12(j)" in combined or "section 12(j)" in combined:
            return "Section 12(j) delinquent filing"

        # 2. Rule 102(e) - Suspension of individual accountants/attorneys
        if "102(e)" in combined or "rule 102(e)" in combined:
            return "Rule 102(e) professional sanction"

        # 3. Auditor sanctions (Big 4 and national firms)
        auditor_names = [
            "kpmg",
            "ernst & young",
            "deloitte",
            "pricewaterhousecoopers",
            "pwc",
            "bdo usa",
            "grant thornton",
            "crowe",
        ]
        title_lower = title.lower()
        for aud in auditor_names:
            if aud in title_lower:
                return f"Auditor firm sanction: {aud}"

        # 4. Individual-only proceedings (Title contains person name without company suffix)
        if re.search(r"in the matter of [a-z\s]+, cpa\b", title_lower) or re.search(
            r"in the matter of [a-z\s]+, ca\b", title_lower
        ):
            return "Individual accountant proceeding"

        return None

    def extract_respondent_name(self, title: str, text: str) -> Optional[str]:
        """Extract primary corporate respondent name from caption or title."""
        # Pattern 1: "In the Matter of XYZ Corp., Respondent"
        match = re.search(
            r"in the matter of\s+([A-Za-z0-9\.,\s&]+?)(?:,|\s+respondent|\s+defendants)",
            title,
            re.IGNORECASE,
        )
        if match:
            candidate = match.group(1).strip()
            if len(candidate) > 3 and not candidate.lower().startswith("sec v"):
                return candidate

        # Pattern 2: "SEC Charges XYZ Corp."
        match = re.search(
            r"sec charges\s+([A-Za-z0-9\.,\s&]+?)\s+(?:with|for)", title, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        return None

    def resolve_cik(self, respondent_name: str, text: str) -> Tuple[Optional[str], str, float]:
        """Resolve respondent to CIK using explicit CIK, exact name, formerNames, or fuzzy matching.

        Returns (cik, match_method, confidence_score)
        """
        # 1. Check for explicit CIK in release text
        cik_match = re.search(
            r"\bCIK(?:\s*(?:no\.?|code)?:?\s*|\s+)(\d{1,10})\b", text, re.IGNORECASE
        )
        if cik_match:
            cik_found = cik_match.group(1).zfill(10)
            return cik_found, "explicit_cik_text", 100.0

        if not respondent_name or not self.company_lookup:
            return None, "unresolved", 0.0

        norm_target = normalize_company_name(respondent_name)

        # 2. Exact match against current company name
        if norm_target in self.company_lookup:
            info = self.company_lookup[norm_target]
            return info["cik"], "exact_name", 100.0

        # 3. Match against formerNames
        for norm_name, info in self.company_lookup.items():
            for former in info.get("former_names", []):
                norm_former = normalize_company_name(former)
                if norm_target == norm_former:
                    return info["cik"], "former_name", 98.0

        # 4. High-threshold fuzzy match (>= 90%)
        best_cik = None
        best_score = 0.0
        for norm_name, info in self.company_lookup.items():
            score = fuzz.token_sort_ratio(norm_target, norm_name)
            if score > best_score:
                best_score = score
                best_cik = info["cik"]

        if best_score >= 90.0:
            return best_cik, "fuzzy_name", best_score

        return None, "unresolved", best_score

    def extract_affected_fiscal_years(self, text: str) -> List[Tuple[int, str, str]]:
        """Extract affected fiscal years, expanding year ranges and mapping quarters.

        Returns list of tuples: (fiscal_year, confidence, rationale)
        """
        results: Dict[int, Tuple[str, str]] = {}

        # 1. Year Ranges: "fiscal years 2013 through 2015" or "2013 to 2016"
        range_pattern = re.compile(
            r"fiscal\s+years?\s+(\d{4})\s*(?:through|to|and|-)\s*(\d{4})", re.IGNORECASE
        )
        for match in range_pattern.finditer(text):
            start_yr = int(match.group(1))
            end_yr = int(match.group(2))
            if 1990 <= start_yr <= 2030 and 1990 <= end_yr <= 2030 and end_yr >= start_yr:
                for y in range(start_yr, end_yr + 1):
                    results[y] = (
                        "high",
                        f"Expanded from range: fiscal years {start_yr} through {end_yr}",
                    )

        # 2. Individual Fiscal Years: "fiscal year 2014" or "for FY 2015"
        fy_pattern = re.compile(r"(?:fiscal\s+year|fy)\s*(\d{4})", re.IGNORECASE)
        for match in fy_pattern.finditer(text):
            yr = int(match.group(1))
            if 1990 <= yr <= 2030 and yr not in results:
                results[yr] = ("high", f"Explicit mention of fiscal year {yr}")

        # 3. For the year ended [Date YYYY]
        year_ended_pattern = re.compile(
            r"(?:for\s+the\s+year\s+ended|period\s+ended)\s+[a-z]+\s+\d{1,2},\s*(\d{4})",
            re.IGNORECASE,
        )
        for match in year_ended_pattern.finditer(text):
            yr = int(match.group(1))
            if 1990 <= yr <= 2030 and yr not in results:
                results[yr] = ("high", f"Explicit year-ended date in {yr}")

        # 4. Quarter-only misstatement: "first quarter of 2014", "Q3 2015" -> Map to FY (medium confidence)
        quarter_pattern = re.compile(
            r"(?:first|second|third|fourth|q[1-4]|1st|2nd|3rd|4th)\s+quarter\s+(?:of\s+)?(\d{4})",
            re.IGNORECASE,
        )
        for match in quarter_pattern.finditer(text):
            yr = int(match.group(1))
            if 1990 <= yr <= 2030 and yr not in results:
                results[yr] = (
                    "medium",
                    f"Derived from quarterly misstatement in quarter of {yr}",
                )

        # Format output list sorted by year
        output = [(yr, conf, rat) for yr, (conf, rat) in sorted(results.items())]
        return output
