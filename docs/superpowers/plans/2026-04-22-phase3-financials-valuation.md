# Phase 3: Financials + Valuation — Implementation Plan

**Goal:** Implement financial statement analysis (Income Statement, Balance Sheet, Cash Flow) and stock valuation models (PE, DDM, DCF).

**Architecture:** Financial data is fetched from TWSE MOPS (Taiwan) and SEC EDGAR (US). Valuation models use this data to estimate "fair value".

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, yfinance (for US financials), SEC API (optional), next.js.

---

## File Structure (Phase 3 additions)

```
backend/
├── app/
│   ├── models/
│   │   └── financial.py          # FinancialStatement + FinancialRatio models
│   ├── schemas/
│   │   ├── financial.py          # Financial schemas
│   │   └── valuation.py          # Valuation model schemas
│   ├── api/v1/
│   │   ├── financials.py         # Financials endpoints
│   │   └── valuation_models.py   # Valuation model endpoints
│   ├── modules/
│   │   ├── financial_analysis/
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # FinancialDataProvider protocol
│   │   │   ├── mops_parser.py    # TWSE MOPS parser (Monthly/Quarterly)
│   │   │   ├── sec_parser.py     # SEC EDGAR parser
│   │   │   ├── ratios.py         # Ratio calculation engine
│   │   │   └── cashflow.py       # Cashflow & FCF analysis
│   │   └── price_estimator/
│   │       ├── __init__.py
│   │       ├── pe_model.py       # PE Band valuation
│   │       ├── ddm.py            # Dividend Discount Model
│   │       ├── dcf.py            # Discounted Cash Flow
│   │       └── composite.py      # Composite valuation engine
│   └── services/
│       └── financial_service.py  # Orchestrates fetch -> calculate -> save
├── tests/
│   ├── unit/modules/
│   │   ├── test_mops_parser.py
│   │   ├── test_sec_parser.py
│   │   ├── test_financial_ratios.py
│   │   ├── test_price_estimator.py
│   │   └── test_dcf_model.py
│   └── integration/
│       ├── test_financials_api.py
│       └── test_valuation_api.py
```

---

## Task 1: Financial Data Models & Schemas

- [ ] **Step 1.1: Create financial models**
    - `FinancialStatement`: Store raw BS/IS/CF data points.
    - `FinancialRatio`: Store calculated ROE, GPM, etc.
- [ ] **Step 1.2: Create Pydantic schemas for financials and valuation outputs.**
- [ ] **Step 1.3: Run migrations via Alembic.**

## Task 2: Taiwan Financials (MOPS)

- [ ] **Step 2.1: Implement MOPS Parser**
    - Monthly revenue fetching (OpenAPI or Web Scraping).
    - Quarterly reports (Seasonality adjustment).
- [ ] **Step 2.2: Add unit tests for MOPS parsing.**

## Task 3: US Financials (SEC/yfinance)

- [ ] **Step 3.1: Implement SEC/yfinance Parser**
    - Use `yfinance` to fetch fundamental data (fastest for Phase 3).
    - Fallback to SEC EDGAR API if needed.
- [ ] **Step 3.2: Add unit tests for US financial data fetching.**

## Task 4: Ratio & Cashflow Analysis

- [ ] **Step 4.1: Implement Ratio Engine**
    - Profitability: ROE, ROA, GPM, OPM, NPM.
    - Efficiency: Asset Turnover, Inventory Turnover.
    - Solvency: Current Ratio, Debt-to-Equity.
- [ ] **Step 4.2: Implement Cashflow Analysis**
    - Free Cash Flow (OCF - CapEx).
    - Cash Conversion Cycle.

## Task 5: Price Estimation Models

- [ ] **Step 5.1: Implement PE/PB Band Model**
    - Historical PE/PB range + Forward EPS/BPS.
- [ ] **Step 5.2: Implement DCF (Discounted Cash Flow)**
    - Growth stage + Terminal value.
- [ ] **Step 5.3: Implement DDM (Dividend Discount Model)**
    - For stable dividend payers.
- [ ] **Step 5.4: Implement Composite Engine**
    - Weighted average of multiple models.

## Task 6: API Integration

- [ ] **Step 6.1: Add `financials` and `valuation` endpoints.**
- [ ] **Step 6.2: Add integration tests for the new endpoints.**

## Task 7: Frontend Financials & Valuation Dashboard

- [ ] **Step 7.1: Financials Page**
    - Multi-period comparison table.
    - Growth charts (Revenue, Net Income).
- [ ] **Step 7.2: Valuation Dashboard**
    - Fair value "speedometer".
    - Sensitivity analysis for DCF parameters.

## Task 8: (Maintenance) Frontend Test Infrastructure

- [ ] **Step 8.1: Setup Vitest properly and add basic component tests to reach coverage goals.**
