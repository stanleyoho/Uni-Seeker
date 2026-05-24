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
    valuation: (symbol: string) =>
      [...queryKeys.stocks.detail(symbol), "valuation"] as const,
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
  journal: {
    all: ["journal"] as const,
    accounts: () => [...queryKeys.journal.all, "accounts"] as const,
    account: (id: number) => [...queryKeys.journal.all, "account", id] as const,
    trades: (accountId: number, symbol?: string, page?: number) =>
      [...queryKeys.journal.all, "trades", accountId, symbol, page] as const,
    groups: () => [...queryKeys.journal.all, "groups"] as const,
    group: (id: number) => [...queryKeys.journal.all, "group", id] as const,
    alerts: () => [...queryKeys.journal.all, "alerts"] as const,
  },
  watchlist: {
    all: ["watchlist"] as const,
    list: () => ["watchlist", "list"] as const,
  },
  institutional: {
    all: ["institutional"] as const,
    filers: {
      all: ["institutional", "filers"] as const,
      list: () => ["institutional", "filers", "list"] as const,
      detail: (id: number) => ["institutional", "filers", id] as const,
      search: (q: string) =>
        ["institutional", "filers", "search", q] as const,
    },
    filings: {
      all: ["institutional", "filings"] as const,
      listByFiler: (filerId: number) =>
        ["institutional", "filings", filerId] as const,
      holdings: (filerId: number, period: string) =>
        ["institutional", "filings", filerId, "holdings", period] as const,
      // Round 12 — per-stock multi-quarter timeline. Window encoded in
      // the key so a date-range change correctly invalidates the cache.
      holdingHistory: (
        filerId: number,
        identifier: string,
        fromDate: string,
        toDate: string,
        limit: number,
      ) =>
        [
          "institutional",
          "filings",
          filerId,
          "holdings",
          identifier,
          "history",
          fromDate,
          toDate,
          limit,
        ] as const,
      diff: (filerId: number, from: string, to: string) =>
        ["institutional", "filings", filerId, "diff", from, to] as const,
    },
    stocks: {
      all: ["institutional", "stocks"] as const,
      bySymbol: (symbol: string) =>
        ["institutional", "stocks", symbol] as const,
    },
  },
  me: {
    all: ["me"] as const,
    notifications: () => ["me", "notifications"] as const,
    auditLogs: (limit?: number, offset?: number, eventTypes?: string[]) =>
      [
        "me",
        "audit-logs",
        limit ?? null,
        offset ?? null,
        eventTypes?.length ? [...eventTypes].sort() : null,
      ] as const,
  },
  holdings: {
    all: ["holdings"] as const,
    accounts: {
      all: ["holdings", "accounts"] as const,
      list: () => ["holdings", "accounts", "list"] as const,
      detail: (id: number) => ["holdings", "accounts", id] as const,
    },
    trades: {
      all: ["holdings", "trades"] as const,
      list: (accountId?: number, limit?: number, offset?: number) =>
        ["holdings", "trades", "list", accountId, limit, offset] as const,
      detail: (id: number) => ["holdings", "trades", id] as const,
    },
    positions: {
      all: ["holdings", "positions"] as const,
      list: (accountId?: number) =>
        ["holdings", "positions", "list", accountId] as const,
      detail: (accountId: number, symbol: string, market: string) =>
        ["holdings", "positions", accountId, symbol, market] as const,
    },
    summary: {
      all: ["holdings", "summary"] as const,
      user: (baseCurrency?: string) =>
        ["holdings", "summary", "user", baseCurrency ?? null] as const,
      account: (accountId: number) =>
        ["holdings", "summary", "account", accountId] as const,
    },
    fx: {
      all: ["holdings", "fx"] as const,
      rate: (base: string, quote: string, asOf?: string) =>
        ["holdings", "fx", "rate", base, quote, asOf ?? null] as const,
    },
    dividends: {
      all: ["holdings", "dividends"] as const,
      list: (accountId?: number, limit?: number, offset?: number) =>
        ["holdings", "dividends", "list", accountId, limit, offset] as const,
      detail: (id: number) => ["holdings", "dividends", id] as const,
    },
    alerts: {
      all: ["holdings", "alerts"] as const,
      list: () => ["holdings", "alerts", "list"] as const,
    },
  },
} as const;
