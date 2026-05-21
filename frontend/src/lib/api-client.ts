const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// ---------------------------------------------------------------------------
// API Error class
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// Auth helper
// ---------------------------------------------------------------------------

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("auth_token");
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

// ---------------------------------------------------------------------------
// Core fetch wrapper with timeout + retry + auth injection
// ---------------------------------------------------------------------------

const API_TIMEOUT = 10000; // 10 seconds

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);

  try {
    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
        ...options?.headers,
      },
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(
        body.message || body.detail || `Request failed: ${res.status}`,
        res.status,
        body.error,
      );
    }

    // Handle 204 No Content or empty responses
    const text = await res.text();
    if (!text) return undefined as T;
    return JSON.parse(text) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("Request timeout", 408, "TIMEOUT");
    }
    throw new ApiError(
      err instanceof Error ? err.message : "Network error",
      0,
      "NETWORK_ERROR",
    );
  } finally {
    clearTimeout(timeoutId);
  }
}

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

export interface StockPrice {
  symbol: string;
  market: string;
  date: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number;
  change: string;
  change_percent: string;
}

export interface PriceListResponse {
  data: StockPrice[];
  total: number;
}

export interface IndicatorResponse {
  symbol: string;
  indicator: string;
  values: Record<string, (string | null)[]>;
}

// --- Stock Search ---

export interface StockSearchResult {
  symbol: string;
  name: string;
  market: string;
}

// --- Screener ---

export interface ScreenCondition {
  indicator: string;
  params: Record<string, unknown>;
  op: string;
  value: unknown;
}

export interface ScreenResult {
  symbol: string;
  indicator_values: Record<string, string>;
}

export interface ScreenResponse {
  results: ScreenResult[];
  total: number;
}

// --- Notifications ---

export interface NotificationRule {
  id: number;
  name: string;
  rule_type: string;
  symbol: string;
  conditions: Record<string, unknown>;
  is_active: boolean;
}

// --- Financials ---

export interface FinancialRatios {
  symbol: string;
  period: string;
  gross_margin: string | null;
  operating_margin: string | null;
  net_margin: string | null;
  roe: string | null;
  roa: string | null;
  current_ratio: string | null;
  debt_ratio: string | null;
  revenue_growth: string | null;
  net_income_growth: string | null;
}

export interface HealthScore {
  symbol: string;
  period: string;
  total_score: string;
  profitability_score: string;
  efficiency_score: string;
  leverage_score: string;
  growth_score: string;
}

export interface FinancialStatement {
  period: string;
  period_type: string;
  data: Record<string, string>;
}

export interface FullAnalysis {
  financials: {
    symbol: string;
    currency: string;
    income_statements: FinancialStatement[];
    balance_sheets: FinancialStatement[];
    cash_flows: FinancialStatement[];
  };
  ratios: FinancialRatios[];
  health_scores: HealthScore[];
}

// --- Auth ---

export interface AuthUser {
  id: number;
  email: string;
  username: string;
  tier: string;
}

// --- Company Info ---

export interface CompanyInfo {
  symbol: string;
  name: string;
  market: string;
  industry: string;
}

// --- Margin Trading ---

export interface MarginData {
  symbol: string;
  name: string;
  margin_buy: number;
  margin_sell: number;
  margin_balance: number;
  margin_limit: number;
  margin_usage_pct: number;
  short_buy: number;
  short_sell: number;
  short_balance: number;
  short_limit: number;
  short_usage_pct: number;
  offset: number;
  margin_short_ratio: number;
}

// --- Market Overview ---

export interface MarketIndex {
  symbol: string;
  name: string;
  value: string;
  change: string;
  change_percent: string;
}

export interface MarketMover {
  symbol: string;
  name: string;
  market: string;
  close: string;
  change: string;
  change_percent: string;
  volume: number;
}

export interface MarketMoversResponse {
  gainers: MarketMover[];
  losers: MarketMover[];
  most_active: MarketMover[];
  date: string | null;
}

// --- Revenue ---

export interface RevenueRecord {
  period: string;
  revenue: string;
  currency: string;
}

export interface RevenueAnalysis {
  symbol: string;
  latest_revenue: string;
  qoq_growth: string | null;
  yoy_growth: string | null;
  is_revenue_high: boolean;
  is_revenue_low: boolean;
  trend: string;
  consecutive_growth_quarters: number;
  records: RevenueRecord[];
}

// --- Heatmap ---

export interface HeatmapStock {
  symbol: string;
  name: string;
  close: string;
  change_percent: string;
  volume: number;
}

export interface HeatmapSector {
  industry: string;
  stock_count: number;
  avg_change_percent: string;
  total_volume: number;
  stocks: HeatmapStock[];
}

export interface HeatmapResponse {
  sectors: HeatmapSector[];
  date: string | null;
}

// --- Low Base ---

export interface LowBaseScore {
  symbol: string;
  name: string;
  total_score: string;
  valuation_score: string;
  price_position_score: string;
  quality_score: string;
  pe_percentile: string | null;
  ma240_deviation: string | null;
  peg: string | null;
  details: Record<string, unknown>;
}

export interface LowBaseRanking {
  results: LowBaseScore[];
  total_scanned: number;
  total_qualified: number;
}

// --- Institutional Investors ---

export interface InstitutionalData {
  date: string;
  foreign_buy: number;
  foreign_sell: number;
  foreign_net: number;
  trust_buy: number;
  trust_sell: number;
  trust_net: number;
  dealer_buy: number;
  dealer_sell: number;
  dealer_net: number;
  total_net: number;
}

export interface InstitutionalResponse {
  symbol: string;
  data: InstitutionalData[];
}

// --- Backtest ---

export interface StrategyInfo {
  name: string;
  description: string;
  params: Record<string, unknown>;
}

export interface BacktestMetrics {
  total_return: string;
  annualized_return: string;
  max_drawdown: string;
  sharpe_ratio: string;
  win_rate: string;
  total_trades: number;
  profit_factor: string;
}

export interface TradeRecord {
  action: string;
  date: string;
  price: string;
  shares: number;
  reason: string;
}

export interface BacktestResult {
  symbol: string;
  strategy: string;
  metrics: BacktestMetrics;
  equity_curve: string[];
  trades: TradeRecord[];
}

// --- Job Queue ---

export interface JobEnqueueRequest {
  symbol: string;
  job_type?: string;
  strategy?: string;
  strategies?: string[];
  mode?: string;
  params?: Record<string, unknown>;
  param_grid?: Record<string, unknown[]>;
  initial_capital?: number;
  position_size?: number;
  stop_loss?: number | null;
  take_profit?: number | null;
}

export interface JobStatus {
  id: number;
  symbol: string;
  job_type: string;
  status: string;
  progress_pct: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
}

export interface QueueStatus {
  jobs: JobStatus[];
  running_count: number;
  pending_count: number;
}

export interface TradeLogEntry {
  date: string;
  action: string;
  price: number;
  shares: number;
  reason: string;
}

export interface BacktestHistoryItem {
  id: number;
  job_id: number;
  symbol: string;
  strategy_name: string;
  strategy_params: Record<string, unknown>;
  total_return: number;
  annualized_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  win_rate: number;
  total_trades: number;
  profit_factor: number;
  trade_log: TradeLogEntry[] | null;
  equity_curve: number[] | null;
  backtest_type: string;
  composite_mode: string | null;
  date_range_start: string | null;
  date_range_end: string | null;
  buy_hold_return: number | null;
  trading_days: number | null;
  created_at: string;
}

export interface BacktestHistoryResponse {
  results: BacktestHistoryItem[];
  total: number;
}

export interface JobResultResponse {
  job: JobStatus;
  results: BacktestHistoryItem[];
}

// --- Portfolio ---

export interface PortfolioAllocationInput {
  symbol: string;
  weight: number;
  strategy: string;
  params?: Record<string, unknown>;
}

export interface PortfolioBacktestRequest {
  allocations: PortfolioAllocationInput[];
  rebalance_mode?: string;
  rebalance_config?: Record<string, unknown>;
  initial_capital?: number;
}

export interface PortfolioBacktestResponse {
  portfolio_metrics: Record<string, number>;
  individual_metrics: Record<string, Record<string, number>>;
  portfolio_equity_curve: number[];
  individual_equity_curves: Record<string, number[]>;
  trade_log: Record<string, unknown>[];
  rebalance_log: Record<string, unknown>[];
  allocations: PortfolioAllocationInput[];
}

// --- Scanner ---

export interface SignalDetail {
  strategy: string;
  action: string;
  strength: number;
  reason: string;
}

export interface ApiStockSignal {
  symbol: string;
  name: string;
  composite_action: string;
  score: number;
  signals: SignalDetail[];
}

export interface ScanResponse {
  results: ApiStockSignal[];
  scan_date: string;
  total_scanned: number;
  strategies_used: string[];
}

// --- Valuation ---

export interface PriceEstimate {
  model_type: string;
  date: string;
  cheap_price: string | null;
  fair_price: string | null;
  expensive_price: string | null;
  confidence: string;
  details: Record<string, any>;
}

export interface ValuationEstimates {
  symbol: string;
  estimates: PriceEstimate[];
  latest_composite: PriceEstimate | null;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------


export async function fetchPrices(symbol: string, limit = 30): Promise<PriceListResponse> {
  return apiFetch<PriceListResponse>(`${API_BASE}/prices/${symbol}?limit=${limit}`);
}

export async function fetchIndicator(
  symbol: string,
  indicator: string,
  params: Record<string, unknown> = {},
): Promise<IndicatorResponse> {
  return apiFetch<IndicatorResponse>(`${API_BASE}/indicators/calculate`, {
    method: "POST",
    body: JSON.stringify({ symbol, indicator, params }),
  });
}

export async function fetchIndicatorList(): Promise<string[]> {
  const data = await apiFetch<{ indicators: string[] }>(`${API_BASE}/indicators/`);
  return data.indicators;
}

export async function searchStocks(query: string, limit = 10): Promise<StockSearchResult[]> {
  if (!query.trim()) return [];
  try {
    const data = await apiFetch<{ results: StockSearchResult[] }>(
      `${API_BASE}/stocks/search?q=${encodeURIComponent(query)}&limit=${limit}`,
    );
    return data.results;
  } catch {
    return [];
  }
}

export async function screenStocks(
  conditions: ScreenCondition[],
  operator = "AND",
  sortBy?: string,
  limit = 50,
): Promise<ScreenResponse> {
  return apiFetch<ScreenResponse>(`${API_BASE}/screener/screen`, {
    method: "POST",
    body: JSON.stringify({ conditions, operator, sort_by: sortBy, limit }),
  });
}

// --- Notifications ---

export async function fetchNotificationRules(): Promise<NotificationRule[]> {
  const data = await apiFetch<{ rules: NotificationRule[] }>(`${API_BASE}/notifications/rules`);
  return data.rules;
}

export async function createNotificationRule(
  rule: { name: string; rule_type: string; symbol: string; conditions: Record<string, unknown> },
): Promise<NotificationRule> {
  return apiFetch<NotificationRule>(`${API_BASE}/notifications/rules`, {
    method: "POST",
    body: JSON.stringify(rule),
  });
}

export async function deleteNotificationRule(id: number): Promise<void> {
  await apiFetch<void>(`${API_BASE}/notifications/rules/${id}`, { method: "DELETE" });
}

// --- Financials ---

export async function fetchFinancialAnalysis(symbol: string): Promise<FullAnalysis> {
  return apiFetch<FullAnalysis>(`${API_BASE}/financials/${symbol}`);
}

// --- Auth ---

export async function register(email: string, password: string, username: string): Promise<string> {
  const data = await apiFetch<{ access_token: string }>(`${API_BASE}/auth/register`, {
    method: "POST",
    body: JSON.stringify({ email, password, username }),
  });
  return data.access_token;
}

export async function login(email: string, password: string): Promise<string> {
  const data = await apiFetch<{ access_token: string }>(`${API_BASE}/auth/login`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return data.access_token;
}

export async function fetchMe(token: string): Promise<AuthUser> {
  return apiFetch<AuthUser>(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

// --- Company Info ---

export async function fetchCompanyInfo(symbol: string): Promise<CompanyInfo | null> {
  try {
    return await apiFetch<CompanyInfo>(`${API_BASE}/company/${encodeURIComponent(symbol)}`);
  } catch {
    return null;
  }
}

// --- Margin Trading ---

export async function fetchMarginData(symbol: string): Promise<MarginData | null> {
  try {
    return await apiFetch<MarginData>(`${API_BASE}/margin/${encodeURIComponent(symbol)}`);
  } catch {
    return null;
  }
}

// --- Market Overview ---

export async function fetchMarketIndices(): Promise<MarketIndex[]> {
  try {
    const data = await apiFetch<{ indices: MarketIndex[] }>(`${API_BASE}/market/indices`);
    return data.indices;
  } catch {
    return [];
  }
}

export async function fetchMarketMovers(marketFilter?: string, limit = 10): Promise<MarketMoversResponse> {
  const params = new URLSearchParams();
  if (marketFilter) params.set("market_filter", marketFilter);
  params.set("limit", String(limit));
  try {
    return await apiFetch<MarketMoversResponse>(`${API_BASE}/market/movers?${params}`);
  } catch {
    return { gainers: [], losers: [], most_active: [], date: null };
  }
}

// --- Revenue ---

export async function fetchRevenueAnalysis(symbol: string): Promise<RevenueAnalysis | null> {
  try {
    return await apiFetch<RevenueAnalysis>(`${API_BASE}/revenue/${encodeURIComponent(symbol)}`);
  } catch {
    return null;
  }
}

// --- Heatmap ---

export async function fetchHeatmapData(marketFilter?: string): Promise<HeatmapResponse> {
  const params = new URLSearchParams();
  if (marketFilter) params.set("market_filter", marketFilter);
  try {
    return await apiFetch<HeatmapResponse>(`${API_BASE}/heatmap/sectors?${params}`);
  } catch {
    return { sectors: [], date: null };
  }
}

// --- Low Base ---

export async function fetchLowBaseRanking(limit = 20): Promise<LowBaseRanking> {
  return apiFetch<LowBaseRanking>(`${API_BASE}/low-base/scan?limit=${limit}`);
}

export async function fetchLowBaseScore(symbol: string): Promise<LowBaseScore> {
  return apiFetch<LowBaseScore>(`${API_BASE}/low-base/${symbol}`);
}

// --- Institutional Investors ---

export async function fetchInstitutional(
  symbol: string,
  startDate: string,
  endDate: string,
): Promise<InstitutionalData[]> {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
  });
  const json = await apiFetch<InstitutionalResponse>(
    `${API_BASE}/institutional/${encodeURIComponent(symbol)}?${params}`,
  );
  return json.data;
}

// --- Backtest ---

export async function fetchStrategies(): Promise<StrategyInfo[]> {
  const data = await apiFetch<{ strategies: StrategyInfo[] }>(`${API_BASE}/strategies/`);
  return data.strategies;
}

export async function runAutoDiscovery(params: {
  symbol: string;
  initial_capital?: number;
  position_size?: number;
  stop_loss?: number | null;
  take_profit?: number | null;
  start_date?: string | null;
  end_date?: string | null;
}): Promise<any> {
  return apiFetch(`${API_BASE}/backtest/run/auto-discovery`, {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function runBacktest(params: {
  symbol: string;
  strategy: string;
  params?: Record<string, unknown>;
  initial_capital?: number;
  position_size?: number;
  stop_loss?: number | null;
  take_profit?: number | null;
  start_date?: string | null;
  end_date?: string | null;
}): Promise<BacktestResult> {
  return apiFetch<BacktestResult>(`${API_BASE}/backtest/run`, {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// --- Job Queue ---

export async function enqueueBacktestJob(req: JobEnqueueRequest): Promise<JobStatus> {
  return apiFetch<JobStatus>(`${API_BASE}/backtest/jobs`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function fetchQueueStatus(): Promise<QueueStatus> {
  return apiFetch<QueueStatus>(`${API_BASE}/backtest/jobs`);
}

export async function fetchJobResult(jobId: number): Promise<JobResultResponse> {
  return apiFetch<JobResultResponse>(`${API_BASE}/backtest/jobs/${jobId}`);
}

export async function cancelJob(jobId: number): Promise<void> {
  await apiFetch<void>(`${API_BASE}/backtest/jobs/${jobId}`, { method: "DELETE" });
}

export async function fetchBacktestHistory(
  symbol?: string,
  limit?: number,
  offset?: number,
): Promise<BacktestHistoryResponse> {
  const params = new URLSearchParams();
  if (symbol) params.set("symbol", symbol);
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  return apiFetch<BacktestHistoryResponse>(`${API_BASE}/backtest/history?${params}`);
}

export async function fetchBacktestResult(id: number): Promise<BacktestHistoryItem> {
  return apiFetch<BacktestHistoryItem>(`${API_BASE}/backtest/results/${id}`);
}

export async function fetchBestStrategies(symbol: string): Promise<BacktestHistoryResponse> {
  return apiFetch<BacktestHistoryResponse>(
    `${API_BASE}/backtest/history/${encodeURIComponent(symbol)}/best`,
  );
}

// --- Portfolio ---

export async function runPortfolioBacktest(
  req: PortfolioBacktestRequest,
): Promise<PortfolioBacktestResponse> {
  return apiFetch<PortfolioBacktestResponse>(`${API_BASE}/portfolio/backtest`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// --- Scanner ---

export async function runSignalScan(req?: {
  symbols?: string[];
  strategy_keys?: string[];
  limit?: number;
}): Promise<ScanResponse> {
  return apiFetch<ScanResponse>(`${API_BASE}/scanner/scan`, {
    method: "POST",
    body: JSON.stringify(req ?? {}),
  });
}

export async function fetchStockSignals(symbol: string): Promise<ApiStockSignal> {
  return apiFetch<ApiStockSignal>(`${API_BASE}/scanner/${encodeURIComponent(symbol)}`);
}

// --- Valuation ---

export async function fetchValuationEstimates(symbol: string): Promise<ValuationEstimates> {
  return apiFetch<ValuationEstimates>(`${API_BASE}/valuation/${encodeURIComponent(symbol)}/estimates`);
}

// ---------------------------------------------------------------------------
// Journal — Types
// ---------------------------------------------------------------------------

export interface JournalAccount {
  id: number;
  name: string;
  broker: string | null;
  market: "TW" | "US" | "CRYPTO";
  currency: string;
  description: string | null;
  created_at: string;
}

export interface JournalPosition {
  id: number;
  account_id: number;
  symbol: string;
  market: string;
  currency: string;
  quantity: string;        // Decimal as string from backend
  avg_cost_fifo: string | null;
  total_cost: string | null;
  realized_pnl: string;
  is_closed: boolean;
}

export interface JournalAccountDetail {
  account: JournalAccount;
  positions: JournalPosition[];
}

export interface JournalTrade {
  id: number;
  account_id: number;
  symbol: string;
  market: string;
  action: "BUY" | "SELL" | "DIVIDEND" | "SPLIT";
  date: string;
  price: string | null;
  quantity: string | null;
  fee: string;
  tax: string;
  trade_fx_rate: string | null;
  tags: string[];
  note: string | null;
  created_at: string;
}

export interface JournalTradeListResponse {
  total: number;
  items: JournalTrade[];
}

export interface JournalTradeCreate {
  symbol: string;
  market: "TW" | "US" | "CRYPTO";
  action: "BUY" | "SELL" | "DIVIDEND" | "SPLIT";
  date: string;
  price?: string | null;
  quantity?: string | null;
  fee?: string;
  tax?: string;
  trade_fx_rate?: string | null;
  tags?: string[];
  note?: string | null;
  split_ratio?: string | null;
}

export interface JournalAccountCreate {
  name: string;
  broker?: string | null;
  market: "TW" | "US" | "CRYPTO";
  currency: "TWD" | "USD" | "USDT" | "BTC" | "ETH";
  description?: string | null;
}

export interface JournalGroupMember {
  account_id: number;
  target_weight: string | null;
  account: JournalAccount;
}

export interface JournalGroup {
  id: number;
  name: string;
  description: string | null;
  base_currency: string;
  members: JournalGroupMember[];
}

export interface JournalAllocationRule {
  id: number;
  symbol: string;
  target_weight: string;
  lower_threshold: string;
  upper_threshold: string;
  is_active: boolean;
}

export interface JournalRebalanceAlert {
  scope: "account" | "group";
  scope_id: number;
  scope_name: string;
  symbol: string;
  current_weight: string;
  target_weight: string;
  deviation: string;    // positive = over, negative = under
  direction: "over" | "under";
}

export interface JournalAlertsResponse {
  alerts: JournalRebalanceAlert[];
}

// ---------------------------------------------------------------------------
// Journal — API functions
// ---------------------------------------------------------------------------

export async function fetchJournalAccounts(): Promise<JournalAccount[]> {
  return apiFetch<JournalAccount[]>(`${API_BASE}/journal/accounts`);
}

export async function fetchJournalAccount(id: number): Promise<JournalAccountDetail> {
  return apiFetch<JournalAccountDetail>(`${API_BASE}/journal/accounts/${id}`);
}

export async function createJournalAccount(body: JournalAccountCreate): Promise<JournalAccount> {
  return apiFetch<JournalAccount>(`${API_BASE}/journal/accounts`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchJournalTrades(
  accountId: number,
  params?: { symbol?: string; page?: number; page_size?: number },
): Promise<JournalTradeListResponse> {
  const qs = new URLSearchParams();
  if (params?.symbol) qs.set("symbol", params.symbol);
  if (params?.page !== undefined) qs.set("page", String(params.page));
  if (params?.page_size) qs.set("page_size", String(params.page_size));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch<JournalTradeListResponse>(
    `${API_BASE}/journal/accounts/${accountId}/trades${query}`,
  );
}

export async function createJournalTrade(
  accountId: number,
  body: JournalTradeCreate,
): Promise<JournalTrade> {
  return apiFetch<JournalTrade>(`${API_BASE}/journal/accounts/${accountId}/trades`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchJournalGroups(): Promise<JournalGroup[]> {
  return apiFetch<JournalGroup[]>(`${API_BASE}/journal/groups`);
}

export async function fetchJournalGroup(id: number): Promise<JournalGroup> {
  return apiFetch<JournalGroup>(`${API_BASE}/journal/groups/${id}`);
}

export async function createJournalGroup(body: {
  name: string;
  description?: string | null;
  base_currency?: string;
  members?: { account_id: number; target_weight?: string | null }[];
}): Promise<JournalGroup> {
  return apiFetch<JournalGroup>(`${API_BASE}/journal/groups`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchJournalAlerts(): Promise<JournalAlertsResponse> {
  return apiFetch<JournalAlertsResponse>(`${API_BASE}/journal/alerts`);
}

// ---------------------------------------------------------------------------
// Holdings — Types (Phase 3, /holdings/* endpoints)
//
// Decimal-as-string convention: backend serializes every Decimal column
// (qty, price, fee, tax, avg_cost, realized_pnl, etc.) via
// @field_serializer(when_used="json"). Frontend MUST treat these as
// `string` and call `Number(...)` only at the render boundary.
//
// Important alignment notes vs. plain spec:
//   - AccountResponse carries `market` + `description` (not user_id /
//     updated_at). Account creation REQUIRES `market`.
//   - TradeCreateRequest uses `qty` on the wire (not `quantity`). The
//     response payload uses `quantity` (ORM column name). The PATCH body
//     accepts EITHER (service maps qty -> quantity). We expose the wire
//     shape verbatim — `qty` on create, `quantity` on the row.
//   - PositionResponse uses `qty` (NOT `quantity`), exposes `total_cost`
//     and `price_as_of`, and `avg_cost` may be null. `is_closed` is
//     present.
//   - GET /holdings/positions returns an envelope { account_id, positions }
//     (not a bare array).
//   - GET /holdings/positions/{account_id}/{symbol} REQUIRES `market`
//     query param (composite uniqueness key).
//   - GET /holdings/trades REQUIRES `account_id` query param.
//   - DividendCreateRequest accepts `ratio` (STOCK branch). Response
//     carries `total_amount` + `net_amount` as computed fields.
//   - DELETE /holdings/dividends/{id} returns 204 (apiFetch handles it).
// ---------------------------------------------------------------------------

export type HoldingMarket = "TW_TWSE" | "TW_TPEX" | "US_NYSE" | "US_NASDAQ";
export type HoldingTradeAction = "BUY" | "SELL";
export type HoldingDividendType = "CASH" | "STOCK";

// ── Accounts ───────────────────────────────────────────────────────────────

export interface HoldingAccount {
  id: number;
  name: string;
  market: HoldingMarket;
  broker: string | null;
  currency: string;
  description: string | null;
  created_at: string;
}

export interface HoldingAccountCreateRequest {
  name: string;
  market: HoldingMarket;
  broker?: string | null;
  currency?: string;
  description?: string | null;
}

export interface HoldingAccountUpdateRequest {
  name?: string;
  market?: HoldingMarket;
  broker?: string | null;
  currency?: string;
  description?: string | null;
}

// ── Trades ─────────────────────────────────────────────────────────────────

export interface HoldingTrade {
  id: number;
  account_id: number;
  symbol: string;
  market: HoldingMarket;
  action: string;            // backend returns the raw string ("BUY"/"SELL")
  trade_date: string;        // ISO date (YYYY-MM-DD)
  price: string | null;      // Decimal-as-string
  quantity: string | null;   // ORM column name in response
  fee: string;
  tax: string;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface HoldingTradeCreateRequest {
  account_id: number;
  action: HoldingTradeAction;
  symbol: string;
  market: HoldingMarket;
  qty: string;               // wire uses `qty` on POST
  price: string;
  fee?: string;
  tax?: string;
  trade_date?: string | null;
  note?: string | null;
}

export interface HoldingTradeUpdateRequest {
  account_id?: number;
  action?: HoldingTradeAction;
  symbol?: string;
  market?: HoldingMarket;
  qty?: string;
  price?: string;
  fee?: string;
  tax?: string;
  trade_date?: string | null;
  note?: string | null;
}

// ── Positions (read-only, derived) ─────────────────────────────────────────

export interface HoldingPosition {
  account_id: number;
  symbol: string;
  market: HoldingMarket;
  currency: string;
  qty: string;
  avg_cost: string | null;
  total_cost: string | null;
  realized_pnl: string;
  last_price: string | null;
  prev_close: string | null;
  price_as_of: string | null;
  unrealized_pnl: string | null;
  unrealized_pnl_pct: string | null;
  daily_change: string | null;
  daily_change_pct: string | null;
  is_closed: boolean;
}

export interface HoldingPositionListResponse {
  account_id: number | null;
  positions: HoldingPosition[];
}

// ── Summary ────────────────────────────────────────────────────────────────

export interface HoldingSummary {
  total_cost: string;
  total_value: string;
  total_unrealized_pnl: string;
  total_daily_change: string;
  gain_simple: string;
  gain_simple_pct: string;
  position_count: number;
  account_count: number;
}

// ── Dividends ──────────────────────────────────────────────────────────────

export interface HoldingDividend {
  id: number;
  account_id: number;
  symbol: string;
  market: HoldingMarket;
  dividend_type: string;       // "CASH" | "STOCK" — backend returns raw str
  ex_dividend_date: string;
  pay_date: string | null;
  amount_per_share: string;
  quantity_at_record: string;
  currency: string;
  withholding_tax: string;
  total_amount: string;        // computed_field
  net_amount: string;          // computed_field
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface HoldingDividendCreateRequest {
  account_id: number;
  symbol: string;
  market: HoldingMarket;
  dividend_type: HoldingDividendType;
  ex_dividend_date: string;
  pay_date?: string | null;
  amount_per_share?: string | null;     // required for CASH
  quantity_at_record: string;
  ratio?: string | null;                // required for STOCK
  currency?: string;
  withholding_tax?: string;
  note?: string | null;
}

export interface HoldingDividendUpdateRequest {
  note?: string | null;
  pay_date?: string | null;
  withholding_tax?: string;
}

// ── CSV Import (Phase 4) ──────────────────────────────────────────────────

/**
 * One row in an ImportResult — successful preview rows have `error=null`,
 * failed rows have `error` populated with a snake_case identifier
 * (e.g. "invalid_action", "dividend_actions_not_supported").
 *
 * All numeric fields are echoed back as strings (not parsed) so the
 * frontend preview table renders the verbatim CSV value.
 */
export interface ImportResultRow {
  row_index: number;
  action: string | null;
  symbol: string | null;
  quantity: string | null;
  price: string | null;
  trade_date: string | null;
  error: string | null;
}

/**
 * Result of a CSV import — same shape for dry-run and commit. When
 * `dry_run=false` the only valid outcomes are
 * `failed_rows == 0 && successful_rows == parsed_rows` (full commit)
 * or `successful_rows == 0` (atomic rollback).
 */
export interface ImportResult {
  parsed_rows: number;
  successful_rows: number;
  failed_rows: number;
  errors: ImportResultRow[];
  dry_run: boolean;
}

// ---------------------------------------------------------------------------
// Holdings — API functions
// ---------------------------------------------------------------------------

// ── Accounts ───────────────────────────────────────────────────────────────

export async function listHoldingAccounts(): Promise<HoldingAccount[]> {
  return apiFetch<HoldingAccount[]>(`${API_BASE}/holdings/accounts`);
}

export async function createHoldingAccount(
  body: HoldingAccountCreateRequest,
): Promise<HoldingAccount> {
  return apiFetch<HoldingAccount>(`${API_BASE}/holdings/accounts`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getHoldingAccount(id: number): Promise<HoldingAccount> {
  return apiFetch<HoldingAccount>(`${API_BASE}/holdings/accounts/${id}`);
}

export async function updateHoldingAccount(
  id: number,
  body: HoldingAccountUpdateRequest,
): Promise<HoldingAccount> {
  return apiFetch<HoldingAccount>(`${API_BASE}/holdings/accounts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteHoldingAccount(id: number): Promise<void> {
  await apiFetch<{ ok: boolean }>(`${API_BASE}/holdings/accounts/${id}`, {
    method: "DELETE",
  });
}

// ── Trades ─────────────────────────────────────────────────────────────────

export async function listHoldingTrades(
  accountId: number,
  limit?: number,
  offset?: number,
): Promise<HoldingTrade[]> {
  const qs = new URLSearchParams({ account_id: String(accountId) });
  if (limit !== undefined) qs.set("limit", String(limit));
  if (offset !== undefined) qs.set("offset", String(offset));
  return apiFetch<HoldingTrade[]>(
    `${API_BASE}/holdings/trades?${qs.toString()}`,
  );
}

export async function createHoldingTrade(
  body: HoldingTradeCreateRequest,
): Promise<HoldingTrade> {
  return apiFetch<HoldingTrade>(`${API_BASE}/holdings/trades`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getHoldingTrade(id: number): Promise<HoldingTrade> {
  return apiFetch<HoldingTrade>(`${API_BASE}/holdings/trades/${id}`);
}

export async function updateHoldingTrade(
  id: number,
  body: HoldingTradeUpdateRequest,
): Promise<HoldingTrade> {
  return apiFetch<HoldingTrade>(`${API_BASE}/holdings/trades/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteHoldingTrade(id: number): Promise<void> {
  await apiFetch<{ ok: boolean }>(`${API_BASE}/holdings/trades/${id}`, {
    method: "DELETE",
  });
}

// ── Positions ──────────────────────────────────────────────────────────────

export async function listHoldingPositions(
  accountId?: number,
): Promise<HoldingPositionListResponse> {
  const qs = new URLSearchParams();
  if (accountId !== undefined) qs.set("account_id", String(accountId));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch<HoldingPositionListResponse>(
    `${API_BASE}/holdings/positions${query}`,
  );
}

export async function getHoldingPosition(
  accountId: number,
  symbol: string,
  market: HoldingMarket,
): Promise<HoldingPosition> {
  const qs = new URLSearchParams({ market });
  return apiFetch<HoldingPosition>(
    `${API_BASE}/holdings/positions/${accountId}/${encodeURIComponent(symbol)}?${qs.toString()}`,
  );
}

// ── Summary ────────────────────────────────────────────────────────────────

export async function getUserHoldingSummary(): Promise<HoldingSummary> {
  return apiFetch<HoldingSummary>(`${API_BASE}/holdings/summary`);
}

export async function getAccountHoldingSummary(
  accountId: number,
): Promise<HoldingSummary> {
  return apiFetch<HoldingSummary>(`${API_BASE}/holdings/summary/${accountId}`);
}

// ── Dividends ──────────────────────────────────────────────────────────────

export async function listHoldingDividends(
  accountId?: number,
  limit?: number,
  offset?: number,
): Promise<HoldingDividend[]> {
  const qs = new URLSearchParams();
  if (accountId !== undefined) qs.set("account_id", String(accountId));
  if (limit !== undefined) qs.set("limit", String(limit));
  if (offset !== undefined) qs.set("offset", String(offset));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch<HoldingDividend[]>(
    `${API_BASE}/holdings/dividends${query}`,
  );
}

export async function createHoldingDividend(
  body: HoldingDividendCreateRequest,
): Promise<HoldingDividend> {
  return apiFetch<HoldingDividend>(`${API_BASE}/holdings/dividends`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getHoldingDividend(id: number): Promise<HoldingDividend> {
  return apiFetch<HoldingDividend>(`${API_BASE}/holdings/dividends/${id}`);
}

export async function updateHoldingDividend(
  id: number,
  body: HoldingDividendUpdateRequest,
): Promise<HoldingDividend> {
  return apiFetch<HoldingDividend>(`${API_BASE}/holdings/dividends/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteHoldingDividend(id: number): Promise<void> {
  await apiFetch<void>(`${API_BASE}/holdings/dividends/${id}`, {
    method: "DELETE",
  });
}

// ── CSV Import (Phase 4) ──────────────────────────────────────────────────

/**
 * Bulk-import trades from a broker CSV.
 *
 * Wire shape: raw `text/csv` body (NOT multipart) — keeps us off the
 * `python-multipart` dependency on the backend. Metadata (`account_id`,
 * `dry_run`) goes on the query string. The browser sets the boundary
 * we want when we pass a `Blob` directly.
 *
 * Use `dry_run=true` first to render a preview table, then call again
 * with `dry_run=false` to commit. Backend is atomic: on any row failure
 * with `dry_run=false`, ZERO rows commit.
 */
export async function importHoldingsCsv(
  accountId: number,
  file: Blob | File | string,
  dryRun: boolean,
): Promise<ImportResult> {
  const qs = new URLSearchParams({
    account_id: String(accountId),
    dry_run: dryRun ? "true" : "false",
  });
  const url = `${API_BASE}/holdings/imports/csv?${qs.toString()}`;

  // Normalise to a Blob with the text/csv content-type. Strings get
  // wrapped; Blobs / Files pass through but we re-wrap to FORCE the
  // mime type (some `File` instances from <input type="file"> arrive
  // with `application/vnd.ms-excel` which our endpoint *does* accept,
  // but pinning text/csv keeps the contract obvious).
  const body =
    typeof file === "string"
      ? new Blob([file], { type: "text/csv" })
      : new Blob([file], { type: "text/csv" });

  // We bypass `apiFetch` because that wrapper hard-codes
  // `Content-Type: application/json`. Reuse `getAuthHeaders()` for the
  // bearer token, then attach our own text/csv content-type.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);
  try {
    const res = await fetch(url, {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "text/csv",
        ...getAuthHeaders(),
      },
      body,
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new ApiError(
        errBody.message || errBody.detail || `Request failed: ${res.status}`,
        res.status,
        errBody.error,
      );
    }

    const text = await res.text();
    if (!text) {
      throw new ApiError("Empty response", 500, "EMPTY_RESPONSE");
    }
    return JSON.parse(text) as ImportResult;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("Request timeout", 408, "TIMEOUT");
    }
    throw new ApiError(
      err instanceof Error ? err.message : "Network error",
      0,
      "NETWORK_ERROR",
    );
  } finally {
    clearTimeout(timeoutId);
  }
}

// ---------------------------------------------------------------------------
// Holdings — CSV Exports (Phase 4, /holdings/exports/*.csv)
//
// These endpoints return raw CSV (text/csv; charset=utf-8) with a BOM prefix
// for Excel compatibility. We need the BINARY body (`Blob`), not JSON, so
// we bypass the apiFetch wrapper and hit `fetch` directly while re-using
// `getAuthHeaders()` for the bearer token.
//
// Tier gate (PRO only — `tax_export` feature in tier_limits.yaml). FREE / BASIC
// users will receive 403 `feature_unavailable:tax_export`; we translate that
// to an ApiError so callers can render the same "升級 Pro 解鎖此功能" toast
// they already use elsewhere.
// ---------------------------------------------------------------------------

/**
 * Helper — fetch a CSV endpoint, returning the response body as a Blob.
 *
 * Centralised so all four export calls share the same error-handling and
 * auth-injection. On non-2xx the function inspects the JSON envelope
 * (`{ message }`) to surface a structured `ApiError`; on network failure
 * it falls back to a NETWORK_ERROR code.
 */
async function fetchCsvBlob(url: string): Promise<Blob> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);
  try {
    const res = await fetch(url, {
      method: "GET",
      signal: controller.signal,
      headers: {
        ...getAuthHeaders(),
      },
    });
    if (!res.ok) {
      // Backend always emits a JSON error envelope (`error_handler.py`).
      // Be defensive in case a future change ships an HTML 500 page.
      const body = await res.json().catch(() => ({}));
      throw new ApiError(
        body.message || body.detail || `Request failed: ${res.status}`,
        res.status,
        body.error,
      );
    }
    return await res.blob();
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("Request timeout", 408, "TIMEOUT");
    }
    throw new ApiError(
      err instanceof Error ? err.message : "Network error",
      0,
      "NETWORK_ERROR",
    );
  } finally {
    clearTimeout(timeoutId);
  }
}

export interface HoldingExportTradeOptions {
  accountId?: number;
  dateFrom?: string;            // ISO YYYY-MM-DD (inclusive)
  dateTo?: string;
}

export interface HoldingExportPositionOptions {
  accountId?: number;
}

export interface HoldingExportDividendOptions {
  accountId?: number;
  dateFrom?: string;
  dateTo?: string;
}

export async function exportHoldingsTrades(
  opts: HoldingExportTradeOptions = {},
): Promise<Blob> {
  const qs = new URLSearchParams();
  if (opts.accountId !== undefined) qs.set("account_id", String(opts.accountId));
  if (opts.dateFrom) qs.set("date_from", opts.dateFrom);
  if (opts.dateTo) qs.set("date_to", opts.dateTo);
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return fetchCsvBlob(`${API_BASE}/holdings/exports/trades.csv${query}`);
}

export async function exportHoldingsPositions(
  opts: HoldingExportPositionOptions = {},
): Promise<Blob> {
  const qs = new URLSearchParams();
  if (opts.accountId !== undefined) qs.set("account_id", String(opts.accountId));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return fetchCsvBlob(`${API_BASE}/holdings/exports/positions.csv${query}`);
}

export async function exportHoldingsDividends(
  opts: HoldingExportDividendOptions = {},
): Promise<Blob> {
  const qs = new URLSearchParams();
  if (opts.accountId !== undefined) qs.set("account_id", String(opts.accountId));
  if (opts.dateFrom) qs.set("date_from", opts.dateFrom);
  if (opts.dateTo) qs.set("date_to", opts.dateTo);
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return fetchCsvBlob(`${API_BASE}/holdings/exports/dividends.csv${query}`);
}

export async function exportHoldingsSummary(): Promise<Blob> {
  return fetchCsvBlob(`${API_BASE}/holdings/exports/summary.csv`);
}

/**
 * Trigger a browser download for a Blob by clicking a hidden anchor.
 *
 * Uses `URL.createObjectURL` + `<a download>` (the cross-browser idiom
 * for synthetic downloads). The ObjectURL is revoked synchronously
 * after `click()`; the browser has already started the download by then.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  if (typeof document === "undefined" || typeof URL === "undefined") return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
