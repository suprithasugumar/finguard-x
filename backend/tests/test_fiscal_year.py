"""Tests for fiscal year derivation including 52/53-week filers."""

from datetime import date

from backend.app.ingest.fiscal_year import derive_fiscal_year


def test_standard_calendar_filer():
    """Calendar year filers (1231) map directly to period_end year."""
    assert derive_fiscal_year(date(2023, 12, 31), "1231") == 2023
    assert derive_fiscal_year(date(2022, 12, 31), "1231") == 2022


def test_apple_52_53_week_filer():
    """Apple (FYE 0930) ends on the last Saturday of September, occasionally floating into October."""
    # 2023: ended Sept 30
    assert derive_fiscal_year(date(2023, 9, 30), "0930") == 2023
    # 2022: ended Sept 24
    assert derive_fiscal_year(date(2022, 9, 24), "0930") == 2022
    # 2021: ended Sept 25
    assert derive_fiscal_year(date(2021, 9, 25), "0930") == 2021
    # 53-week cycle floating into October 1: belongs to FY 2016
    assert derive_fiscal_year(date(2016, 10, 1), "0930") == 2016


def test_retail_january_52_53_week_filer():
    """Retailers like Target/Walmart (FYE 0131) end around late Jan or early Feb."""
    # 2024: ended Feb 3, 2024 -> FY 2024
    assert derive_fiscal_year(date(2024, 2, 3), "0131") == 2024
    # 2023: ended Jan 28, 2023 -> FY 2023
    assert derive_fiscal_year(date(2023, 1, 28), "0131") == 2023


def test_nike_may_year_end():
    """Nike (FYE 0531) ending May 31."""
    assert derive_fiscal_year(date(2023, 5, 31), "0531") == 2023
    assert derive_fiscal_year(date(2023, 5, 28), "0531") == 2023
