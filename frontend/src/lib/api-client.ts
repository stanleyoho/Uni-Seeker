import type { components } from "./api/generated/schema";

type Schemas = components["schemas"];

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

// Market data + scanner + screener types — sourced from generated OpenAPI
// schema (E2E-1 wire-up W3). IndicatorResponse stays handwritten because
// the indicators endpoint returns an inline shape with no named schema.

export type StockPrice = Schemas["StockPriceResponse"];
export type PriceListResponse = Schemas["StockPriceListResponse"];

export interface IndicatorResponse {
  symbol: string;
  indicator: string;
  values: Record<string, (string | null)[]>;
}

// --- Stock Search ---

export type StockSearchResult = Schemas["StockSearchResult"];

// --- Screener ---

export type ScreenCondition = Schemas["ConditionSchema"];
export type ScreenResult = Schemas["ScreenResultItem"];
export type ScreenResponse = Schemas["ScreenResponse"];

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

export type MarketIndex = Schemas["MarketIndex"];
export type MarketMover = Schemas["MarketMover"];
export type MarketMoversResponse = Schemas["MarketMoversResponse"];

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

export type HeatmapStock = Schemas["HeatmapStock"];
export type HeatmapSector = Schemas["HeatmapSector"];
export type HeatmapResponse = Schemas["HeatmapResponse"];

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
// Types sourced from the generated OpenAPI schema (E2E-1 wire-up W2).
// Drift between backend Pydantic schemas and these aliases is caught
// by the schema-gate CI workflow.

export type PortfolioAllocationInput = Schemas["PortfolioAllocationInput"];
export type PortfolioBacktestRequest = Schemas["PortfolioBacktestRequest"];
export type PortfolioBacktestResponse = Schemas["PortfolioBacktestResponse"];

// --- Scanner ---

export type SignalDetail = Schemas["SignalDetail"];
export type ApiStockSignal = Schemas["StockSignalResponse"];
export type ScanResponse = Schemas["ScanResponse"];

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
// Watchlist — Types + API functions (/watchlist endpoints, WATCH-001)
//
// Backend contract (app/api/v1/watchlist.py):
//   GET    /watchlist/            → list[WatchlistItemResponse]
//   POST   /watchlist/            → 201 WatchlistItemResponse, body { symbol }
//                                   - 403 watchlist_limit_exceeded (Free tier cap=10)
//                                   - 409 watchlist_already_exists
//                                   - 404 stock_not_found
//   DELETE /watchlist/{symbol}    → 200 { ok: true }  (NOT 204)
//
// Trailing-slash note: backend uses @router.get("/") + prefix="/watchlist",
// so the canonical path is /watchlist/ — hitting /watchlist would 307 and
// strip the Authorization header. We always include the trailing slash on
// the collection endpoint.
// ---------------------------------------------------------------------------

export interface WatchlistItem {
  id: number;
  symbol: string;
  /**
   * Joined from stocks.name on the server (Round 6). May be null if the
   * stock row was deleted out-of-band — callers should fall back to
   * `symbol` for display.
   */
  stock_name: string | null;
  created_at: string;
}

/** Per-symbol failure returned inside a bulk-add response (Round 6). */
export interface WatchlistBulkAddError {
  symbol: string;
  /** snake_case: `stock_not_found` | `invalid_symbol` | `internal_error` */
  reason: string;
}

/**
 * Envelope for POST /watchlist/bulk (Round 6).
 *
 * The endpoint NEVER returns 4xx for per-row issues — only quota
 * (403 limit_exceeded:max_watchlist) and validation (422) and auth (401)
 * can short-circuit. Per-row issues land in `errors[]`.
 */
export interface WatchlistBulkAddResponse {
  added: WatchlistItem[];
  skipped_duplicates: string[];
  errors: WatchlistBulkAddError[];
}

export async function listWatchlist(): Promise<WatchlistItem[]> {
  return apiFetch<WatchlistItem[]>(`${API_BASE}/watchlist/`);
}

export async function addToWatchlist(symbol: string): Promise<WatchlistItem> {
  return apiFetch<WatchlistItem>(`${API_BASE}/watchlist/`, {
    method: "POST",
    body: JSON.stringify({ symbol }),
  });
}

/**
 * Bulk-add up to 20 symbols in one call. Atomic at the tier-quota level:
 * if the projected `existing + new_unique` exceeds the Free cap (10), the
 * whole batch is rejected with 403 `limit_exceeded:max_watchlist` and
 * nothing is inserted. Per-row issues (unknown symbol etc.) are reported
 * inside the 201 envelope.
 *
 * NOTE: The /portfolio page migration flow does NOT use this — see
 * `watchlist-migration.ts` for why it sticks with single-symbol adds.
 */
export async function bulkAddToWatchlist(
  symbols: string[],
): Promise<WatchlistBulkAddResponse> {
  return apiFetch<WatchlistBulkAddResponse>(`${API_BASE}/watchlist/bulk`, {
    method: "POST",
    body: JSON.stringify({ symbols }),
  });
}

export async function removeFromWatchlist(symbol: string): Promise<void> {
  // Backend returns 200 { ok: true } here, not 204. apiFetch will parse it
  // to { ok: true } but we discard the body — callers only care about success.
  await apiFetch<{ ok: boolean }>(
    `${API_BASE}/watchlist/${encodeURIComponent(symbol)}`,
    { method: "DELETE" },
  );
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

// Types sourced from the generated OpenAPI schema (E2E-1 wire-up W2).
// Drift between backend Pydantic schemas and these aliases is caught
// by the schema-gate CI workflow.

export type HoldingMarket = Schemas["Market"];

// Action / dividend-type / currency enums are not separately exposed by the
// FastAPI schema (they appear inline as plain string fields), so we keep the
// literal unions here as the canonical frontend type.
export type HoldingTradeAction = "BUY" | "SELL";
export type HoldingDividendType = "CASH" | "STOCK";

// ── Accounts ───────────────────────────────────────────────────────────────

export type HoldingAccount = Schemas["AccountResponse"];
export type HoldingAccountCreateRequest = Schemas["AccountCreateRequest"];
export type HoldingAccountUpdateRequest = Schemas["AccountUpdateRequest"];

// ── Trades ─────────────────────────────────────────────────────────────────

export type HoldingTrade = Schemas["TradeResponse"];
export type HoldingTradeCreateRequest = Schemas["TradeCreateRequest"];
export type HoldingTradeUpdateRequest = Schemas["TradeUpdateRequest"];

// ── Positions (read-only, derived) ─────────────────────────────────────────

export type HoldingPosition = Schemas["PositionResponse"];
export type HoldingPositionListResponse = Schemas["PositionListResponse"];

// ── Summary ────────────────────────────────────────────────────────────────

export type HoldingSummary = Schemas["SummaryResponse"];

// ── Multi-currency (Phase 4+ / Round 10 Z1) ────────────────────────────────

/**
 * Supported FX base/quote currencies — kept in sync with backend
 * `_SUPPORTED_BASE_CURRENCIES` in `app/api/v1/holdings/summary.py` and
 * `app/api/v1/holdings/fx.py`. Add new ISO 4217 codes in BOTH places.
 */
export type Currency = "TWD" | "USD" | "JPY" | "HKD" | "EUR" | "GBP" | "CNY";

export const SUPPORTED_CURRENCIES: Currency[] = [
  "TWD",
  "USD",
  "JPY",
  "HKD",
  "EUR",
  "GBP",
  "CNY",
];

export type CurrencyBreakdown = Schemas["CurrencyBreakdown"];
export type MultiCurrencyHoldingSummary = Schemas["MultiCurrencySummaryResponse"];

// ── Dividends ──────────────────────────────────────────────────────────────

export type HoldingDividend = Schemas["DividendResponse"];
export type HoldingDividendCreateRequest = Schemas["DividendCreateRequest"];
export type HoldingDividendUpdateRequest = Schemas["DividendUpdateRequest"];

// ── CSV Import (Phase 4) ──────────────────────────────────────────────────

export type ImportResultRow = Schemas["ImportResultRow"];
export type ImportResult = Schemas["ImportResult"];
export type BrokerInfo = Schemas["BrokerInfo"];
export type BrokerListResponse = Schemas["BrokerListResponse"];

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

/**
 * Type guard — distinguishes the multi-currency response from the
 * legacy single-currency one. The backend returns the multi shape only
 * when the caller passed `?base_currency=`.
 */
export function isMultiCurrencyHoldingSummary(
  s: HoldingSummary | MultiCurrencyHoldingSummary,
): s is MultiCurrencyHoldingSummary {
  return (
    typeof (s as MultiCurrencyHoldingSummary).by_currency !== "undefined" &&
    Array.isArray((s as MultiCurrencyHoldingSummary).by_currency)
  );
}

/**
 * Fetch the user-wide KPI row.
 *
 *   - `baseCurrency=undefined` → legacy `HoldingSummary` (same-currency
 *     aggregation; preserves backwards compat with X1/X2 callers).
 *   - `baseCurrency="USD"` → `MultiCurrencyHoldingSummary` with
 *     cross-currency totals + per-currency breakdown. Pro-only when
 *     positions span >1 currency (403 propagated to caller).
 */
export async function getUserHoldingSummary(
  baseCurrency?: Currency,
): Promise<HoldingSummary | MultiCurrencyHoldingSummary> {
  if (baseCurrency === undefined) {
    return apiFetch<HoldingSummary>(`${API_BASE}/holdings/summary`);
  }
  const qs = new URLSearchParams({ base_currency: baseCurrency });
  return apiFetch<MultiCurrencyHoldingSummary>(
    `${API_BASE}/holdings/summary?${qs.toString()}`,
  );
}

export async function getAccountHoldingSummary(
  accountId: number,
): Promise<HoldingSummary> {
  return apiFetch<HoldingSummary>(`${API_BASE}/holdings/summary/${accountId}`);
}

// ── FX (Round 10 Z1) ──────────────────────────────────────────────────────

/**
 * Spot or historical FX rate, such that
 *   `quote_amount = base_amount * rate`.
 *
 * Wire shape mirrors backend `FxRateResponse` in
 * `app/api/v1/holdings/fx.py`. `rate` is Decimal-as-string. `as_of` is
 * either the requested ISO date or `null` (spot).
 */
export interface FxRateResponse {
  base: string;
  quote: string;
  rate: string;
  as_of: string | null;
}

export async function getFxRate(
  base: Currency,
  quote: Currency,
  asOf?: string,
): Promise<FxRateResponse> {
  const qs = new URLSearchParams({ base, quote });
  if (asOf) qs.set("as_of", asOf);
  return apiFetch<FxRateResponse>(
    `${API_BASE}/holdings/fx/rate?${qs.toString()}`,
  );
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
 * List the broker adapters available for CSV import (Round 10).
 *
 * Returns the registry in canonical order — broker-specific adapters
 * first, generic fallback last. The modal renders this as a select
 * dropdown with an extra "auto-detect" sentinel at the top (frontend-only).
 */
export async function listImportBrokers(): Promise<BrokerInfo[]> {
  const data = await apiFetch<BrokerListResponse>(
    `${API_BASE}/holdings/imports/brokers`,
  );
  return data.brokers;
}

/**
 * Bulk-import trades from a broker CSV.
 *
 * Wire shape: raw `text/csv` body (NOT multipart) — keeps us off the
 * `python-multipart` dependency on the backend. Metadata (`account_id`,
 * `dry_run`, `broker_key`) goes on the query string. The browser sets
 * the boundary we want when we pass a `Blob` directly.
 *
 * `brokerKey` is optional; omit to let the backend auto-detect via
 * BrokerParser.can_handle() heuristics. Round 10 added per-broker
 * adapters: "interactive_brokers", "yuanta", "fubon", "schwab",
 * "fidelity", "generic" (Y2 canonical fallback).
 *
 * Use `dry_run=true` first to render a preview table, then call again
 * with `dry_run=false` to commit. Backend is atomic: on any row failure
 * with `dry_run=false`, ZERO rows commit.
 */
export async function importHoldingsCsv(
  accountId: number,
  file: Blob | File | string,
  dryRun: boolean,
  brokerKey?: string | null,
): Promise<ImportResult> {
  const qs = new URLSearchParams({
    account_id: String(accountId),
    dry_run: dryRun ? "true" : "false",
  });
  if (brokerKey) qs.set("broker_key", brokerKey);
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

// ---------------------------------------------------------------------------
// Institutional 13F — Types (Phase 2, /institutional/* endpoints)
//
// Mirrors backend Pydantic schemas in
//   `app/schemas/institutional/{filer,filing,cross_stock,subscription}.py`.
// Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
//
// Wire conventions:
//   - Decimal-as-string: every USD / share value lands as `string | null`;
//     call `Number(...)` only at the render boundary.
//   - 5-way change_type literal (NEW/INCREASED/DECREASED/EXITED/UNCHANGED) is
//     widened to `string` to match the cross-stock single-side classification
//     which is loosely typed on the backend (it stringifies an enum value).
//   - `put_call` is exactly one of "PUT"/"CALL"/null on the wire.
//
// Trailing-slash note (mirrors watchlist): the backend uses
//   `APIRouter(prefix="/filers")` mounted on `/institutional`, so list /
//   subscribe live at `/institutional/filers` (NO trailing slash). The
//   sub-router for search is a POST. We match these path shapes verbatim.
// ---------------------------------------------------------------------------

export interface F13Filer {
  id: number;
  cik: string;
  name: string;
  legal_name: string | null;
  /** Decimal-as-string. May be null until first refresh ingests a filing. */
  latest_total_value_usd: string | null;
  latest_options_notional_usd: string | null;
  /** ISO date (YYYY-MM-DD) of the most recent 13F-HR `report_period_end`. */
  latest_filing_date: string | null;
  latest_position_count: number | null;
  created_at: string;
}

export interface F13FilerSearchResult {
  cik: string;
  name: string;
  legal_name: string | null;
  /** True when the local DB already has this filer (instant subscribe). */
  is_locally_known: boolean;
}

/**
 * One row of `f13_filings` — the per-quarter snapshot meta.
 *
 * `form_type` is typically "13F-HR" or "13F-HR/A" (amendment); occasionally
 * "13F-NT" once Phase 4+ broadens scope. Kept as `string` so we don't
 * crash on unexpected values.
 */
export interface F13Filing {
  id: number;
  filer_id: number;
  accession_number: string;
  form_type: string;
  /** Quarter-end date (e.g. "2025-12-31"). */
  report_period_end: string;
  filed_at: string;
  total_value_usd: string | null;
  options_notional_usd: string | null;
  total_positions: number | null;
  raw_xml_url: string | null;
}

/**
 * One row of `f13_holdings`.
 *
 * `stock_symbol` is denormalised by the backend when the CUSIP has been
 * mapped to `stocks.symbol`. Null means the CUSIP is unmapped — render the
 * raw `cusip` + `name_of_issuer` instead.
 */
export interface F13Holding {
  id: number;
  cusip: string;
  name_of_issuer: string;
  /** USD market value at quarter-end (already × 1000 from raw 13F units). */
  value_usd: string;
  shares: string | null;
  put_call: "PUT" | "CALL" | null;
  investment_discretion: string | null;
  stock_id: number | null;
  stock_symbol: string | null;
}

export interface F13HoldingsAtPeriod {
  filing: F13Filing;
  holdings: F13Holding[];
}

/** Backend's diff-engine 5-way classification. */
export type F13ChangeType =
  | "NEW"
  | "INCREASED"
  | "DECREASED"
  | "EXITED"
  | "UNCHANGED";

export interface F13HoldingChange {
  cusip: string;
  name_of_issuer: string;
  /** Widened from F13ChangeType so cross-stock's loose string still fits. */
  change_type: F13ChangeType | string;
  prev_shares: string | null;
  curr_shares: string | null;
  delta_shares: string;
  delta_pct: string | null;
  prev_value_usd: string | null;
  curr_value_usd: string | null;
  delta_value_usd: string;
}

export interface F13Diff {
  /** ISO date of the previous period (the `from` query param). */
  prev_period: string;
  curr_period: string;
  changes: F13HoldingChange[];
}

export interface F13RefreshResult {
  filings_added: number;
  holdings_added: number;
}

/**
 * Round 12 — per-stock multi-quarter timeline for a filer.
 *
 * One entry per quarterly filing in the requested window. `shares` /
 * `value_usd` are `null` when the filer filed that quarter but didn't
 * hold the requested stock; the timeline component renders these as
 * "未持有". `delta_*` follow the NEW / INCREASED / DECREASED / EXITED /
 * UNCHANGED / NOT_HELD classification on the wire.
 */
export type F13HistoryChangeType =
  | "NEW"
  | "INCREASED"
  | "DECREASED"
  | "EXITED"
  | "UNCHANGED"
  | "NOT_HELD";

export interface F13HoldingHistoryEntry {
  filing_id: number;
  /** ISO date string. */
  report_period_end: string;
  form_type: string;
  shares: string | null;
  value_usd: string | null;
  put_call: "PUT" | "CALL" | null;
  investment_discretion: string | null;
  delta_shares: string | null;
  delta_pct: string | null;
  change_type: F13HistoryChangeType | string;
}

export interface F13HoldingHistory {
  filer_id: number;
  /** CUSIP populated when the holding was found by CUSIP (or via stock JOIN). */
  cusip: string | null;
  /** Symbol populated when the holding was mapped to a `stocks` row. */
  symbol: string | null;
  /** ASC by `report_period_end` (oldest → newest). */
  entries: F13HoldingHistoryEntry[];
}

/** Cross-stock view: one filer-row in the per-stock institutional panel. */
export interface F13InstitutionalHolderForStock {
  filer_id: number;
  filer_name: string;
  filer_cik: string;
  latest_shares: string | null;
  latest_value_usd: string | null;
  prev_shares: string | null;
  /** Always present; "UNCHANGED" when prev/current are roughly equal. */
  change_type: string;
}

export interface F13InstitutionalStock {
  symbol: string;
  stock_id: number | null;
  holders: F13InstitutionalHolderForStock[];
}

/** POST /institutional/filers response envelope. */
export interface F13SubscriptionResponse {
  filer: F13Filer;
  subscribed_at: string;
  notify_on_new_filing: boolean;
}

// --- Bulk subscribe (POST /institutional/filers/bulk) ---

export interface F13BulkSubscribeRequestItem {
  /** CIK string (backend pads to 10 digits). */
  cik: string;
  /**
   * Optional display name. When omitted, the backend tries
   * EdgarClient.get_filer_metadata(cik) to auto-resolve.
   */
  name?: string;
}

export interface F13BulkSubscribeError {
  cik: string;
  /** snake_case: `invalid_cik` | `edgar_lookup_failed` | `unknown` */
  reason: string;
}

/**
 * Envelope for `POST /institutional/filers/bulk` (201).
 *
 * Quota errors (403 limit_exceeded:max_tracked_filers) short-circuit
 * the whole batch BEFORE any row is inserted; per-row issues land in
 * `errors[]`.
 */
export interface F13BulkSubscribeResponse {
  subscribed: F13Filer[];
  skipped_duplicates: string[];
  errors: F13BulkSubscribeError[];
}

// ---------------------------------------------------------------------------
// Institutional 13F — API functions
// ---------------------------------------------------------------------------

export async function listInstitutionalFilers(): Promise<F13Filer[]> {
  return apiFetch<F13Filer[]>(`${API_BASE}/institutional/filers`);
}

/**
 * Subscribe the current user to a filer by CIK.
 *
 * Backend behaviour (`F13SubscriptionService.subscribe`):
 *   - Local CIK exists → just insert subscription (200/201).
 *   - CIK new → fetch EDGAR for filer metadata + create row (`name`
 *     required for new filers; if omitted backend uses EDGAR-resolved name).
 *   - Already subscribed → 409 `f13_subscription_exists`.
 *   - Tier cap hit → 403 `limit_exceeded:max_tracked_filers`.
 *
 * Returns only the filer row (we discard `subscribed_at` /
 * `notify_on_new_filing`); callers that need those should hit the dedicated
 * subscription endpoints in a follow-up phase.
 */
export async function subscribeFiler(
  cik: string,
  name: string,
): Promise<F13Filer> {
  const res = await apiFetch<F13SubscriptionResponse>(
    `${API_BASE}/institutional/filers`,
    {
      method: "POST",
      body: JSON.stringify({ cik, name }),
    },
  );
  return res.filer;
}

export async function unsubscribeFiler(filerId: number): Promise<void> {
  await apiFetch<void>(`${API_BASE}/institutional/filers/${filerId}`, {
    method: "DELETE",
  });
}

/**
 * Search filers across local DB + EDGAR fulltext.
 *
 * Backend is `POST /filers/search?q=...&limit=...` (POST despite being a
 * pure read — matches the existing route shape). Empty / short queries
 * are short-circuited client-side because the backend rejects q.length < 2
 * with 422.
 */
export async function searchFilers(
  q: string,
  limit = 20,
): Promise<F13FilerSearchResult[]> {
  if (q.trim().length < 2) return [];
  const qs = new URLSearchParams({
    q: q.trim(),
    limit: String(limit),
  });
  return apiFetch<F13FilerSearchResult[]>(
    `${API_BASE}/institutional/filers/search?${qs.toString()}`,
    { method: "POST" },
  );
}

/**
 * Bulk-subscribe up to 20 filers in one call.
 *
 * The backend is atomic at the tier-quota level: if the projected
 * `current_subscriptions + new_unique_ciks` would exceed
 * `max_tracked_filers`, the whole batch is rejected with 403
 * `limit_exceeded:max_tracked_filers` and NOTHING is inserted. Per-row
 * issues (invalid CIK, EDGAR lookup failure when `name` omitted) land
 * inside the 201 envelope's `errors[]`.
 */
export async function bulkSubscribeFilers(
  items: F13BulkSubscribeRequestItem[],
): Promise<F13BulkSubscribeResponse> {
  return apiFetch<F13BulkSubscribeResponse>(
    `${API_BASE}/institutional/filers/bulk`,
    {
      method: "POST",
      body: JSON.stringify({ items }),
    },
  );
}

/**
 * On-demand refresh — fetch + ingest the latest N quarters for a filer.
 *
 * Tier-gated: FREE/BASIC users will receive 403 with
 * `feature_unavailable:institutional_realtime_refresh`. A second concurrent
 * refresh on the same filer returns 429 with `f13_refresh_in_flight`.
 */
export async function refreshFiler(
  filerId: number,
  maxQuarters = 4,
): Promise<F13RefreshResult> {
  const qs = new URLSearchParams({ max_quarters: String(maxQuarters) });
  return apiFetch<F13RefreshResult>(
    `${API_BASE}/institutional/filers/${filerId}/refresh?${qs.toString()}`,
    { method: "POST" },
  );
}

export async function listFilings(
  filerId: number,
  limit = 20,
  offset = 0,
): Promise<F13Filing[]> {
  const qs = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return apiFetch<F13Filing[]>(
    `${API_BASE}/institutional/filers/${filerId}/filings?${qs.toString()}`,
  );
}

/**
 * Fetch a filer's holdings for one period.
 *
 * `period` accepts the literal "latest" or an ISO date (YYYY-MM-DD) that
 * MUST match an existing `report_period_end`. The page uses "latest" by
 * default and an explicit date when the user changes the period selector.
 */
export async function getHoldings(
  filerId: number,
  period: string,
): Promise<F13HoldingsAtPeriod> {
  const qs = new URLSearchParams({ period });
  return apiFetch<F13HoldingsAtPeriod>(
    `${API_BASE}/institutional/filers/${filerId}/holdings?${qs.toString()}`,
  );
}

/**
 * Round 12 — per-stock position history across multiple quarters.
 *
 * Replaces the previous "fan out one /holdings request per filing"
 * pattern with a single round trip. The backend handles change-type
 * classification + delta math and returns ASC-sorted entries with
 * NOT_HELD placeholders for quarters where the filer didn't hold the
 * stock.
 *
 * Access: subscription to the filer OR Pro-tier
 * `institutional_ownership_panel` feature. Window defaults to 2y on
 * the backend when `fromDate` / `toDate` are omitted; we mirror the
 * default behaviour by allowing the caller to omit either side.
 */
export async function getHoldingHistory(
  filerId: number,
  identifier: string,
  opts?: { fromDate?: string; toDate?: string; limit?: number },
): Promise<F13HoldingHistory> {
  const qs = new URLSearchParams();
  if (opts?.fromDate) qs.set("from_date", opts.fromDate);
  if (opts?.toDate) qs.set("to_date", opts.toDate);
  if (opts?.limit != null) qs.set("limit", String(opts.limit));
  const suffix = qs.toString();
  return apiFetch<F13HoldingHistory>(
    `${API_BASE}/institutional/filers/${filerId}/holdings/${encodeURIComponent(
      identifier,
    )}/history${suffix ? `?${suffix}` : ""}`,
  );
}

/**
 * Quarter-over-quarter diff between two stored filings.
 *
 * Both dates MUST already exist in `f13_filings`; this endpoint does NOT
 * implicitly refresh. Callers should drive the period picker off a recent
 * `useFilings()` result so the user can only pick stored periods.
 *
 * Note: the backend route aliases `from_date` ↔ `from` and `to_date` ↔ `to`
 * (FastAPI `Query(alias=...)`). The query string here uses the wire names.
 */
export async function getDiff(
  filerId: number,
  fromDate: string,
  toDate: string,
): Promise<F13Diff> {
  const qs = new URLSearchParams({ from: fromDate, to: toDate });
  return apiFetch<F13Diff>(
    `${API_BASE}/institutional/filers/${filerId}/diff?${qs.toString()}`,
  );
}

/**
 * Cross-stock institutional panel — "which filers hold this symbol?"
 *
 * Pro-only feature (`feature_unavailable:institutional_ownership_panel`
 * for lower tiers). The Phase 2 page does not surface this yet; we expose
 * the client so the per-stock page can adopt it without another round.
 */
export async function getInstitutionalForStock(
  symbol: string,
): Promise<F13InstitutionalStock> {
  return apiFetch<F13InstitutionalStock>(
    `${API_BASE}/institutional/stocks/${encodeURIComponent(symbol)}/institutional`,
  );
}

// ---------------------------------------------------------------------------
// Me — notification preferences (Round 9 Y7)
// ---------------------------------------------------------------------------
//
// Single-channel v1 shape. Backend deliberately keeps email/LINE/webhook
// off the wire until those channels actually ship — see
// `backend/app/schemas/me_notifications.py` for the rationale. Setting
// `telegram_chat_id` to `null` is the canonical "stop sending me TG alerts"
// gesture (column becomes NULL, F13NotificationService filters us out).

export interface MeNotificationSettings {
  /** Numeric chat id ("123456789") or @channel handle. `null` ⇒ disabled. */
  telegram_chat_id: string | null;
  /**
   * Round 14: Email channel opt-in (UNI_USER_003). When `true` the
   * dispatcher fans 13F + alert notifications out to the user's
   * primary `email` in addition to (or instead of) Telegram.
   */
  notify_via_email: boolean;
}

/**
 * PATCH body shape — every field is optional. Omitted fields are NOT
 * touched on the user row (backend reads `model_fields_set`), so the
 * UI can flip the email toggle without re-sending the Telegram chat
 * id (and vice versa). `telegram_chat_id: null` is the canonical
 * "stop TG alerts" gesture.
 */
export interface MeNotificationSettingsPatch {
  telegram_chat_id?: string | null;
  notify_via_email?: boolean;
}

export async function getMeNotifications(): Promise<MeNotificationSettings> {
  return apiFetch<MeNotificationSettings>(`${API_BASE}/me/notifications`);
}

export async function updateMeNotifications(
  req: MeNotificationSettingsPatch,
): Promise<MeNotificationSettings> {
  return apiFetch<MeNotificationSettings>(`${API_BASE}/me/notifications`, {
    method: "PATCH",
    body: JSON.stringify(req),
  });
}

// ---------------------------------------------------------------------------
// Per-filer subscription preferences (Round 9 Y7)
// ---------------------------------------------------------------------------
//
// Only PATCH is exposed by the backend — there is intentionally no GET
// (the list endpoint omits `notify_on_new_filing` per Phase-2 envelope
// trim). Frontend tracks the toggle state optimistically and reconciles
// from PATCH responses. Backend default is `true`, so a fresh subscription
// is "notify me" until the user opts out.

export interface F13SubscriptionPreferences {
  filer_id: number;
  notify_on_new_filing: boolean;
}

export async function updateFilerPreferences(
  filerId: number,
  req: { notify_on_new_filing: boolean },
): Promise<F13SubscriptionPreferences> {
  return apiFetch<F13SubscriptionPreferences>(
    `${API_BASE}/institutional/filers/${filerId}/preferences`,
    {
      method: "PATCH",
      body: JSON.stringify(req),
    },
  );
}

// ---------------------------------------------------------------------------
// Holdings — Rebalancing (Phase 5+, Pro-tier preview)
// ---------------------------------------------------------------------------
//
// `POST /holdings/rebalance/preview` returns the trades required to move
// the current portfolio toward a user-supplied target allocation. The
// endpoint is preview-only — no database writes occur. The frontend
// surfaces the suggestions and lets the user execute each one via the
// existing `POST /holdings/trades` flow.
//
// Decimal-as-string: `qty`, `estimated_price`, `estimated_value`,
// `total_portfolio_value`, `cash_residual`, and the values of
// `final_allocation_pct` arrive as strings; convert with `Number(...)`
// at the render boundary only.

/** One target row sent to `/holdings/rebalance/preview`. */
export interface RebalanceTarget {
  symbol: string;
  market: HoldingMarket;
  /** Percentage 0..100 as Decimal-string ("33.333" preserves precision). */
  target_pct: string;
}

export interface RebalanceRequest {
  targets: RebalanceTarget[];
  /** Restrict to one account; omit to aggregate across all. */
  account_id?: number;
  /** Skip trades below this absolute |delta_value|; defaults server-side to 100. */
  min_trade_value?: string;
}

export interface SuggestedTrade {
  symbol: string;
  market: HoldingMarket;
  action: "BUY" | "SELL";
  qty: string;
  estimated_price: string;
  estimated_value: string;
  /** Human-readable reason — surface as tooltip / secondary text. */
  rationale: string;
}

/** Pass-through shape from the backend `skipped_trades` list. */
export interface SkippedTrade {
  symbol: string;
  market: HoldingMarket;
  target_pct: string;
  delta_value: string;
  /** One of: below_min_trade_value | missing_price_for_buy | missing_price_for_sell | exit_below_min_trade_value */
  reason: string;
}

export interface RebalanceResponse {
  total_portfolio_value: string;
  suggested_trades: SuggestedTrade[];
  /** Keys are `${symbol}|${market}` per the backend's composite key. */
  final_allocation_pct: Record<string, string>;
  skipped_trades: SkippedTrade[];
  cash_residual: string;
}

export async function previewRebalance(
  req: RebalanceRequest,
): Promise<RebalanceResponse> {
  return apiFetch<RebalanceResponse>(
    `${API_BASE}/holdings/rebalance/preview`,
    {
      method: "POST",
      body: JSON.stringify(req),
    },
  );
}

// ── Phase 2: execute (persists trades server-side) ─────────────────────────
//
// The execute endpoint re-computes `suggested_trades` server-side from the
// same `RebalanceRequest` payload as preview and writes each row through
// the regular `PortfolioTradeService.record_trade` pipeline. Returns a
// per-row summary (executed / skipped / failed) — never throws on partial
// success; only the whole-batch errors (403 / 404 / 422) bubble.
//
// `account_id` is REQUIRED for execute (preview allows aggregate mode);
// the backend returns 422 `account_id_required_for_execute` when omitted.

export interface ExecutedRebalanceTrade {
  symbol: string;
  market: HoldingMarket;
  action: "BUY" | "SELL";
  qty: string;
  price: string;
  /** Primary key of the inserted `portfolio_trades` row. */
  trade_id: number;
}

export interface SkippedRebalanceTrade {
  symbol: string;
  market: HoldingMarket;
  reason: string;
  target_pct?: string | null;
  delta_value?: string | null;
}

export interface FailedRebalanceTrade {
  symbol: string;
  market: HoldingMarket;
  action: "BUY" | "SELL";
  /** Canonical `_detail` string — e.g. `insufficient_shares`. */
  error_code: string;
  message: string;
}

export interface RebalanceExecuteResponse {
  executed: ExecutedRebalanceTrade[];
  skipped: SkippedRebalanceTrade[];
  failed: FailedRebalanceTrade[];
  /** Sum of `qty * price` across `executed` rows (Decimal as string). */
  total_executed_value: string;
}

export async function executeRebalance(
  req: RebalanceRequest,
): Promise<RebalanceExecuteResponse> {
  return apiFetch<RebalanceExecuteResponse>(
    `${API_BASE}/holdings/rebalance/execute`,
    {
      method: "POST",
      body: JSON.stringify(req),
    },
  );
}

// ---------------------------------------------------------------------------
// /me/audit-logs — user-facing audit history viewer (Round 13)
// ---------------------------------------------------------------------------
//
// The backend column for the verb is named ``action`` for legacy reasons,
// but the user-facing API renames it to ``event_type`` and the
// JSONB sidecar ``event_metadata`` → ``metadata``. The frontend follows
// the API contract, not the DB column names — that mapping is owned by
// ``backend/app/schemas/audit.py``.
//
// Retention: the backend clamps responses to the last 10 days. If a
// client passes a larger ``offset`` than ``total_count``, the response
// is simply an empty page.

export interface AuditLogEntry {
  /** UUID returned as string — opaque row key for the React list. */
  id: string;
  event_type: string;
  resource_type: string | null;
  resource_id: string | null;
  after_state: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  /** ISO-8601 UTC timestamp. */
  created_at: string;
}

export interface AuditLogListResponse {
  entries: AuditLogEntry[];
  /** Total rows matching the filter inside the 10-day window. */
  total_count: number;
  /** ``offset + entries.length < total_count`` — pre-computed by server. */
  has_more: boolean;
}

export interface ListMyAuditLogsOptions {
  limit?: number;
  offset?: number;
  /** Whitelist of event_type values; ``undefined`` ⇒ all types. */
  eventTypes?: string[];
}

/**
 * Fetch the current user's audit-log history.
 *
 * Multi-value query param semantics for ``event_types``:
 *   ``?event_types=user_login&event_types=watchlist_added`` per the
 *   FastAPI list[str] convention. We build it manually instead of
 *   using URLSearchParams.append() with a single key so the surface
 *   stays declarative.
 */
export async function listMyAuditLogs(
  opts: ListMyAuditLogsOptions = {},
): Promise<AuditLogListResponse> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.offset !== undefined) params.set("offset", String(opts.offset));
  if (opts.eventTypes && opts.eventTypes.length > 0) {
    for (const t of opts.eventTypes) params.append("event_types", t);
  }
  const qs = params.toString();
  const url = qs
    ? `${API_BASE}/me/audit-logs?${qs}`
    : `${API_BASE}/me/audit-logs`;
  return apiFetch<AuditLogListResponse>(url);
}

// ---------------------------------------------------------------------------
// Alert rules (UNI-ALERT-001) — /holdings/alerts
// ---------------------------------------------------------------------------

export type AlertRuleType =
  | "POSITION_PRICE_DROP"
  | "POSITION_PRICE_RISE"
  | "PORTFOLIO_VALUE_ABOVE"
  | "PORTFOLIO_VALUE_BELOW"
  | "POSITION_PNL_PCT_ABOVE"
  | "POSITION_PNL_PCT_BELOW";

export type AlertStatus = "ACTIVE" | "PAUSED" | "TRIGGERED";
export type AlertThresholdType = "PCT" | "ABSOLUTE";

export interface AlertRule {
  id: number;
  name: string;
  rule_type: AlertRuleType;
  symbol: string | null;
  market: string | null;
  /** Decimal-as-string per project convention. */
  threshold_value: string;
  threshold_type: AlertThresholdType;
  status: AlertStatus;
  last_evaluated_at: string | null;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertRuleCreateRequest {
  name: string;
  rule_type: AlertRuleType;
  threshold_value: string;
  threshold_type: AlertThresholdType;
  symbol?: string | null;
  market?: string | null;
}

export interface AlertRuleUpdateRequest {
  name?: string;
  status?: AlertStatus;
  threshold_value?: string;
  threshold_type?: AlertThresholdType;
}

export interface AlertEvaluationResult {
  triggered: boolean;
  actual_value: string;
  threshold: string;
  message: string;
}

export async function listAlertRules(): Promise<AlertRule[]> {
  return apiFetch<AlertRule[]>(`${API_BASE}/holdings/alerts`);
}

export async function createAlertRule(
  body: AlertRuleCreateRequest,
): Promise<AlertRule> {
  return apiFetch<AlertRule>(`${API_BASE}/holdings/alerts`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateAlertRule(
  id: number,
  body: AlertRuleUpdateRequest,
): Promise<AlertRule> {
  return apiFetch<AlertRule>(`${API_BASE}/holdings/alerts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteAlertRule(id: number): Promise<void> {
  await apiFetch<{ ok: boolean }>(`${API_BASE}/holdings/alerts/${id}`, {
    method: "DELETE",
  });
}

export async function evaluateAlertRule(
  id: number,
): Promise<AlertEvaluationResult> {
  return apiFetch<AlertEvaluationResult>(
    `${API_BASE}/holdings/alerts/${id}/evaluate`,
    { method: "POST" },
  );
}
