// WatchlistLivePanel tests — covers:
//   - empty symbols → empty-state hint
//   - error state → error message
//   - happy path → one row per symbol with price/RSI/MA-cross rendered,
//     Taiwan 紅漲綠跌 colour applied via pnlColor
//   - freshness dot flashes when `dataUpdatedAt` advances (auto-refresh cue)
//
// We mock `useWatchlistIndicators` so the test does not need a real
// QueryClient / network; the hook's polling is exercised in the api-client
// + hook layers, not here.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import type { WatchlistLiveIndicator } from "@/lib/api-client";

// ---- Mock the polling hook -----------------------------------------------

const hookState: {
  data: WatchlistLiveIndicator[];
  isLoading: boolean;
  isError: boolean;
  dataUpdatedAt: number;
} = { data: [], isLoading: false, isError: false, dataUpdatedAt: 0 };

vi.mock("@/hooks/use-watchlist-indicators", () => ({
  WATCHLIST_POLL_INTERVAL_MS: 15000,
  useWatchlistIndicators: () => ({ ...hookState }),
}));

import { WatchlistLivePanel } from "./WatchlistLivePanel";

function mkItem(
  overrides: Partial<WatchlistLiveIndicator> & { symbol: string },
): WatchlistLiveIndicator {
  return {
    last_price: null,
    prev_close: null,
    change: null,
    change_percent: null,
    rsi: null,
    ma_short: null,
    ma_long: null,
    ma_cross: null,
    pct_from_ma_long: null,
    ...overrides,
  };
}

beforeEach(() => {
  hookState.data = [];
  hookState.isLoading = false;
  hookState.isError = false;
  hookState.dataUpdatedAt = 0;
});

describe("WatchlistLivePanel", () => {
  it("renders the empty-state when there are no symbols", () => {
    render(<WatchlistLivePanel symbols={[]} />);
    expect(screen.getByTestId("watchlist-live-empty")).toBeInTheDocument();
  });

  it("renders an error message when the query errors", () => {
    hookState.isError = true;
    render(<WatchlistLivePanel symbols={["2330.TW"]} />);
    expect(screen.getByTestId("watchlist-live-error")).toBeInTheDocument();
  });

  it("renders one row per symbol with price, RSI and MA cross", () => {
    hookState.data = [
      mkItem({
        symbol: "2330.TW",
        last_price: "150.0000",
        change: "10.0000",
        change_percent: "7.1400",
        rsi: "72.5000",
        ma_cross: "golden",
        pct_from_ma_long: "5.2000",
      }),
      mkItem({
        symbol: "AAPL",
        last_price: "180.0000",
        change: "-2.0000",
        change_percent: "-1.1000",
        rsi: "28.0000",
        ma_cross: "death",
        pct_from_ma_long: "-3.4000",
      }),
    ];
    render(<WatchlistLivePanel symbols={["2330.TW", "AAPL"]} />);

    // One row per symbol; TW suffix stripped for the symbol cell.
    expect(
      screen.getByTestId("watchlist-live-row-2330.TW"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-live-row-AAPL")).toBeInTheDocument();
    expect(screen.getByText("2330")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();

    // Price + RSI rendered.
    expect(screen.getByText("150.00")).toBeInTheDocument();
    expect(screen.getByText("72.5")).toBeInTheDocument();
    expect(screen.getByText("28.0")).toBeInTheDocument();

    // MA cross labels.
    expect(screen.getByText("黃金交叉")).toBeInTheDocument();
    expect(screen.getByText("死亡交叉")).toBeInTheDocument();
  });

  it("applies 紅漲綠跌 colour to the gain/loss cell (red up, green down)", () => {
    hookState.data = [
      mkItem({
        symbol: "UP",
        last_price: "10.0000",
        change: "1.0000",
        change_percent: "11.0000",
      }),
      mkItem({
        symbol: "DN",
        last_price: "10.0000",
        change: "-1.0000",
        change_percent: "-9.0000",
      }),
    ];
    render(<WatchlistLivePanel symbols={["UP", "DN"]} />);

    const up = screen.getByText(/\+1\.00 \(\+11\.00%\)/);
    const dn = screen.getByText(/-1\.00 \(-9\.00%\)/);
    // pnlColor: positive → --stock-up (red), negative → --stock-down (green).
    expect(up).toHaveStyle({ color: "var(--stock-up)" });
    expect(dn).toHaveStyle({ color: "var(--stock-down)" });
  });

  it("flashes the freshness dot when a new poll lands (dataUpdatedAt changes)", () => {
    hookState.data = [mkItem({ symbol: "2330.TW", last_price: "100.0000" })];
    hookState.dataUpdatedAt = 1000;
    const { rerender } = render(<WatchlistLivePanel symbols={["2330.TW"]} />);

    const dot = screen.getByTestId("watchlist-live-dot");
    // Initial mount: not flashing.
    expect(dot.getAttribute("data-flash")).toBe("false");

    // Simulate a fresh poll → dataUpdatedAt advances.
    act(() => {
      hookState.dataUpdatedAt = 2000;
      rerender(<WatchlistLivePanel symbols={["2330.TW"]} />);
    });
    expect(
      screen.getByTestId("watchlist-live-dot").getAttribute("data-flash"),
    ).toBe("true");
  });
});
