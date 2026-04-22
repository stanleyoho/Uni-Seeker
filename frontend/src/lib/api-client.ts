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
