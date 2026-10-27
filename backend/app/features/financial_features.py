"""Normalized financial features and Beneish M-Score extractor with strict anti-leakage."""

import datetime
import logging
import math
from datetime import date
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.db.models.entities import Company, Filing, FinancialFact
from backend.app.db.models.features import CompanyYearFeatures

logger = logging.getLogger("finguard.features.financial")

# Tag Priority Hierarchy with Enhanced Fallback Chains for US-GAAP Concepts
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
        "CommonStockValue",
    ],
    "revenues": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "SalesRevenueGoodsGross",
        "OtherSalesRevenueNet",
        "OperatingRevenue",
        "RealEstateRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "cogs": [
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfGoodsSold",
        "CostOfServices",
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
        "ReceivablesNetCurrent",
        "AccountsReceivableNet",
        "AccountsReceivableGrossCurrent",
        "AccountsAndOtherReceivablesNetCurrent",
        "OtherReceivablesNetCurrent",
        "AccountsAndNotesReceivableNet",
        "ReceivablesNet",
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
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "sga": [
        "SellingGeneralAndAdministrativeExpense",
        "GeneralAndAdministrativeExpense",
        "SellingAndMarketingExpense",
        "OtherGeneralAndAdministrativeExpense",
        "SellingExpense",
        "OtherSellingGeneralAndAdministrativeExpense",
        "OperatingExpenses",
    ],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebt",
    ],
    "short_term_debt": [
        "DebtCurrent",
        "ShortTermBorrowings",
        "LongTermDebtCurrent",
    ],
    "cfo": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
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
        """Extract features for a company-year following R3 anti-leakage and Phase 1 specifications."""
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
        # Financial firms: SIC 6000-6999
        is_financial = bool(sic and sic.strip() and sic.strip().startswith("6"))

        # 2. Sourced values for Current Year (t)
        curr_vals, curr_tags = self._resolve_concept_values(
            cik=cik,
            fiscal_year=fiscal_year,
            accession_number=filing.accession_number,
            cutoff_date=filing.filing_date,
        )

        # 3. Sourced values for Prior Year (t-1)
        prior_vals, prior_tags, prior_source = self._resolve_prior_year_values(
            cik=cik,
            fiscal_year=fiscal_year - 1,
            current_filing=filing,
        )

        # 4. Compute Ratios, Beneish Components, and Status/Null Reasons
        computed = self._compute_all_features(
            curr=curr_vals,
            prior=prior_vals,
            is_financial=is_financial,
            fiscal_year=fiscal_year,
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
            feature_statuses=computed["feature_statuses"],
            inventory_applicable=computed["inventory_applicable"],
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
            # Composite M-Score & Both Strict / Neutral Metrics
            beneish_m_score=computed.get("beneish_strict"),
            beneish_strict=computed.get("beneish_strict"),
            beneish_neutral=computed.get("beneish_neutral"),
            beneish_n_components=computed.get("beneish_n_components", 0),
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
        """Resolve concept values using priority hierarchy and fallback chains from financial_facts."""
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

        # Contemporaneous filing date fallback: if a concept was missing from the exact accession number,
        # resolve from any fact filed for that (cik, fiscal_year) on or before cutoff_date (strict anti-leakage)
        missing_concepts = [c for c in TAG_PRIORITIES if c not in resolved]
        if missing_concepts and accession_number and cutoff_date:
            fallback_query = self.session.query(FinancialFact).filter(
                FinancialFact.cik == cik,
                FinancialFact.fiscal_year == fiscal_year,
                FinancialFact.filed_date <= cutoff_date,
            )
            fallback_facts = fallback_query.all()
            fallback_map = {f.tag: f.value for f in fallback_facts if f.value is not None}
            for concept in missing_concepts:
                for tag in TAG_PRIORITIES[concept]:
                    if tag in fallback_map and fallback_map[tag] is not None:
                        resolved[concept] = float(fallback_map[tag])
                        tags_used[concept] = f"{tag} (contemporaneous_fallback)"
                        break

        # Fallback chain for liabilities: if Liabilities is absent, sum Current + Noncurrent
        if "liabilities" not in resolved:
            if "LiabilitiesCurrent" in fact_map and fact_map["LiabilitiesCurrent"] is not None:
                lc = float(fact_map["LiabilitiesCurrent"])
                lnc = float(fact_map.get("LiabilitiesNoncurrent") or 0.0)
                resolved["liabilities"] = lc + lnc
                tags_used["liabilities"] = "LiabilitiesCurrent+LiabilitiesNoncurrent"

        # Accounting identity fallback: GrossProfit = Revenues - COGS
        if "cogs" not in resolved and "gross_profit" in resolved and "revenues" in resolved:
            resolved["cogs"] = resolved["revenues"] - resolved["gross_profit"]
            tags_used["cogs"] = "revenues - gross_profit"
        elif "gross_profit" not in resolved and "cogs" in resolved and "revenues" in resolved:
            resolved["gross_profit"] = resolved["revenues"] - resolved["cogs"]
            tags_used["gross_profit"] = "revenues - cogs"

        return resolved, tags_used

    def _resolve_prior_year_values(
        self,
        cik: str,
        fiscal_year: int,
        current_filing: Filing,
    ) -> Tuple[Dict[str, float], Dict[str, str], str]:
        """Resolve prior year values: prior original 10-K (handling 52/53-week years) with comparative fallback."""
        # Check standard fiscal year - 1
        prior_filing = (
            self.session.query(Filing)
            .filter(
                Filing.cik == cik,
                Filing.fiscal_year == fiscal_year,
                Filing.is_amendment.is_(False),
                Filing.filing_date < current_filing.filing_date,
            )
            .order_by(Filing.filing_date.desc())
            .first()
        )

        # 52/53-week year end shift fallback
        if not prior_filing and current_filing.period_end:
            prior_filing = (
                self.session.query(Filing)
                .filter(
                    Filing.cik == cik,
                    Filing.is_amendment.is_(False),
                    Filing.filing_date < current_filing.filing_date,
                    Filing.period_end >= current_filing.period_end - datetime.timedelta(days=390),
                    Filing.period_end <= current_filing.period_end - datetime.timedelta(days=330),
                )
                .order_by(Filing.filing_date.desc())
                .first()
            )

        if prior_filing:
            vals, tags = self._resolve_concept_values(
                cik=cik,
                fiscal_year=prior_filing.fiscal_year,
                accession_number=prior_filing.accession_number,
                cutoff_date=prior_filing.filing_date,
            )
            # Supplement missing prior concepts from comparative facts filed on or before current filing date
            missing_prior_concepts = [c for c in TAG_PRIORITIES if c not in vals]
            if missing_prior_concepts:
                comp_vals, comp_tags = self._resolve_concept_values(
                    cik=cik,
                    fiscal_year=prior_filing.fiscal_year,
                    cutoff_date=current_filing.filing_date,
                )
                for c in missing_prior_concepts:
                    if c in comp_vals:
                        vals[c] = comp_vals[c]
                        tags[c] = f"{comp_tags[c]} (comparative_prior_supplement)"
            if vals:
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
        fiscal_year: int,
    ) -> Dict[str, Any]:
        """Compute all 18 ratios and 8 Beneish components with strict status and reason tracking."""
        res: Dict[str, Any] = {
            "null_reasons": {},
            "feature_statuses": {},
            "inventory_applicable": True,
        }
        reasons = res["null_reasons"]
        statuses = res["feature_statuses"]
        is_pre_xbrl = fiscal_year < 2012

        def set_status(feature_name: str, val: Optional[float], reason: Optional[str] = None):
            if val is not None and not math.isnan(val) and not math.isinf(val):
                res[feature_name] = val
                statuses[feature_name] = "ok"
            else:
                res[feature_name] = None
                reasons[feature_name] = reason or "missing_input"
                if is_financial and (feature_name.startswith("beneish") or feature_name in [
                    "current_ratio", "sales_to_receivables", "inventory_to_assets",
                    "working_capital_to_assets", "receivables_to_assets", "asset_turnover"
                ]):
                    statuses[feature_name] = "not_applicable"
                elif is_pre_xbrl and reason in ["missing_prior_assets", "missing_rec_or_rev", "missing_prior_rev"]:
                    statuses[feature_name] = "pre_xbrl"
                else:
                    statuses[feature_name] = "missing_input"

        # Financial Inputs
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

        # -------------------------------------------------------------
        # 18 CORE RATIOS
        # -------------------------------------------------------------
        # 1. Asset Turnover: Rev / TA
        if rev is not None and ta and ta > 0:
            set_status("asset_turnover", rev / ta)
        else:
            set_status("asset_turnover", None, "missing_rev_or_assets")

        # 2. ROA: NI / TA (Must compute whenever NI and TA exist)
        if ni is not None and ta and ta > 0:
            set_status("roa", ni / ta)
        else:
            set_status("roa", None, "missing_ni_or_assets")

        # 3. Operating Margin: OpInc / Rev (Must compute whenever OpInc and Rev exist)
        if op_inc is not None and rev and rev != 0:
            set_status("operating_margin", op_inc / rev)
        else:
            set_status("operating_margin", None, "missing_opinc_or_rev")

        # 4. Net Margin: NI / Rev (Must compute whenever NI and Rev exist)
        if ni is not None and rev and rev != 0:
            set_status("net_margin", ni / rev)
        else:
            set_status("net_margin", None, "missing_ni_or_rev")

        # 5. Current Ratio: CA / CL
        if ca is not None and cl and cl > 0:
            set_status("current_ratio", ca / cl)
        else:
            set_status("current_ratio", None, "missing_ca_or_cl")

        # 6. Debt to Equity: TL / Equity
        if tl is not None and equity and equity > 0:
            set_status("debt_to_equity", tl / equity)
        else:
            set_status("debt_to_equity", None, "missing_tl_or_equity")

        # 7. Cash to Assets: Cash / TA
        if cash is not None and ta and ta > 0:
            set_status("cash_to_assets", cash / ta)
        else:
            set_status("cash_to_assets", None, "missing_cash_or_ta")

        # 8. Working Capital to Assets: (CA - CL) / TA
        if ca is not None and cl is not None and ta and ta > 0:
            set_status("working_capital_to_assets", (ca - cl) / ta)
        else:
            set_status("working_capital_to_assets", None, "missing_ca_cl_or_ta")

        # 9. CFO to Assets: CFO / TA
        if cfo is not None and ta and ta > 0:
            set_status("cfo_to_assets", cfo / ta)
        else:
            set_status("cfo_to_assets", None, "missing_cfo_or_ta")

        # 10. Sales to Receivables: Rev / Rec
        if rev is not None and rec and rec > 0:
            set_status("sales_to_receivables", rev / rec)
        else:
            set_status("sales_to_receivables", None, "missing_rev_or_rec")

        # 11. Receivables to Assets: Rec / TA
        if rec is not None and ta and ta > 0:
            set_status("receivables_to_assets", rec / ta)
        else:
            set_status("receivables_to_assets", None, "missing_rec_or_ta")

        # 12. Inventory to Assets: Inv / TA
        # SPEC RULE 4: If firm reports no inventory concept at all, set inventory_to_assets = 0.0 and inventory_applicable = false
        if inv is not None and ta and ta > 0:
            res["inventory_applicable"] = True
            set_status("inventory_to_assets", inv / ta)
        elif ta and ta > 0:
            res["inventory_applicable"] = False
            res["inventory_to_assets"] = 0.0
            statuses["inventory_to_assets"] = "ok"
            reasons["inventory_to_assets"] = "zero_inventory_firm"
        else:
            res["inventory_applicable"] = False
            set_status("inventory_to_assets", None, "missing_assets")

        # 13. CapEx to Assets: CapEx / TA
        if capex is not None and ta and ta > 0:
            set_status("capex_to_assets", capex / ta)
        else:
            set_status("capex_to_assets", None, "missing_capex_or_ta")

        # 14. Debt to Assets: (LTD + STD) / TA
        total_debt = ltd + std
        if total_debt > 0 and ta and ta > 0:
            set_status("debt_to_assets", total_debt / ta)
        elif tl is not None and ta and ta > 0:
            set_status("debt_to_assets", tl / ta)
        else:
            set_status("debt_to_assets", None, "missing_debt_or_ta")

        # 15. Cash Flow Margin: CFO / Rev
        if cfo is not None and rev and rev > 0:
            set_status("cash_flow_margin", cfo / rev)
        else:
            set_status("cash_flow_margin", None, "missing_cfo_or_rev")

        # 16. Accruals CF to Assets: (NI - CFO) / TA
        if ni is not None and cfo is not None and ta and ta > 0:
            set_status("accruals_cf_to_assets", (ni - cfo) / ta)
        else:
            set_status("accruals_cf_to_assets", None, "missing_ni_cfo_or_ta")

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
            set_status("accruals_bs_to_assets", (delta_wc - depr) / ta)
        else:
            set_status("accruals_bs_to_assets", None, "missing_bs_accruals_inputs")

        # 18. Asset Growth: (TA - TA_prev) / TA_prev
        if ta is not None and ta_prev and ta_prev > 0:
            set_status("asset_growth", (ta - ta_prev) / ta_prev)
        else:
            set_status("asset_growth", None, "missing_prior_assets")

        # -------------------------------------------------------------
        # BENEISH M-SCORE 8 COMPONENTS & INCLUSION CHECKS
        # -------------------------------------------------------------
        # SPEC RULE 5: SIC 6000-6999 Financial Firms excluded
        if is_financial:
            reasons["beneish"] = "not_applicable_financial_firm"
            reasons["beneish_strict"] = "not_applicable_financial_firm"
            reasons["beneish_neutral"] = "not_applicable_financial_firm"
            statuses["beneish_strict"] = "not_applicable"
            statuses["beneish_neutral"] = "not_applicable"
            for k in [
                "beneish_dsri", "beneish_gmi", "beneish_aqi", "beneish_sgi",
                "beneish_depi", "beneish_sgai", "beneish_lvgi", "beneish_tata"
            ]:
                set_status(k, None, "not_applicable_financial_firm")
            res["beneish_m_score"] = None
            res["beneish_strict"] = None
            res["beneish_neutral"] = None
            res["beneish_n_components"] = 0
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
            set_status("beneish_dsri", (rec / rev) / (rec_prev / rev_prev))
        else:
            set_status("beneish_dsri", None, "missing_rec_or_rev")

        # 2. GMI: ((Rev_prev - COGS_prev) / Rev_prev) / ((Rev - COGS) / Rev)
        # SPEC RULE 3: Do NOT fabricate Gross Profit as Revenues - OperatingExpenses.
        # Use reported COGS or reported GrossProfit.
        gp = curr.get("gross_profit")
        gp_prev = prior.get("gross_profit")
        gm_curr = None
        gm_prev = None

        if cogs is not None and rev and rev > 0:
            gm_curr = (rev - cogs) / rev
        elif gp is not None and rev and rev > 0:
            gm_curr = gp / rev

        if cogs_prev is not None and rev_prev and rev_prev > 0:
            gm_prev = (rev_prev - cogs_prev) / rev_prev
        elif gp_prev is not None and rev_prev and rev_prev > 0:
            gm_prev = gp_prev / rev_prev

        if gm_curr is not None and gm_prev is not None:
            if gm_curr > 0:
                set_status("beneish_gmi", gm_prev / gm_curr)
            elif gm_curr <= 0:
                # Margin severely deteriorated to zero or negative:
                # Set GMI to capped penalty reflecting severe gross margin deterioration
                penalty = max(1.5, min(5.0, gm_prev / 0.02 if gm_prev > 0 else 2.0))
                set_status("beneish_gmi", penalty)
        elif not res.get("inventory_applicable"):
            # Pure service firm with no inventory / COGS reported: neutral index 1.0 (no margin deterioration)
            set_status("beneish_gmi", 1.0, "service_firm_neutral")
        else:
            set_status("beneish_gmi", None, "no_cogs_reported")

        # 3. AQI: (1 - (CA + PPEN) / TA) / (1 - (CA_prev + PPEN_prev) / TA_prev)
        cur_ppen = ppen if ppen is not None else 0.0
        pr_ppen = ppen_prev if ppen_prev is not None else 0.0
        if (
            ta
            and ta > 0
            and ta_prev
            and ta_prev > 0
            and ca is not None
            and ca_prev is not None
        ):
            non_ca_ppen_curr = 1.0 - (ca + cur_ppen) / ta
            non_ca_ppen_prev = 1.0 - (ca_prev + pr_ppen) / ta_prev
            if non_ca_ppen_prev > 0:
                set_status("beneish_aqi", max(0.01, non_ca_ppen_curr / non_ca_ppen_prev))
            else:
                set_status("beneish_aqi", 1.0, "zero_prior_noncurrent_assets")
        else:
            set_status("beneish_aqi", None, "missing_ca_or_ta")

        # 4. SGI: Rev / Rev_prev
        if rev is not None and rev_prev and rev_prev > 0:
            set_status("beneish_sgi", rev / rev_prev)
        else:
            set_status("beneish_sgi", None, "missing_prior_rev")

        # 5. DEPI: Depr_rate_prev / Depr_rate_curr
        # Depr_rate = Depr / (PPEN + Depr)
        if (
            depr is not None
            and depr_prev is not None
            and depr > 0
            and depr_prev > 0
        ):
            denom_curr = cur_ppen + depr
            denom_prev = pr_ppen + depr_prev
            if denom_curr > 0 and denom_prev > 0:
                dr_curr = depr / denom_curr
                dr_prev = depr_prev / denom_prev
                if dr_curr > 0:
                    set_status("beneish_depi", dr_prev / dr_curr)
                else:
                    set_status("beneish_depi", 1.0, "zero_depr_rate")
            else:
                set_status("beneish_depi", 1.0, "zero_depr_or_ppen")
        elif cur_ppen == 0.0 and pr_ppen == 0.0:
            set_status("beneish_depi", 1.0, "zero_tangible_assets_neutral")
        elif (depr is None or depr == 0) and (depr_prev is None or depr_prev == 0):
            set_status("beneish_depi", 1.0, "zero_depreciation_neutral")
        else:
            set_status("beneish_depi", None, "missing_depr_or_ppen")

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
            set_status("beneish_sgai", (sga / rev) / (sga_prev / rev_prev))
        else:
            set_status("beneish_sgai", None, "missing_sga_or_rev")

        # 7. LVGI: Lev_curr / Lev_prev
        # Lev = (LTD + CL) / TA
        curr_cl = cl if cl is not None else 0.0
        prev_cl = cl_prev if cl_prev is not None else 0.0
        if ta and ta > 0 and ta_prev and ta_prev > 0:
            lev_curr = (ltd + curr_cl) / ta
            lev_prev = (ltd_prev + prev_cl) / ta_prev
            if lev_prev > 0:
                set_status("beneish_lvgi", lev_curr / lev_prev)
            else:
                set_status("beneish_lvgi", None, "zero_prior_leverage")
        else:
            set_status("beneish_lvgi", None, "missing_assets")

        # 8. TATA: (NI - CFO) / TA (with secondary balance-sheet based fallback if CFO absent)
        if ni is not None and cfo is not None and ta and ta > 0:
            set_status("beneish_tata", (ni - cfo) / ta)
        elif res.get("accruals_bs_to_assets") is not None:
            set_status("beneish_tata", res["accruals_bs_to_assets"])
            reasons["beneish_tata"] = "bs_accruals_fallback"
        else:
            set_status("beneish_tata", None, "missing_ni_cfo_or_ta")

        # Secondary TATA (Balance-Sheet Based)
        if res.get("accruals_bs_to_assets") is not None:
            res["beneish_tata_bs"] = res["accruals_bs_to_assets"]

        # =========================================================================
        # COMPOSITE BENEISH M-SCORES: (a) beneish_strict and (b) beneish_neutral
        # Model 1 weights:
        # M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI + 0.115*DEPI
        #     - 0.172*SGAI + 4.037*TATA + 0.0327*LVGI
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
        present_comps = [k for k in comp_keys if res.get(k) is not None]
        n_comps = len(present_comps)
        res["beneish_n_components"] = n_comps

        # (a) beneish_strict: ALL 8 components must be present
        if n_comps == 8:
            m_strict = (
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
            if not math.isnan(m_strict) and not math.isinf(m_strict):
                res["beneish_strict"] = m_strict
                res["beneish_m_score"] = m_strict
                statuses["beneish_strict"] = "ok"
                res["beneish_flag_178"] = m_strict > -1.78
                res["beneish_flag_222"] = m_strict > -2.22
            else:
                set_status("beneish_strict", None, "nan_inf")
                res["beneish_m_score"] = None
        else:
            missing_comps = [k for k in comp_keys if res.get(k) is None]
            set_status("beneish_strict", None, f"incomplete_components ({', '.join(missing_comps)})")
            res["beneish_m_score"] = None
            res["beneish_flag_178"] = None
            res["beneish_flag_222"] = None

        # (b) beneish_neutral: missing indices set to neutral (1.0; TATA 0.0)
        # Allows robust multi-year tracking even if 1 or 2 niche tags are missing
        if n_comps > 0:
            dsri_n = res["beneish_dsri"] if res.get("beneish_dsri") is not None else 1.0
            gmi_n = res["beneish_gmi"] if res.get("beneish_gmi") is not None else 1.0
            aqi_n = res["beneish_aqi"] if res.get("beneish_aqi") is not None else 1.0
            sgi_n = res["beneish_sgi"] if res.get("beneish_sgi") is not None else 1.0
            depi_n = res["beneish_depi"] if res.get("beneish_depi") is not None else 1.0
            sgai_n = res["beneish_sgai"] if res.get("beneish_sgai") is not None else 1.0
            lvgi_n = res["beneish_lvgi"] if res.get("beneish_lvgi") is not None else 1.0
            tata_n = res["beneish_tata"] if res.get("beneish_tata") is not None else 0.0

            m_neutral = (
                -4.84
                + 0.920 * dsri_n
                + 0.528 * gmi_n
                + 0.404 * aqi_n
                + 0.892 * sgi_n
                + 0.115 * depi_n
                - 0.172 * sgai_n
                + 4.037 * tata_n
                + 0.0327 * lvgi_n
            )
            if not math.isnan(m_neutral) and not math.isinf(m_neutral):
                res["beneish_neutral"] = m_neutral
                statuses["beneish_neutral"] = "ok"
            else:
                set_status("beneish_neutral", None, "nan_inf")
        else:
            set_status("beneish_neutral", None, "zero_components_present")

        return res
