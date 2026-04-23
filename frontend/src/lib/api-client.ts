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
