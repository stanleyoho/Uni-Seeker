// K4 婆媽 portfolio widgets — contract tests.
//
// Two tiles: 今日盈虧 (reuses summary.total_daily_change) + 本月股息收入
// (its own monthly-summary hook). We mock the dividend hook and feed the
// summary in via props, asserting:
//   - net/gross/cash-count render from the monthly-summary payload
//   - STOCK 配股 count line appears only when stock_count > 0 (money is
//     CASH-only, so the figure never reflects 配股)
//   - 今日盈虧 sign + colour follow the Taiwan 紅漲綠跌 convention
//     (--stock-up for a gain, --stock-down for a loss)
//   - skeletons render while either data source is loading
//
// Visual layout is left to manual / Playwright screenshot review, per the
// HomeWidgets / WatchlistRail convention in this repo.

import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider } from "@/i18n/context";
import type { HoldingSummary } from "@/lib/api-client";

const monthlyState: {
  data:
    | {
        month: string;
        gross_amount: string;
        net_amount: string;
        cash_count: number;
        stock_count: number;
      }
    | undefined;
  isLoading: boolean;
} = { data: undefined, isLoading: false };

vi.mock("@/hooks/use-holdings", () => ({
  useMonthlyDividendSummary: () => ({ ...monthlyState }),
}));

// Import AFTER the mock so the component binds to it.
import { PopoSummaryWidgets } from "./popo-summary-widgets";

function renderWidgets(props: Parameters<typeof PopoSummaryWidgets>[0]) {
  return render(
    <I18nProvider>
      <PopoSummaryWidgets {...props} />
    </I18nProvider>,
  );
}

const baseSummary: HoldingSummary = {
  total_cost: "100000",
  total_value: "110000",
  total_unrealized_pnl: "10000",
  total_daily_change: "1500",
  gain_simple: "10000",
  gain_simple_pct: "10",
  position_count: 3,
  account_count: 1,
};

beforeEach(() => {
  monthlyState.data = undefined;
  monthlyState.isLoading = false;
});

describe("PopoSummaryWidgets — 本月股息收入", () => {
  it("renders net amount, gross, and cash count from the payload", () => {
    monthlyState.data = {
      month: "2026-06",
      gross_amount: "5000",
      net_amount: "4500",
      cash_count: 2,
      stock_count: 0,
    };
    renderWidgets({ summary: baseSummary });
    // Net is the headline figure (本月實收淨額).
    expect(screen.getByText(/4,500/)).toBeInTheDocument();
    // Gross + cash-count line.
    expect(screen.getByText(/5,000/)).toBeInTheDocument();
    expect(screen.getByText(/2 筆現金股利/)).toBeInTheDocument();
  });

  it("shows the 配股 count line only when stock_count > 0", () => {
    monthlyState.data = {
      month: "2026-06",
      gross_amount: "300",
      net_amount: "300",
      cash_count: 1,
      stock_count: 2,
    };
    renderWidgets({ summary: baseSummary });
    expect(screen.getByText(/另有配股 2 筆/)).toBeInTheDocument();
  });

  it("omits the 配股 line when stock_count is 0", () => {
    monthlyState.data = {
      month: "2026-06",
      gross_amount: "300",
      net_amount: "300",
      cash_count: 1,
      stock_count: 0,
    };
    renderWidgets({ summary: baseSummary });
    expect(screen.queryByText(/另有配股/)).toBeNull();
  });

  it("renders a skeleton while the monthly summary is loading", () => {
    monthlyState.data = undefined;
    monthlyState.isLoading = true;
    renderWidgets({ summary: baseSummary });
    // The dividend headline text is absent during the skeleton phase.
    expect(screen.queryByText(/筆現金股利/)).toBeNull();
  });
});

describe("PopoSummaryWidgets — 今日盈虧 (紅漲綠跌)", () => {
  it("uses --stock-up colour for a positive daily change", () => {
    monthlyState.data = {
      month: "2026-06",
      gross_amount: "0",
      net_amount: "0",
      cash_count: 0,
      stock_count: 0,
    };
    renderWidgets({ summary: baseSummary });
    const tile = screen.getByTestId("popo-today-pnl");
    // +1,500 headline with the gain (red) token.
    const headline = screen.getByText(/\+1,500/);
    expect(headline).toBeInTheDocument();
    expect(tile.innerHTML).toContain("var(--stock-up)");
  });

  it("uses --stock-down colour for a negative daily change", () => {
    monthlyState.data = {
      month: "2026-06",
      gross_amount: "0",
      net_amount: "0",
      cash_count: 0,
      stock_count: 0,
    };
    renderWidgets({
      summary: { ...baseSummary, total_daily_change: "-2000" },
    });
    const tile = screen.getByTestId("popo-today-pnl");
    expect(screen.getByText(/-2,000/)).toBeInTheDocument();
    expect(tile.innerHTML).toContain("var(--stock-down)");
  });

  it("renders a skeleton while the summary is loading", () => {
    renderWidgets({ summary: undefined, summaryLoading: true });
    expect(screen.queryByTestId("popo-today-pnl")).toBeNull();
  });
});
