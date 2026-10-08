"""Normalized financial features and Beneish M-Score extractor with strict anti-leakage."""

import logging
import math
from datetime import date
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.db.models.entities import Company, Filing, FinancialFact
from backend.app.db.models.features import CompanyYearFeatures

logger = logging.getLogger("finguard.features.financial")

# Tag Priority Hierarchy for US-GAAP Concepts
TAG_PRIORITIES = {
    "assets": [
        "Assets",
    ],
    "liabilities": [
        "Liabilities",
    ],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "revenues": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "OperatingRevenue",
        "SalesRevenueGoodsNet",
        "RealEstateRevenueNet",
    ],
    "cogs": [
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfRevenue",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "Cash",
    ],
    "current_assets": [
        "AssetsCurrent",
    ],
    "current_liabilities": [
        "LiabilitiesCurrent",
    ],
    "receivables": [
        "AccountsReceivableNetCurrent",
        "AccountsAndNotesReceivableNet",
    ],
    "inventory": [
        "InventoryNet",
        "InventoryGross",
    ],
    "gross_profit": [
        "GrossProfit",
    ],
    "ppe_net": [
        "PropertyPlantAndEquipmentNet",
    ],
    "depreciation": [
        "DepreciationDepletionAndAmortization",
        "Depreciation",
        "DepreciationAndAmortization",
    ],
    "sga": [
        "SellingGeneralAndAdministrativeExpense",
        "GeneralAndAdministrativeExpense",
    ],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "short_term_debt": [
        "DebtCurrent",
        "ShortTermBorrowings",
        "LongTermDebtCurrent",
    ],
    "cfo": [
        "NetCashProvidedByUsedInOperatingActivities",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
}


class FinancialFeaturesExtractor:
    """Extracts raw financial metrics and calculates 18 ratios + 8 Beneish M-Score components."""

    def __init__(self, session: Session):
        self.session = session

    def extract_company_year_features(
        self,
        cik: str,
        fiscal_year: int,
        cutoff_date: Optional[date] = None,
    ) -> Optional[CompanyYearFeatures]:
        """Extract features for a company-year following R3 anti-leakage and DEC-008."""
        # 1. Fetch current 10-K filing
        filing_query = self.session.query(Filing).filter(
            Filing.cik == cik,
            Filing.fiscal_year == fiscal_year,
            Filing.is_amendment.is_(False),
        )
        if cutoff_date:
            filing_query = filing_query.filter(Filing.filing_date <= cutoff_date)

        filing = filing_query.first()
        if not filing:
            return None

        # Fetch company metadata
        company = self.session.query(Company).filter(Company.cik == cik).first()
        sic = company.sic if company else None
        is_financial = bool(sic and sic.startswith("6"))

        # 2. Sourced values for Current Year (t)
        curr_vals, curr_tags = self._resolve_concept_values(
            cik=cik,
            fiscal_year=fiscal_year,
            accession_number=filing.accession_number,
            cutoff_date=filing.filing_date,
        )

        # 3. Sourced values for Prior Year (t-1) following DEC-008
        prior_vals, prior_tags, prior_source = self._resolve_prior_year_values(
            cik=cik,
            fiscal_year=fiscal_year - 1,
            current_filing=filing,
        )

        # 4. Compute Ratios, Beneish Components, and Null Reasons
        computed = self._compute_all_features(
            curr=curr_vals,
            prior=prior_vals,
            is_financial=is_financial,
        )

        cyf = CompanyYearFeatures(
            company_id=company.id if company else None,
            cik=cik,
            fiscal_year=fiscal_year,
            accession_number=filing.accession_number,
            form_type=filing.form_type,
            filing_date=filing.filing_date,
            sic=sic,
            beneish_applicable=not is_financial,
            prior_val_source=prior_source,
            source_tags={"current": curr_tags, "prior": prior_tags},
            null_reasons=computed["null_reasons"],
            # 18 Core Financial Ratios
            asset_turnover=computed.get("asset_turnover"),
            roa=computed.get("roa"),
            operating_margin=computed.get("operating_margin"),
            net_margin=computed.get("net_margin"),
            current_ratio=computed.get("current_ratio"),
            debt_to_equity=computed.get("debt_to_equity"),
            cash_to_assets=computed.get("cash_to_assets"),
            working_capital_to_assets=computed.get("working_capital_to_assets"),
            cfo_to_assets=computed.get("cfo_to_assets"),
            sales_to_receivables=computed.get("sales_to_receivables"),
            receivables_to_assets=computed.get("receivables_to_assets"),
            inventory_to_assets=computed.get("inventory_to_assets"),
            capex_to_assets=computed.get("capex_to_assets"),
            debt_to_assets=computed.get("debt_to_assets"),
            cash_flow_margin=computed.get("cash_flow_margin"),
            accruals_bs_to_assets=computed.get("accruals_bs_to_assets"),
            accruals_cf_to_assets=computed.get("accruals_cf_to_assets"),
            asset_growth=computed.get("asset_growth"),
            # 8 Beneish Components
            beneish_dsri=computed.get("beneish_dsri"),
            beneish_gmi=computed.get("beneish_gmi"),
            beneish_aqi=computed.get("beneish_aqi"),
            beneish_sgi=computed.get("beneish_sgi"),
            beneish_depi=computed.get("beneish_depi"),
            beneish_sgai=computed.get("beneish_sgai"),
            beneish_lvgi=computed.get("beneish_lvgi"),
            beneish_tata=computed.get("beneish_tata"),
            beneish_tata_bs=computed.get("beneish_tata_bs"),
            # Composite M-Score & Flags
            beneish_m_score=computed.get("beneish_m_score"),
            beneish_flag_178=computed.get("beneish_flag_178"),
            beneish_flag_222=computed.get("beneish_flag_222"),
        )
        return cyf

    def _resolve_concept_values(
        self,
        cik: str,
        fiscal_year: int,
        accession_number: Optional[str] = None,
        cutoff_date: Optional[date] = None,
    ) -> Tuple[Dict[str, float], Dict[str, str]]:
        """Resolve concept values using priority hierarchy from financial_facts."""
        query = self.session.query(FinancialFact).filter(
            FinancialFact.cik == cik,
            FinancialFact.fiscal_year == fiscal_year,
            FinancialFact.is_original_filing.is_(True),
        )
        if accession_number:
            query = query.filter(FinancialFact.accession_number == accession_number)
        if cutoff_date:
            query = query.filter(FinancialFact.filed_date <= cutoff_date)

        facts = query.all()
        fact_map = {f.tag: f.value for f in facts}

        resolved: Dict[str, float] = {}
        tags_used: Dict[str, str] = {}

        for concept, tag_list in TAG_PRIORITIES.items():
            for tag in tag_list:
                if tag in fact_map and fact_map[tag] is not None:
                    resolved[concept] = float(fact_map[tag])
                    tags_used[concept] = tag
                    break

        return resolved, tags_used

    def _resolve_prior_year_values(
        self,
        cik: str,
        fiscal_year: int,
        current_filing: Filing,
    ) -> Tuple[Dict[str, float], Dict[str, str], str]:
        """Resolve prior year values following DEC-008: prior original 10-K with comparative fallback."""
        prior_filing = (
            self.session.query(Filing)
            .filter(
                Filing.cik == cik,
                Filing.fiscal_year == fiscal_year,
                Filing.is_amendment.is_(False),
                Filing.filing_date < current_filing.filing_date,
            )
            .first()
        )

        if prior_filing:
            vals, tags = self._resolve_concept_values(
                cik=cik,
                fiscal_year=fiscal_year,
                accession_number=prior_filing.accession_number,
                cutoff_date=prior_filing.filing_date,
            )
            return vals, tags, "prior_original_10k"

        # Comparative fallback from facts filed on or before current filing
        vals, tags = self._resolve_concept_values(
            cik=cik,
            fiscal_year=fiscal_year,
            cutoff_date=current_filing.filing_date,
        )
        if vals:
            return vals, tags, "comparative_fallback"

        return {}, {}, "missing"

    def _compute_all_features(
        self,
        curr: Dict[str, float],
        prior: Dict[str, float],
        is_financial: bool,
    ) -> Dict[str, Any]:
        """Compute all 18 ratios and 8 Beneish components with strict null tracking."""
        res: Dict[str, Any] = {"null_reasons": {}}
        reasons = res["null_reasons"]

        # Helper getters
        ta = curr.get("assets")
        ta_prev = prior.get("assets")
        rev = curr.get("revenues")
        rev_prev = prior.get("revenues")
        ni = curr.get("net_income")
        op_inc = curr.get("operating_income")
        cogs = curr.get("cogs")
        cogs_prev = prior.get("cogs")
        rec = curr.get("receivables")
        rec_prev = prior.get("receivables")
        inv = curr.get("inventory")
        ca = curr.get("current_assets")
        ca_prev = prior.get("current_assets")
        cl = curr.get("current_liabilities")
        cl_prev = prior.get("current_liabilities")
        cash = curr.get("cash")
        cash_prev = prior.get("cash")
        tl = curr.get("liabilities")
        equity = curr.get("equity")
        cfo = curr.get("cfo")
        capex = curr.get("capex")
        ppen = curr.get("ppe_net")
        ppen_prev = prior.get("ppe_net")
        depr = curr.get("depreciation")
        depr_prev = prior.get("depreciation")
        sga = curr.get("sga")
        sga_prev = prior.get("sga")
        ltd = curr.get("long_term_debt", 0.0)
        ltd_prev = prior.get("long_term_debt", 0.0)
        std = curr.get("short_term_debt", 0.0)
        std_prev = prior.get("short_term_debt", 0.0)

        # 1. Asset Turnover: Rev / TA
        if rev is not None and ta and ta > 0:
            res["asset_turnover"] = rev / ta
        else:
            reasons["asset_turnover"] = "missing_rev_or_assets"

        # 2. ROA: NI / TA
        if ni is not None and ta and ta > 0:
            res["roa"] = ni / ta
        else:
            reasons["roa"] = "missing_ni_or_assets"

        # 3. Operating Margin: OpInc / Rev
        if op_inc is not None and rev and rev > 0:
            res["operating_margin"] = op_inc / rev
        else:
            reasons["operating_margin"] = "missing_opinc_or_rev"

        # 4. Net Margin: NI / Rev
        if ni is not None and rev and rev > 0:
            res["net_margin"] = ni / rev
        else:
            reasons["net_margin"] = "missing_ni_or_rev"

        # 5. Current Ratio: CA / CL
        if ca is not None and cl and cl > 0:
            res["current_ratio"] = ca / cl
        else:
            reasons["current_ratio"] = "missing_ca_or_cl"

        # 6. Debt to Equity: TL / Equity
        if tl is not None and equity and equity > 0:
            res["debt_to_equity"] = tl / equity
        else:
            reasons["debt_to_equity"] = "missing_tl_or_equity"

        # 7. Cash to Assets: Cash / TA
        if cash is not None and ta and ta > 0:
            res["cash_to_assets"] = cash / ta
        else:
            reasons["cash_to_assets"] = "missing_cash_or_ta"

        # 8. Working Capital to Assets: (CA - CL) / TA
        if ca is not None and cl is not None and ta and ta > 0:
            res["working_capital_to_assets"] = (ca - cl) / ta
        else:
            reasons["working_capital_to_assets"] = "missing_ca_cl_or_ta"

        # 9. CFO to Assets: CFO / TA
        if cfo is not None and ta and ta > 0:
            res["cfo_to_assets"] = cfo / ta
        else:
            reasons["cfo_to_assets"] = "missing_cfo_or_ta"

        # 10. Sales to Receivables: Rev / Rec
        if rev is not None and rec and rec > 0:
            res["sales_to_receivables"] = rev / rec
        else:
            reasons["sales_to_receivables"] = "missing_rev_or_rec"

        # 11. Receivables to Assets: Rec / TA
        if rec is not None and ta and ta > 0:
            res["receivables_to_assets"] = rec / ta
        else:
            reasons["receivables_to_assets"] = "missing_rec_or_ta"

        # 12. Inventory to Assets: Inv / TA
        if inv is not None and ta and ta > 0:
            res["inventory_to_assets"] = inv / ta
        else:
            reasons["inventory_to_assets"] = "no_inventory_reported"

        # 13. CapEx to Assets: CapEx / TA
        if capex is not None and ta and ta > 0:
            res["capex_to_assets"] = capex / ta
        else:
            reasons["capex_to_assets"] = "missing_capex_or_ta"

        # 14. Debt to Assets: (LTD + STD) / TA
        total_debt = ltd + std
        if total_debt > 0 and ta and ta > 0:
            res["debt_to_assets"] = total_debt / ta
        elif tl is not None and ta and ta > 0:
            res["debt_to_assets"] = tl / ta
        else:
            reasons["debt_to_assets"] = "missing_debt_or_ta"

        # 15. Cash Flow Margin: CFO / Rev
        if cfo is not None and rev and rev > 0:
            res["cash_flow_margin"] = cfo / rev
        else:
            reasons["cash_flow_margin"] = "missing_cfo_or_rev"

        # 16. Accruals CF to Assets: (NI - CFO) / TA
        if ni is not None and cfo is not None and ta and ta > 0:
            res["accruals_cf_to_assets"] = (ni - cfo) / ta
        else:
            reasons["accruals_cf_to_assets"] = "missing_ni_cfo_or_ta"

        # 17. Accruals BS to Assets
        if (
            ca is not None
            and ca_prev is not None
            and cash is not None
            and cash_prev is not None
            and cl is not None
            and cl_prev is not None
            and depr is not None
            and ta
            and ta > 0
        ):
            delta_wc = (ca - ca_prev) - (cash - cash_prev) - ((cl - cl_prev) - (std - std_prev))
            res["accruals_bs_to_assets"] = (delta_wc - depr) / ta
        else:
            reasons["accruals_bs_to_assets"] = "missing_bs_accruals_inputs"

        # 18. Asset Growth: (TA - TA_prev) / TA_prev
        if ta is not None and ta_prev and ta_prev > 0:
            res["asset_growth"] = (ta - ta_prev) / ta_prev
        else:
            reasons["asset_growth"] = "missing_prior_assets"

        # =========================================================================
        # BENEISH M-SCORE 8 COMPONENTS
        # =========================================================================
        if is_financial:
            reasons["beneish"] = "financial_industry_inapplicable"
            return res

        # 1. DSRI: (Rec_t / Rev_t) / (Rec_{t-1} / Rev_{t-1})
        if (
            rec is not None
            and rev
            and rev > 0
            and rec_prev is not None
            and rev_prev
            and rev_prev > 0
            and rec_prev > 0
        ):
            dsri = (rec / rev) / (rec_prev / rev_prev)
            if not math.isnan(dsri) and not math.isinf(dsri):
                res["beneish_dsri"] = dsri
            else:
                reasons["beneish_dsri"] = "nan_inf"
        else:
            reasons["beneish_dsri"] = "missing_rec_or_rev"

        # 2. GMI: ((Rev_prev - COGS_prev) / Rev_prev) / ((Rev - COGS) / Rev)
        if (
            rev
            and rev > 0
            and rev_prev
            and rev_prev > 0
            and cogs is not None
            and cogs_prev is not None
        ):
            gm_prev = (rev_prev - cogs_prev) / rev_prev
            gm_curr = (rev - cogs) / rev
            if gm_curr > 0:
                gmi = gm_prev / gm_curr
                if not math.isnan(gmi) and not math.isinf(gmi):
                    res["beneish_gmi"] = gmi
                else:
                    reasons["beneish_gmi"] = "nan_inf"
            else:
                reasons["beneish_gmi"] = "non_positive_current_gross_margin"
        else:
            reasons["beneish_gmi"] = "missing_rev_or_cogs"

        # 3. AQI: (1 - (CA + PPEN) / TA) / (1 - (CA_prev + PPEN_prev) / TA_prev)
        if (
            ta
            and ta > 0
            and ta_prev
            and ta_prev > 0
            and ca is not None
            and ca_prev is not None
            and ppen is not None
            and ppen_prev is not None
        ):
            non_ca_ppen_curr = 1.0 - (ca + ppen) / ta
            non_ca_ppen_prev = 1.0 - (ca_prev + ppen_prev) / ta_prev
            if non_ca_ppen_prev > 0:
                aqi = non_ca_ppen_curr / non_ca_ppen_prev
                if not math.isnan(aqi) and not math.isinf(aqi):
                    res["beneish_aqi"] = aqi
                else:
                    reasons["beneish_aqi"] = "nan_inf"
            else:
                reasons["beneish_aqi"] = "zero_prior_denominator"
        else:
            reasons["beneish_aqi"] = "missing_ca_ppen_or_ta"

        # 4. SGI: Rev / Rev_prev
        if rev is not None and rev_prev and rev_prev > 0:
            sgi = rev / rev_prev
            if not math.isnan(sgi) and not math.isinf(sgi):
                res["beneish_sgi"] = sgi
            else:
                reasons["beneish_sgi"] = "nan_inf"
        else:
            reasons["beneish_sgi"] = "missing_prior_rev"

        # 5. DEPI: Depr_rate_prev / Depr_rate_curr
        # Depr_rate = Depr / (PPEN + Depr)
        if (
            depr is not None
            and depr_prev is not None
            and ppen is not None
            and ppen_prev is not None
        ):
            denom_curr = ppen + depr
            denom_prev = ppen_prev + depr_prev
            if denom_curr > 0 and denom_prev > 0 and depr > 0:
                dr_curr = depr / denom_curr
                dr_prev = depr_prev / denom_prev
                depi = dr_prev / dr_curr
                if not math.isnan(depi) and not math.isinf(depi):
                    res["beneish_depi"] = depi
                else:
                    reasons["beneish_depi"] = "nan_inf"
            else:
                reasons["beneish_depi"] = "zero_depr_or_ppen"
        else:
            reasons["beneish_depi"] = "missing_depr_or_ppen"

        # 6. SGAI: (SGA / Rev) / (SGA_prev / Rev_prev)
        if (
            sga is not None
            and rev
            and rev > 0
            and sga_prev is not None
            and rev_prev
            and rev_prev > 0
            and sga_prev > 0
        ):
            sgai = (sga / rev) / (sga_prev / rev_prev)
            if not math.isnan(sgai) and not math.isinf(sgai):
                res["beneish_sgai"] = sgai
            else:
                reasons["beneish_sgai"] = "nan_inf"
        else:
            reasons["beneish_sgai"] = "missing_sga_or_rev"

        # 7. LVGI: Lev_curr / Lev_prev
        # Lev = (LTD + CL) / TA
        curr_cl = cl if cl is not None else 0.0
        prev_cl = cl_prev if cl_prev is not None else 0.0
        if ta and ta > 0 and ta_prev and ta_prev > 0:
            lev_curr = (ltd + curr_cl) / ta
            lev_prev = (ltd_prev + prev_cl) / ta_prev
            if lev_prev > 0:
                lvgi = lev_curr / lev_prev
                if not math.isnan(lvgi) and not math.isinf(lvgi):
                    res["beneish_lvgi"] = lvgi
                else:
                    reasons["beneish_lvgi"] = "nan_inf"
            else:
                reasons["beneish_lvgi"] = "zero_prior_leverage"
        else:
            reasons["beneish_lvgi"] = "missing_assets"

        # 8. TATA:
        # Primary: (NI - CFO) / TA
        if ni is not None and cfo is not None and ta and ta > 0:
            tata = (ni - cfo) / ta
            if not math.isnan(tata) and not math.isinf(tata):
                res["beneish_tata"] = tata
            else:
                reasons["beneish_tata"] = "nan_inf"
        else:
            reasons["beneish_tata"] = "missing_ni_cfo_or_ta"

        # Secondary TATA (Balance-Sheet Based)
        if res.get("accruals_bs_to_assets") is not None:
            res["beneish_tata_bs"] = res["accruals_bs_to_assets"]

        # =========================================================================
        # COMPOSITE BENEISH M-SCORE
        # M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI + 0.115*DEPI
        #     - 0.172*SGAI + 4.037*TATA + 0.0327*LVGI
        # RULE: M-Score is NULL if ANY component is NULL (No imputation).
        # =========================================================================
        comp_keys = [
            "beneish_dsri",
            "beneish_gmi",
            "beneish_aqi",
            "beneish_sgi",
            "beneish_depi",
            "beneish_sgai",
            "beneish_lvgi",
            "beneish_tata",
        ]
        all_present = all(res.get(k) is not None for k in comp_keys)

        if all_present:
            m = (
                -4.84
                + 0.920 * res["beneish_dsri"]
                + 0.528 * res["beneish_gmi"]
                + 0.404 * res["beneish_aqi"]
                + 0.892 * res["beneish_sgi"]
                + 0.115 * res["beneish_depi"]
                - 0.172 * res["beneish_sgai"]
                + 4.037 * res["beneish_tata"]
                + 0.0327 * res["beneish_lvgi"]
            )
            if not math.isnan(m) and not math.isinf(m):
                res["beneish_m_score"] = m
                res["beneish_flag_178"] = m > -1.78
                res["beneish_flag_222"] = m > -2.22
            else:
                reasons["beneish_m_score"] = "nan_inf"
        else:
            missing_comps = [k for k in comp_keys if res.get(k) is None]
            reasons["beneish_m_score"] = f"incomplete_components ({', '.join(missing_comps)})"

        return res
