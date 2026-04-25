const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

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
  values: Record<string, (number | null)[]>;
}

export async function fetchPrices(symbol: string, limit = 30): Promise<PriceListResponse> {
  const res = await fetch(`${API_BASE}/prices/${symbol}?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to fetch prices: ${res.status}`);
  return res.json();
}

export async function fetchIndicator(
  symbol: string,
  indicator: string,
  params: Record<string, unknown> = {},
): Promise<IndicatorResponse> {
  const res = await fetch(`${API_BASE}/indicators/calculate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, indicator, params }),
  });
  if (!res.ok) throw new Error(`Failed to calculate indicator: ${res.status}`);
  return res.json();
}

export async function fetchIndicatorList(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/indicators/`);
  if (!res.ok) throw new Error(`Failed to fetch indicators: ${res.status}`);
  const data = await res.json();
  return data.indicators;
}

// --- Stock Search ---

export interface StockSearchResult {
  symbol: string;
  name: string;
  market: string;
}

export async function searchStocks(query: string, limit = 10): Promise<StockSearchResult[]> {
  if (!query.trim()) return [];
  const res = await fetch(`${API_BASE}/stocks/search?q=${encodeURIComponent(query)}&limit=${limit}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.results;
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
  indicator_values: Record<string, number>;
}

export interface ScreenResponse {
  results: ScreenResult[];
  total: number;
}

export async function screenStocks(
  conditions: ScreenCondition[],
  operator = "AND",
  sortBy?: string,
  limit = 50,
): Promise<ScreenResponse> {
  const res = await fetch(`${API_BASE}/screener/screen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conditions, operator, sort_by: sortBy, limit }),
  });
  if (!res.ok) throw new Error(`Screen failed: ${res.status}`);
  return res.json();
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

export async function fetchNotificationRules(): Promise<NotificationRule[]> {
  const res = await fetch(`${API_BASE}/notifications/rules`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.rules;
}

export async function createNotificationRule(
  rule: { name: string; rule_type: string; symbol: string; conditions: Record<string, unknown> },
): Promise<NotificationRule> {
  const res = await fetch(`${API_BASE}/notifications/rules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rule),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function deleteNotificationRule(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/notifications/rules/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

// --- Financials ---

export interface FinancialRatios {
  symbol: string;
  period: string;
  gross_margin: number | null;
  operating_margin: number | null;
  net_margin: number | null;
  roe: number | null;
  roa: number | null;
  current_ratio: number | null;
  debt_ratio: number | null;
  revenue_growth: number | null;
  net_income_growth: number | null;
}

export interface HealthScore {
  symbol: string;
  period: string;
  total_score: number;
  profitability_score: number;
  efficiency_score: number;
  leverage_score: number;
  growth_score: number;
}

export interface FinancialStatement {
  period: string;
  period_type: string;
  data: Record<string, number>;
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

export async function fetchFinancialAnalysis(symbol: string): Promise<FullAnalysis> {
  const res = await fetch(`${API_BASE}/financials/${symbol}`);
  if (!res.ok) throw new Error(`Failed to fetch financials: ${res.status}`);
  return res.json();
}

// --- Auth ---

export interface AuthUser {
  id: number;
  email: string;
  username: string;
  tier: string;
}

export async function register(email: string, password: string, username: string): Promise<string> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, username }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Registration failed");
  }
  const data = await res.json();
  return data.access_token;
}

export async function login(email: string, password: string): Promise<string> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Login failed");
  }
  const data = await res.json();
  return data.access_token;
}

export async function fetchMe(token: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Not authenticated");
  return res.json();
}

// --- Company Info ---

export interface CompanyInfo {
  symbol: string;
  name: string;
  market: string;
  industry: string;
}

export async function fetchCompanyInfo(symbol: string): Promise<CompanyInfo | null> {
  const res = await fetch(`${API_BASE}/company/${encodeURIComponent(symbol)}`);
  if (!res.ok) return null;
  return res.json();
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

export async function fetchMarginData(symbol: string): Promise<MarginData | null> {
  const res = await fetch(`${API_BASE}/margin/${encodeURIComponent(symbol)}`);
  if (!res.ok) return null;
  return res.json();
}

// --- Market Overview ---

export interface MarketIndex {
  symbol: string;
  name: string;
  value: number;
  change: number;
  change_percent: number;
}

export interface MarketMover {
  symbol: string;
  name: string;
  market: string;
  close: number;
  change: number;
  change_percent: number;
  volume: number;
}

export interface MarketMoversResponse {
  gainers: MarketMover[];
  losers: MarketMover[];
  most_active: MarketMover[];
  date: string | null;
}

export async function fetchMarketIndices(): Promise<MarketIndex[]> {
  const res = await fetch(`${API_BASE}/market/indices`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.indices;
}

export async function fetchMarketMovers(marketFilter?: string, limit = 10): Promise<MarketMoversResponse> {
  const params = new URLSearchParams();
  if (marketFilter) params.set("market_filter", marketFilter);
  params.set("limit", String(limit));
  const res = await fetch(`${API_BASE}/market/movers?${params}`);
  if (!res.ok) return { gainers: [], losers: [], most_active: [], date: null };
  return res.json();
}

// --- Revenue ---

export interface RevenueRecord {
  period: string;
  revenue: number;
  currency: string;
}

export interface RevenueAnalysis {
  symbol: string;
  latest_revenue: number;
  qoq_growth: number | null;
  yoy_growth: number | null;
  is_revenue_high: boolean;
  is_revenue_low: boolean;
  trend: string;
  consecutive_growth_quarters: number;
  records: RevenueRecord[];
}

export async function fetchRevenueAnalysis(symbol: string): Promise<RevenueAnalysis | null> {
  const res = await fetch(`${API_BASE}/revenue/${encodeURIComponent(symbol)}`);
  if (!res.ok) return null;
  return res.json();
}

// --- Heatmap ---

export interface HeatmapStock {
  symbol: string;
  name: string;
  close: number;
  change_percent: number;
  volume: number;
}

export interface HeatmapSector {
  industry: string;
  stock_count: number;
  avg_change_percent: number;
  total_volume: number;
  stocks: HeatmapStock[];
}

export interface HeatmapResponse {
  sectors: HeatmapSector[];
  date: string | null;
}

export async function fetchHeatmapData(marketFilter?: string): Promise<HeatmapResponse> {
  const params = new URLSearchParams();
  if (marketFilter) params.set("market_filter", marketFilter);
  const res = await fetch(`${API_BASE}/heatmap/sectors?${params}`);
  if (!res.ok) return { sectors: [], date: null };
  return res.json();
}

// --- Low Base ---

export interface LowBaseScore {
  symbol: string;
  name: string;
  total_score: number;
  valuation_score: number;
  price_position_score: number;
  quality_score: number;
  pe_percentile: number | null;
  ma240_deviation: number | null;
  peg: number | null;
  details: Record<string, unknown>;
}

export interface LowBaseRanking {
  results: LowBaseScore[];
  total_scanned: number;
  total_qualified: number;
}

export async function fetchLowBaseRanking(limit = 20): Promise<LowBaseRanking> {
  const res = await fetch(`${API_BASE}/low-base/scan?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function fetchLowBaseScore(symbol: string): Promise<LowBaseScore> {
  const res = await fetch(`${API_BASE}/low-base/${symbol}`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
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

export async function fetchInstitutional(
  symbol: string,
  startDate: string,
  endDate: string,
): Promise<InstitutionalData[]> {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
  });
  const res = await fetch(
    `${API_BASE}/institutional/${encodeURIComponent(symbol)}?${params}`,
  );
  if (!res.ok) throw new Error(`Failed to fetch institutional data: ${res.status}`);
  const json: InstitutionalResponse = await res.json();
  return json.data;
}

// --- Backtest ---

export interface StrategyInfo {
  name: string;
  description: string;
  params: Record<string, unknown>;
}

export interface BacktestMetrics {
  total_return: number;
  annualized_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  win_rate: number;
  total_trades: number;
  profit_factor: number;
}

export interface TradeRecord {
  action: string;
  date: string;
  price: number;
  shares: number;
  reason: string;
}

export interface BacktestResult {
  symbol: string;
  strategy: string;
  metrics: BacktestMetrics;
  equity_curve: number[];
  trades: TradeRecord[];
}

export async function fetchStrategies(): Promise<StrategyInfo[]> {
  const res = await fetch(`${API_BASE}/strategies/`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.strategies;
}

export async function runBacktest(params: {
  symbol: string;
  strategy: string;
  params?: Record<string, unknown>;
  initial_capital?: number;
  position_size?: number;
}): Promise<BacktestResult> {
  const res = await fetch(`${API_BASE}/backtest/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Error ${res.status}` }));
    throw new Error(err.detail || `Backtest failed: ${res.status}`);
  }
  return res.json();
}
