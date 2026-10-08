# FinGuard-X Feature Specification: Financial Ratios & Beneish M-Score (Sprint A)

This document provides the authoritative mathematical formulas, input XBRL tag priorities, prior-year lag definitions, and null-handling semantics for the **18 core financial features** and the **8 Beneish M-Score components** implemented in FinGuard-X.

---

## 1. Operating Principles & Anti-Leakage Rules

### R3 & DEC-008 Compliance:
1. **Current Year Values ($t$):** Sourced strictly from original filings (`is_original_filing = True`). Subsequent restatements are never used for feature generation.
2. **Prior Year Values ($t-1$):** Sourced strictly from the prior year's original 10-K filing (`prior_original_10k`). A comparative column from the current filing is used strictly as a secondary fallback (`comparative_fallback`) if and only if the prior year's filing is missing from the database. The provenance is explicitly recorded in `prior_val_source`.
3. **No Imputation / No Clipping:** Missing values are recorded as `NULL` with an associated `null_reason` code (`missing_in_xbrl`, `zero_denominator`, `industry_inapplicable`, `prior_filing_missing`). Imputation, winsorization, and scaling occur strictly inside cross-validation training folds during downstream modeling.
4. **Financial Industry Exemption:** Financial institutions (SIC 6000–6999: Commercial Banks, Savings Institutions, Brokers, Insurance) operate with non-comparable asset/liability structures. They are flagged with `beneish_applicable = false`, and Beneish components are stored as `NULL`.

---

## 2. XBRL Tag Priority Maps

To handle US-GAAP taxonomy variation, each financial concept maps to an ordered list of XBRL tags. The engine searches tags in order, selecting the first available non-null fact for that company-year:

| Concept | Primary Tag | Secondary Tags (Priority Order) |
|---|---|---|
| **Total Assets ($TA$)** | `Assets` | `AssetsCurrent` + `AssetsNoncurrent` |
| **Total Liabilities ($TL$)** | `Liabilities` | `LiabilitiesCurrent` + `LiabilitiesNoncurrent` |
| **Stockholders' Equity ($SE$)** | `StockholdersEquity` | `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` |
| **Revenues ($Rev$)** | `RevenueFromContractWithCustomerExcludingAssessedTax` | `Revenues`, `SalesRevenueNet`, `OperatingRevenue`, `SalesRevenueGoodsNet`, `RealEstateRevenueNet` |
| **Cost of Goods Sold ($COGS$)** | `CostOfGoodsAndServicesSold` | `CostOfGoodsSold`, `CostOfRevenue` |
| **Operating Income ($OpInc$)** | `OperatingIncomeLoss` | `GrossProfit` - `SellingGeneralAndAdministrativeExpense` |
| **Net Income ($NI$)** | `NetIncomeLoss` | `ProfitLoss` |
| **Cash & Cash Equivalents ($Cash$)** | `CashAndCashEquivalentsAtCarryingValue` | `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`, `Cash` |
| **Current Assets ($CA$)** | `AssetsCurrent` | — |
| **Current Liabilities ($CL$)** | `LiabilitiesCurrent` | — |
| **Accounts Receivable ($Rec$)** | `AccountsReceivableNetCurrent` | `AccountsAndNotesReceivableNet` |
| **Inventory ($Inv$)** | `InventoryNet` | `InventoryGross` |
| **Gross Profit ($GP$)** | `GrossProfit` | $Rev - COGS$ |
| **PPE Net ($PPEN$)** | `PropertyPlantAndEquipmentNet` | `PropertyPlantAndEquipmentGross` - `AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment` |
| **Depreciation & Amortization ($Depr$)** | `DepreciationDepletionAndAmortization` | `Depreciation`, `DepreciationAndAmortization` |
| **SG&A Expense ($SGA$)** | `SellingGeneralAndAdministrativeExpense` | `GeneralAndAdministrativeExpense` + `SellingAndMarketingExpense` |
| **Long-Term Debt ($LTD$)** | `LongTermDebtNoncurrent` | `LongTermDebt`, `LongTermDebtAndCapitalLeaseObligations` |
| **Short-Term Debt ($STD$)** | `DebtCurrent` | `ShortTermBorrowings`, `LongTermDebtCurrent` |
| **Operating Cash Flow ($CFO$)** | `NetCashProvidedByUsedInOperatingActivities` | — |
| **Capital Expenditures ($CapEx$)** | `PaymentsToAcquirePropertyPlantAndEquipment` | `PaymentsToAcquireProductiveAssets` |

---

## 3. The 8 Beneish M-Score Components

All 8 components are calculated on raw financial statements without scaling:

### 1. Days Sales in Receivables Index (DSRI)
Measures whether receivables are growing disproportionately faster than revenues (a classic indicator of premature revenue recognition or fictitious sales).
$$\text{DSRI} = \frac{\text{Receivables}_t / \text{Revenues}_t}{\text{Receivables}_{t-1} / \text{Revenues}_{t-1}}$$
- If $\text{DSRI} > 1.0$, receivables are accelerating relative to revenue.

### 2. Gross Margin Index (GMI)
Measures the degradation of gross margin from prior year to current year. Firms facing eroding margins have higher incentives to engage in accounting manipulation.
$$\text{GMI} = \frac{(\text{Revenues}_{t-1} - \text{COGS}_{t-1}) / \text{Revenues}_{t-1}}{(\text{Revenues}_t - \text{COGS}_t) / \text{Revenues}_t}$$
- If $\text{GMI} > 1.0$, gross margin has deteriorated in the current period.

### 3. Asset Quality Index (AQI)
Measures the proportion of non-current assets that are not tangible property, plant, and equipment (PPE). Indicates capitalization of intangible costs or deferred expenses.
$$\text{Non-PPE Non-Current Assets}_t = \text{Total Assets}_t - (\text{Current Assets}_t + \text{PPE Net}_t)$$
$$\text{AQI} = \frac{1 - (\text{Current Assets}_t + \text{PPE Net}_t) / \text{Total Assets}_t}{1 - (\text{Current Assets}_{t-1} + \text{PPE Net}_{t-1}) / \text{Total Assets}_{t-1}}$$
- If $\text{AQI} > 1.0$, the firm has increased its capitalization of discretionary expenditures.

### 4. Sales Growth Index (SGI)
Measures top-line revenue growth. High-growth firms facing growth deceleration face severe market pressure to manage earnings.
$$\text{SGI} = \frac{\text{Revenues}_t}{\text{Revenues}_{t-1}}$$
- If $\text{SGI} > 1.0$, revenues have grown YoY.

### 5. Depreciation Index (DEPI)
Measures the effective rate of depreciation. A decrease in depreciation rate indicates that the firm extended useful lives of assets or adopted new, slower depreciation methods to inflate earnings.
$$\text{Depr Rate}_t = \frac{\text{Depreciation}_t}{\text{PPE Net}_t + \text{Depreciation}_t}$$
$$\text{DEPI} = \frac{\text{Depr Rate}_{t-1}}{\text{Depr Rate}_t}$$
- If $\text{DEPI} > 1.0$, the current depreciation rate has slowed.

### 6. Sales, General and Administrative Expenses Index (SGAI)
Compares SG&A expenses relative to sales between years. Decreasing sales accompanied by sticky SG&A costs indicates operating headwinds.
$$\text{SGAI} = \frac{\text{SG\&A}_t / \text{Revenues}_t}{\text{SG\&A}_{t-1} / \text{Revenues}_{t-1}}$$

### 7. Leverage Index (LVGI)
Measures changes in total debt leverage relative to total assets. Increasing debt covenants incentivize earnings management.
$$\text{Lev}_t = \frac{\text{Long-Term Debt}_t + \text{Current Liabilities}_t}{\text{Total Assets}_t}$$
$$\text{LVGI} = \frac{\text{Lev}_t}{\text{Lev}_{t-1}}$$

### 8. Total Accruals to Total Assets (TATA)
Reflects the degree to which net income is driven by accounting accruals rather than cash flow.
- **Primary Definition (Cash-Flow Based):**
  $$\text{TATA}_{\text{CFO}} = \frac{\text{Net Income}_t - \text{CFO}_t}{\text{Total Assets}_t}$$
- **Secondary Definition (Balance-Sheet Based):**
  $$\Delta \text{WC}_t = (\Delta \text{CA}_t - \Delta \text{Cash}_t) - (\Delta \text{CL}_t - \Delta \text{STD}_t)$$
  $$\text{TATA}_{\text{BS}} = \frac{\Delta \text{WC}_t - \text{Depreciation}_t}{\text{Total Assets}_t}$$
*Both definitions are stored. $\text{TATA}_{\text{CFO}}$ serves as the primary component in the Beneish formula.*

---

## 4. Composite Beneish M-Score & Thresholds

The 8-variable Beneish M-Score is defined as:
$$M = -4.84 + 0.920 \cdot \text{DSRI} + 0.528 \cdot \text{GMI} + 0.404 \cdot \text{AQI} + 0.892 \cdot \text{SGI} + 0.115 \cdot \text{DEPI} - 0.172 \cdot \text{SGAI} + 4.037 \cdot \text{TATA} + 0.0327 \cdot \text{LVGI}$$

### Missingness Rule:
If **any** of the 8 components is `NULL`, the composite `beneish_m_score` is stored as `NULL` (no imputation).

### Risk Flags:
- `beneish_flag_178`: `True` if $M > -1.78$ (standard high risk of financial manipulation)
- `beneish_flag_222`: `True` if $M > -2.22$ (conservative / sensitive risk threshold)

---

## 5. The Additional 10 Fundamental Financial Features

Beyond the 8 Beneish components, 10 additional ratios provide broad structural accounting signals:

1. **Asset Turnover:** $\text{Revenues}_t / \text{Total Assets}_t$
2. **Return on Assets (ROA):** $\text{Net Income}_t / \text{Total Assets}_t$
3. **Operating Margin:** $\text{Operating Income}_t / \text{Revenues}_t$
4. **Current Ratio:** $\text{Current Assets}_t / \text{Current Liabilities}_t$
5. **Debt to Equity:** $\text{Total Liabilities}_t / \text{Stockholders' Equity}_t$
6. **Cash to Total Assets:** $\text{Cash}_t / \text{Total Assets}_t$
7. **Working Capital to Total Assets:** $(\text{Current Assets}_t - \text{Current Liabilities}_t) / \text{Total Assets}_t$
8. **Cash Flow to Total Assets:** $\text{CFO}_t / \text{Total Assets}_t$
9. **Sales to Receivables:** $\text{Revenues}_t / \text{Receivables}_t$
10. **Asset Growth:** $(\text{Total Assets}_t - \text{Total Assets}_{t-1}) / \text{Total Assets}_{t-1}$
