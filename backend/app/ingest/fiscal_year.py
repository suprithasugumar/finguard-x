"""Fiscal year derivation supporting standard and 52/53-week filers."""

from datetime import date
from typing import Optional


def derive_fiscal_year(period_end: date, fiscal_year_end_mmdd: Optional[str] = None) -> int:
    """Derive company fiscal year from period_end date and fiscal_year_end MMDD code.

    Supports:
    - Standard calendar/fiscal year-end (e.g., 12/31, 06/30, 09/30)
    - 52/53-week filers whose reporting period ends on the nearest Friday/Saturday,
      which may float into the preceding or following month (e.g., Sept 28 or Oct 2).
    - Early-year filers (e.g., retail ending in Jan/Feb).

    Args:
        period_end: The balance sheet / annual reporting period end date.
        fiscal_year_end_mmdd: 4-character string like '1231', '0930', '0131'.

    Returns:
        The integer fiscal year (e.g. 2023).
    """
    if not fiscal_year_end_mmdd or len(fiscal_year_end_mmdd.strip()) < 4:
        # Default fallback if MMDD is missing:
        # Period ending in second half of year belongs to that calendar year.
        # Period ending in early months (Jan/Feb) belongs to that calendar year.
        return period_end.year

    clean_fye = fiscal_year_end_mmdd.strip()
    try:
        fye_month = int(clean_fye[:2])
        fye_day = int(clean_fye[2:4])
        # Validate month
        if not (1 <= fye_month <= 12):
            return period_end.year
    except ValueError:
        return period_end.year

    # Test candidate fiscal years around the period_end year:
    # Candidates: period_end.year - 1, period_end.year, period_end.year + 1
    candidates = [period_end.year - 1, period_end.year, period_end.year + 1]
    best_year = period_end.year
    min_distance = 9999

    for cand_year in candidates:
        # Calculate nominal target date for this candidate year
        try:
            nominal_date = date(cand_year, fye_month, fye_day)
        except ValueError:
            # Handle leap year Feb 29
            nominal_date = date(cand_year, fye_month, 28)

        distance = abs((period_end - nominal_date).days)
        if distance < min_distance:
            min_distance = distance
            best_year = cand_year

    return best_year
