"""SEC 10-K filing text extraction engine for MD&A, Risk Factors, and Related-Party Footnotes."""

import logging
import re
from typing import Any, Dict, Optional, Tuple

from bs4 import BeautifulSoup

logger = logging.getLogger("finguard.ingest.text_extractor")


class FilingTextExtractor:
    """Extracts Item 7 MD&A, Item 1A Risk Factors, and Related-Party Footnotes from 10-K HTML."""

    @staticmethod
    def html_to_clean_text(html_content: str) -> str:
        """Convert raw HTML filing to clean plaintext preserving paragraph boundaries."""
        soup = BeautifulSoup(html_content, "lxml")
        # Remove script and style tags
        for element in soup(["script", "style", "header", "footer"]):
            element.decompose()

        # Extract text
        text = soup.get_text(separator="\n")
        # Normalize whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()

    def extract_sections(self, raw_html_or_text: str) -> Dict[str, Dict[str, Any]]:
        """Extract all 3 target sections from 10-K document."""
        if "<html" in raw_html_or_text[:1000].lower() or "<div" in raw_html_or_text[:1000].lower():
            text = self.html_to_clean_text(raw_html_or_text)
        else:
            text = raw_html_or_text

        results = {}
        # 1. Extract Item 7 MD&A
        mda_text, mda_loc = self._extract_mda(text)
        results["mda"] = {
            "text": mda_text,
            "source_location": mda_loc,
            "status": "success" if mda_text and len(mda_text) > 500 else "not_found",
        }

        # 2. Extract Item 1A Risk Factors
        risk_text, risk_loc = self._extract_risk_factors(text)
        results["risk_factors"] = {
            "text": risk_text,
            "source_location": risk_loc,
            "status": "success" if risk_text and len(risk_text) > 500 else "not_found",
        }

        # 3. Extract Related-Party Note
        rp_text, rp_loc = self._extract_related_party(text)
        results["related_party"] = {
            "text": rp_text,
            "source_location": rp_loc,
            "status": "success" if rp_text and len(rp_text) > 100 else "not_found",
        }

        return results

    def _extract_mda(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract Item 7 MD&A body text."""
        # Regex pattern matching Item 7 heading robustly across unicode/non-breaking spaces
        item7_pattern = re.compile(
            r"(?:^|\n)[ \t\xa0]*(?:ITEM|Item)\s+7[\.\:\s\–\—\xa0]+.{0,20}?(?:MANAGEMENT|Management).{0,10}?(?:DISCUSSION|Discussion)",
            re.IGNORECASE,
        )
        # End boundaries: Item 7A or Item 8
        end_pattern = re.compile(
            r"(?:^|\n)[ \t\xa0]*(?:ITEM|Item)\s+(?:7A|8)[\.\:\s\–\—\xa0]+",
            re.IGNORECASE,
        )

        matches = list(item7_pattern.finditer(text))
        if not matches:
            return None, None

        best_section = None
        best_loc = None

        for match in reversed(matches):
            start_pos = match.end()
            end_match = end_pattern.search(text, start_pos)
            if end_match:
                candidate = text[start_pos : end_match.start()].strip()
            else:
                candidate = text[start_pos : start_pos + 150000].strip()

            if len(candidate) > 1000:
                best_section = candidate
                best_loc = f"char_pos_{match.start()}_{start_pos}"
                break

        return best_section, best_loc

    def _extract_risk_factors(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract Item 1A Risk Factors body text."""
        item1a_pattern = re.compile(
            r"(?:^|\n)[ \t\xa0]*(?:ITEM|Item)\s+1A[\.\:\s\–\—\xa0]+.{0,10}?(?:RISK|Risk).{0,10}?(?:FACTORS|Factors)",
            re.IGNORECASE,
        )
        end_pattern = re.compile(
            r"(?:^|\n)[ \t\xa0]*(?:ITEM|Item)\s+(?:1B|2)[\.\:\s\–\—\xa0]+",
            re.IGNORECASE,
        )

        matches = list(item1a_pattern.finditer(text))
        if not matches:
            return None, None

        best_section = None
        best_loc = None

        for match in reversed(matches):
            start_pos = match.end()
            end_match = end_pattern.search(text, start_pos)
            if end_match:
                candidate = text[start_pos : end_match.start()].strip()
            else:
                candidate = text[start_pos : start_pos + 150000].strip()

            if len(candidate) > 1000:
                best_section = candidate
                best_loc = f"char_pos_{match.start()}_{start_pos}"
                break

        return best_section, best_loc

    def _extract_related_party(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract Related-Party Transactions footnote text."""
        rp_pattern = re.compile(
            r"(?:^|\n)[ \t]*(?:Note\s+\d+[\.\:\s\–\—]+)?Related\s+Party(?:\s+Transactions)?[^\n]*",
            re.IGNORECASE,
        )
        end_pattern = re.compile(
            r"(?:^|\n)[ \t]*Note\s+\d+[\.\:\s\–\—]+",
            re.IGNORECASE,
        )

        matches = list(rp_pattern.finditer(text))
        if not matches:
            return None, None

        for match in reversed(matches):
            start_pos = match.end()
            end_match = end_pattern.search(text, start_pos)
            if end_match:
                candidate = text[start_pos : end_match.start()].strip()
            else:
                candidate = text[start_pos : start_pos + 30000].strip()

            if len(candidate) > 100:
                return candidate, f"char_pos_{match.start()}_{start_pos}"

        return None, None
