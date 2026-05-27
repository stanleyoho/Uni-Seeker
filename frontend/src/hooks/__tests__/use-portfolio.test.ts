import { describe, expect, it } from "vitest";
import { mapApiResponse } from "@/hooks/use-portfolio";
import type {
  PortfolioBacktestParams,
} from "@/hooks/use-portfolio";
import type { PortfolioBacktestResponse } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// mapApiResponse is the pure transform sitting between the backend's
// `PortfolioBacktestResponse` and the frontend's `PortfolioBacktestResult`.
// It's the load-bearing piece of use-portfolio.ts: the W2 drift bug —
// backend renames `sharpe_ratio` → `sharpe` — must NOT regress.
// ---------------------------------------------------------------------------

const baseParams: PortfolioBacktestParams = {
  allocations: [
    { symbol: "2330", weight: 60, strategy: "buy_and_hold" },
    { symbol: "2317", weight: 40, strategy: "buy_and_hold" },
  ],
  rebalance_mode: "none",
  initial_capital: 1_000_000,
};

function makeResponse(
  overrides: Partial<PortfolioBacktestResponse> = {},
): PortfolioBacktestResponse {
  return {
    portfolio_metrics: {
      total_return: 0.25,
      annualized_return: 0.1,
      max_drawdown: -0.15,
      sharpe: 1.42, // backend uses `sharpe`, frontend reads as `sharpe_ratio`
    },
    individual_metrics: {
      "2330": {
        total_return: 0.3,
        annualized_return: 0.12,
        sharpe_ratio: 1.6,
        win_rate: 0.55,
        max_drawdown: -0.12,
      },
      "2317": {
        total_return: 0.15,
        annualized_return: 0.07,
        sharpe_ratio: 0.9,
        win_rate: 0.5,
        max_drawdown: -0.2,
      },
    },
    portfolio_equity_curve: [1_000_000, 1_100_000, 1_250_000],
    individual_equity_curves: {
      "2330": [1, 1.1, 1.3],
      "2317": [1, 1.05, 1.15],
    },
    trade_log: [],
    rebalance_log: [],
    allocations: [],
    ...overrides,
  };
}

describe("mapApiResponse", () => {
  it("renames portfolio_metrics.sharpe → sharpe_ratio (W2 drift guard)", () => {
    const out = mapApiResponse(makeResponse(), baseParams);
    expect(out.sharpe_ratio).toBe(1.42);
  });

  it("passes through total_return / annualized_return / max_drawdown verbatim", () => {
    const out = mapApiResponse(makeResponse(), baseParams);
    expect(out.total_return).toBe(0.25);
    expect(out.annualized_return).toBe(0.1);
    expect(out.max_drawdown).toBe(-0.15);
  });

  it("builds stock_metrics from individual_metrics keyed by allocation symbol", () => {
    const out = mapApiResponse(makeResponse(), baseParams);
    expect(out.stock_metrics).toHaveLength(2);
    const tsmc = out.stock_metrics.find((m) => m.symbol === "2330");
    expect(tsmc).toEqual({
      symbol: "2330",
      weight: 60,
      total_return: 0.3,
      annualized_return: 0.12,
      sharpe_ratio: 1.6,
      win_rate: 0.55,
      max_drawdown: -0.12,
    });
  });

  it("falls back to 0 for missing or non-numeric per-symbol metrics", () => {
    const res = makeResponse({
      individual_metrics: {
        "2330": {}, // empty — all metrics missing
        "2317": { sharpe_ratio: "not-a-number" }, // wrong type
      },
    });
    const out = mapApiResponse(res, baseParams);
    const tsmc = out.stock_metrics.find((m) => m.symbol === "2330")!;
    expect(tsmc.total_return).toBe(0);
    expect(tsmc.sharpe_ratio).toBe(0);
    const hh = out.stock_metrics.find((m) => m.symbol === "2317")!;
    expect(hh.sharpe_ratio).toBe(0); // string coerced to 0 by `asNum`
  });

  it("falls back to 0 for symbols entirely absent from individual_metrics", () => {
    const res = makeResponse({ individual_metrics: {} });
    const out = mapApiResponse(res, baseParams);
    expect(out.stock_metrics.every((m) => m.total_return === 0)).toBe(true);
    expect(out.stock_metrics).toHaveLength(2); // still one row per allocation
  });

  it("forwards equity curve + per-symbol curves unchanged", () => {
    const out = mapApiResponse(makeResponse(), baseParams);
    expect(out.portfolio_equity).toEqual([1_000_000, 1_100_000, 1_250_000]);
    expect(out.stock_equities).toEqual({
      "2330": [1, 1.1, 1.3],
      "2317": [1, 1.05, 1.15],
    });
  });

  it("emits one ISO date per equity-curve point", () => {
    const out = mapApiResponse(makeResponse(), baseParams);
    expect(out.dates).toHaveLength(3);
    // First date is anchored at 2024-01-02 per the mapping implementation.
    expect(out.dates[0]).toBe("2024-01-02");
    out.dates.forEach((d) => expect(d).toMatch(/^\d{4}-\d{2}-\d{2}$/));
  });

  it("normalises a missing rebalance_log to []", () => {
    // The generated schema technically requires rebalance_log, but the SUT
    // defends with `?? []`. Cast through unknown to exercise that branch.
    const res = makeResponse();
    delete (res as unknown as { rebalance_log?: unknown }).rebalance_log;
    const out = mapApiResponse(res, baseParams);
    expect(out.rebalance_log).toEqual([]);
  });

  it("preserves rebalance log entry fields", () => {
    const res = makeResponse({
      rebalance_log: [
        {
          date: "2024-06-15",
          reason: "periodic",
          adjustments: [
            { symbol: "2330", from_weight: 60, to_weight: 55 },
          ],
        },
      ],
    });
    const out = mapApiResponse(res, baseParams);
    expect(out.rebalance_log).toEqual([
      {
        date: "2024-06-15",
        reason: "periodic",
        adjustments: [
          { symbol: "2330", from_weight: 60, to_weight: 55 },
        ],
      },
    ]);
  });
});
