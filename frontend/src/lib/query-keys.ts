export const queryKeys = {
  market: {
    all: ["market"] as const,
    indices: () => [...queryKeys.market.all, "indices"] as const,
    movers: (filter?: string) =>
      [...queryKeys.market.all, "movers", filter] as const,
    heatmap: (filter?: string) =>
      [...queryKeys.market.all, "heatmap", filter] as const,
  },
  stocks: {
    all: ["stocks"] as const,
    detail: (symbol: string) =>
      [...queryKeys.stocks.all, symbol] as const,
    prices: (symbol: string, limit?: number) =>
      [...queryKeys.stocks.detail(symbol), "prices", limit] as const,
    company: (symbol: string) =>
      [...queryKeys.stocks.detail(symbol), "company"] as const,
    margin: (symbol: string) =>
      [...queryKeys.stocks.detail(symbol), "margin"] as const,
    financials: (symbol: string) =>
      [...queryKeys.stocks.detail(symbol), "financials"] as const,
    revenue: (symbol: string) =>
      [...queryKeys.stocks.detail(symbol), "revenue"] as const,
    institutional: (
      symbol: string,
      startDate?: string,
      endDate?: string,
    ) =>
      [
        ...queryKeys.stocks.detail(symbol),
        "institutional",
        startDate,
        endDate,
      ] as const,
  },
  backtest: {
    all: ["backtest"] as const,
    strategies: () =>
      [...queryKeys.backtest.all, "strategies"] as const,
    queue: () => [...queryKeys.backtest.all, "queue"] as const,
    history: (symbol?: string, limit?: number) =>
      [...queryKeys.backtest.all, "history", symbol, limit] as const,
    result: (id: number) =>
      [...queryKeys.backtest.all, "result", id] as const,
  },
  portfolio: {
    all: ["portfolio"] as const,
    history: () =>
      [...queryKeys.portfolio.all, "history"] as const,
  },
  scanner: {
    all: ["scanner"] as const,
    scan: (keys?: string[]) =>
      [...queryKeys.scanner.all, "scan", keys] as const,
    stock: (symbol: string) =>
      [...queryKeys.scanner.all, "stock", symbol] as const,
  },
  lowBase: {
    all: ["low-base"] as const,
    ranking: (limit?: number) =>
      [...queryKeys.lowBase.all, "ranking", limit] as const,
  },
} as const;
