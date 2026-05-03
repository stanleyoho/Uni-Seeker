# API & Page Mapping

## Overview
此文件將前端頁面與其使用的後端 API 端點及資料模型進行對應，以確保開發的清晰度和一致性。

## Frontend Pages & API Consumption

### Page: Homepage (`/`)
- **API Endpoints Used:**
  - `GET /api/v1/market/indices` (via `useMarketIndices` hook)
  - `GET /api/v1/market/movers` (via `useMarketMovers` hook)
  - `GET /api/v1/market/heatmap` (via `useHeatmap` hook)
- **Data Models:** `MarketIndex`, `MarketMover`, `HeatmapSector`

### Page: Stock Detail (`/stocks/[symbol]`)
- **API Endpoints Used:**
  - `GET /api/v1/prices/{symbol}?interval={interval}` (via `usePrices` hook)
  - `GET /api/v1/company/{symbol}` (via `useCompanyInfo` hook)
  - `GET /api/v1/stocks/{symbol}/margin` (via `useMarginData` hook, conditional)
  - `GET /api/v1/stocks/{symbol}/revenue` (via `useRevenue` hook, conditional)
- **Data Models:** `StockPrice`, `CompanyInfo`, `MarginData`, `RevenueAnalysis`

### Page: Research Screener (`/research`)
- **API Endpoints Used:**
  - `POST /api/v1/screener/stocks` (via `screenStocks` function)
- **Data Models:** `ScreenCondition`, `ScreenResult`

### Page: Research Scanner (`/research/scanner`)
- **API Endpoints Used:**
  - `GET /api/v1/scanner/run` (via `useRunScan` hook)
- **Data Models:** `ScanResult`, `SignalAction`

### Page: Research Low Base (`/research/low-base`)
- **API Endpoints Used:**
  - `GET /api/v1/ranking/low-base` (via `useLowBaseRanking` hook)
- **Data Models:** `LowBaseScore`, `LowBaseResult`

### Page: Research Compare (`/research/compare`)
- **API Endpoints Used:**
  - `GET /api/v1/stocks/search` (via `searchStocks` function)
  - `GET /api/v1/prices/{symbol}?interval=1` (via `usePrices` hook)
  - `GET /api/v1/company/{symbol}` (via `useCompanyInfo` hook)
  - `GET /api/v1/financials/{symbol}` (via `useFinancialAnalysis` hook)
- **Data Models:** `StockSearchResult`, `StockPrice`, `CompanyInfo`, `FinancialAnalysis`, `FinancialRatios`

### Page: Portfolio Watchlist (`/portfolio`)
- **API Endpoints Used:**
  - `GET /api/v1/prices/{symbol}?interval=1` (via `usePrices` hook)
  - `GET /api/v1/watchlist` (via `useWatchlist` hook)
- **Data Models:** `WatchlistItem`, `StockPrice`

### Page: Portfolio Backtest (`/portfolio/backtest`)
- **API Endpoints Used:**
  - `POST /api/v1/backtest/run` (via `useRunBacktest` hook)
- **Data Models:** `BacktestRequest`, `BacktestResult`

### Page: Alerts (`/alerts`)
- **API Endpoints Used:**
  - `GET /api/v1/notifications/rules` (via `useNotifications` hook)
  - `POST /api/v1/notifications/rules` (via `addRule` in `useNotifications` hook)
  - `DELETE /api/v1/notifications/rules/{id}` (via `removeRule` in `useNotifications` hook)
  - `PUT /api/v1/notifications/rules/{id}/toggle` (via `toggleRule` in `useNotifications` hook)
- **Data Models:** `ScreenCondition`, `NotificationRule`

### Page: Heatmap (`/heatmap`)
- **API Endpoints Used:**
  - `GET /api/v1/market/heatmap` (via `useHeatmap` hook)
- **Data Models:** `HeatmapSector`

### Page: Institutional Flows (`/institutional`)
- **API Endpoints Used:**
  - `GET /api/v1/institutional?symbol={symbol}&start_date={start}&end_date={end}` (via `useInstitutional` hook)
- **Data Models:** `InstitutionalData`

## Unused API Endpoints
(None identified. Previously listed endpoints were found to be non-existent or deprecated.)

## Precision Handling
- **Status:** FIXED
- **Approach:** Standardized on using `Decimal` in the backend with a custom `PlainSerializer` (`DecimalStr`) to ensure all financial values are transmitted as `string` in JSON.
- **Frontend:** Updated interfaces in `frontend/src/lib/api-client.ts` to use `string` for price-related fields, avoiding JavaScript's floating-point precision issues during transport. Components use `parseFloat` or `useLocaleFormat` for display.
