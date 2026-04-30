// ─── Demo symbols ────────────────────────────────────────────────
export const SYMBOLS = [
  { symbol: '2330.TW', name: 'TSMC', price: 892.0, change: 2.34, sector: 'Semiconductors' },
  { symbol: '2317.TW', name: 'Hon Hai', price: 178.5, change: -0.89, sector: 'Electronics' },
  { symbol: '2454.TW', name: 'MediaTek', price: 1285.0, change: 1.56, sector: 'Semiconductors' },
  { symbol: '2382.TW', name: 'Quanta', price: 312.0, change: -1.23, sector: 'Electronics' },
  { symbol: 'AAPL', name: 'Apple', price: 198.45, change: 1.12, sector: 'Technology' },
  { symbol: 'NVDA', name: 'NVIDIA', price: 875.3, change: 3.45, sector: 'Semiconductors' },
  { symbol: 'MSFT', name: 'Microsoft', price: 425.8, change: 0.67, sector: 'Technology' },
  { symbol: 'GOOGL', name: 'Alphabet', price: 175.2, change: -0.45, sector: 'Technology' },
];

// ─── OHLCV candle data ───────────────────────────────────────────
export interface OHLCV {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/**
 * Generate realistic OHLCV candles using a random-walk model.
 * Times are spaced 5 minutes apart starting from 09:00.
 */
export function generateOHLCV(basePrice: number, count: number = 60): OHLCV[] {
  const candles: OHLCV[] = [];
  let price = basePrice;
  const volatility = basePrice * 0.005; // 0.5% per candle

  for (let i = 0; i < count; i++) {
    const hour = 9 + Math.floor((i * 5) / 60);
    const minute = (i * 5) % 60;
    const time = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;

    const open = price;
    const move1 = (Math.random() - 0.48) * volatility; // slight upward bias
    const move2 = (Math.random() - 0.48) * volatility;
    const mid = open + move1;
    const close = mid + move2;

    const wickUp = Math.random() * volatility * 0.5;
    const wickDown = Math.random() * volatility * 0.5;
    const high = Math.max(open, close) + wickUp;
    const low = Math.min(open, close) - wickDown;

    const baseVolume = 500_000 + Math.random() * 1_500_000;
    // Volume spikes near open and close
    const timeFactor = i < 5 || i > count - 5 ? 2.0 : 1.0;
    const volume = Math.round(baseVolume * timeFactor);

    candles.push({
      time,
      open: parseFloat(open.toFixed(2)),
      high: parseFloat(high.toFixed(2)),
      low: parseFloat(low.toFixed(2)),
      close: parseFloat(close.toFixed(2)),
      volume,
    });

    price = close;
  }

  return candles;
}

// ─── Sparkline data ──────────────────────────────────────────────
/**
 * Generate 20 sparkline price points using a random walk.
 */
export function generateSparkline(basePrice: number, volatility: number = 0.02): number[] {
  const points: number[] = [];
  let price = basePrice;

  for (let i = 0; i < 20; i++) {
    price += price * (Math.random() - 0.5) * volatility;
    points.push(parseFloat(price.toFixed(2)));
  }

  return points;
}

// ─── Sector heatmap ──────────────────────────────────────────────
export const SECTORS = [
  { name: 'Semiconductors', change: 2.1, marketCap: 45 },
  { name: 'Electronics', change: -0.8, marketCap: 28 },
  { name: 'Financial', change: 0.5, marketCap: 35 },
  { name: 'Technology', change: 1.8, marketCap: 40 },
  { name: 'Healthcare', change: -1.2, marketCap: 15 },
  { name: 'Energy', change: 0.3, marketCap: 20 },
  { name: 'Materials', change: -0.6, marketCap: 12 },
  { name: 'Consumer', change: 1.1, marketCap: 18 },
  { name: 'Telecom', change: -0.3, marketCap: 10 },
  { name: 'Industrials', change: 0.9, marketCap: 22 },
];

// ─── Order book ──────────────────────────────────────────────────
export interface OrderBookLevel {
  price: number;
  size: number;
  total: number;
}

export interface OrderBook {
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
}

/**
 * Generate a 10-level order book centered around TSMC's price (~892).
 */
export function generateOrderBook(): OrderBook {
  const midPrice = 892.0;
  const tickSize = 0.5;

  const bids: OrderBookLevel[] = [];
  let bidTotal = 0;
  for (let i = 0; i < 10; i++) {
    const price = parseFloat((midPrice - (i + 1) * tickSize).toFixed(2));
    const size = Math.round(50 + Math.random() * 450);
    bidTotal += size;
    bids.push({ price, size, total: bidTotal });
  }

  const asks: OrderBookLevel[] = [];
  let askTotal = 0;
  for (let i = 0; i < 10; i++) {
    const price = parseFloat((midPrice + (i + 1) * tickSize).toFixed(2));
    const size = Math.round(50 + Math.random() * 450);
    askTotal += size;
    asks.push({ price, size, total: askTotal });
  }

  return { bids, asks };
}

// ─── News feed ───────────────────────────────────────────────────
export const NEWS_ITEMS = [
  { time: '14:32', title: 'TSMC Q1 revenue beats estimates by 8%', severity: 'positive' as const, source: 'Reuters' },
  { time: '14:15', title: 'Fed signals potential rate pause in June', severity: 'neutral' as const, source: 'Bloomberg' },
  { time: '13:58', title: 'NVIDIA announces new AI chip partnership', severity: 'positive' as const, source: 'CNBC' },
  { time: '13:42', title: 'Hon Hai faces supply chain disruption risk', severity: 'negative' as const, source: 'Nikkei' },
  { time: '13:30', title: 'Semiconductor index hits 52-week high', severity: 'positive' as const, source: 'MarketWatch' },
  { time: '13:15', title: 'US-China trade tensions resurface', severity: 'negative' as const, source: 'FT' },
  { time: '12:58', title: 'MediaTek launches 5G modem for IoT', severity: 'neutral' as const, source: 'DigiTimes' },
  { time: '12:45', title: 'Taiwan CPI data slightly above forecast', severity: 'neutral' as const, source: 'Reuters' },
];
