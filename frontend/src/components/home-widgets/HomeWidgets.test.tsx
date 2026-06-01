// Home-widgets contract tests.
//
// Three components, all data-driven from `use-market-data` hooks. We mock the
// hooks and assert each tile renders its key fields when data is present.
// Visual layout / colour is left to manual screenshot review (per project
// convention with WatchlistRail / QuoteRow tests).

import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// ---- Hook mocks ----------------------------------------------------------
//
// We hand-tune the return values per test case via `mockReturnValue`.

const buffettState: {
  data: {
    ratio: string;
    label: "極度低估" | "低估" | "合理" | "高估" | "極度高估";
    historical_extreme: boolean;
    source_date: string;
    gdp_source: string;
    market_cap_source: string;
  } | null;
  isLoading: boolean;
} = {
  data: null,
  isLoading: false,
};

const temperatureState: {
  data: {
    score: string;
    label: "冷" | "正常" | "熱";
    average_change_percent: string;
    source_date: string;
    index_count: number;
  } | null;
  isLoading: boolean;
} = {
  data: null,
  isLoading: false,
};

interface MoverRow {
  symbol: string;
  name: string;
  market: string;
  close: string;
  change: string;
  change_percent: string;
  volume: number;
}

interface MoversShape {
  gainers: MoverRow[];
  losers: MoverRow[];
  most_active: MoverRow[];
  date: string | null;
}

const moversState: {
  data: MoversShape | null;
  isLoading: boolean;
} = {
  data: null,
  isLoading: false,
};

vi.mock("@/hooks/use-market-data", () => ({
  useBuffettIndicator: () => ({ ...buffettState }),
  useMarketTemperature: () => ({ ...temperatureState }),
  useMarketMovers: () => ({ ...moversState }),
}));

// Import AFTER mocks so the components see them.
import {
  BuffettIndicatorTile,
  MarketTemperatureTile,
  RankingsPanel,
} from "./index";

beforeEach(() => {
  buffettState.data = null;
  buffettState.isLoading = false;
  temperatureState.data = null;
  temperatureState.isLoading = false;
  moversState.data = null;
  moversState.isLoading = false;
});

// ---- BuffettIndicatorTile ------------------------------------------------

describe("BuffettIndicatorTile", () => {
  it("renders ratio and label when data is present", () => {
    buffettState.data = {
      ratio: "294.12",
      label: "極度高估",
      historical_extreme: true,
      source_date: "2026-05-28",
      gdp_source: "主計處 v1",
      market_cap_source: "fallback",
    };
    render(<BuffettIndicatorTile />);
    expect(screen.getByText("294.1%")).toBeInTheDocument();
    expect(screen.getByText("極度高估")).toBeInTheDocument();
    expect(screen.getByText("歷史極端區")).toBeInTheDocument();
  });

  it("renders skeleton while loading", () => {
    buffettState.data = null;
    buffettState.isLoading = true;
    const { container } = render(<BuffettIndicatorTile />);
    // Skeleton has no text content — the labels are gone.
    expect(container.querySelector("div")).toBeInTheDocument();
    expect(screen.queryByText(/Buffett/i)).toBeNull();
  });

  it("omits the historical-extreme chip in normal bucket", () => {
    buffettState.data = {
      ratio: "100.00",
      label: "合理",
      historical_extreme: false,
      source_date: "2026-05-28",
      gdp_source: "x",
      market_cap_source: "y",
    };
    render(<BuffettIndicatorTile />);
    expect(screen.getByText("合理")).toBeInTheDocument();
    expect(screen.queryByText("歷史極端區")).toBeNull();
  });
});

// ---- MarketTemperatureTile -----------------------------------------------

describe("MarketTemperatureTile", () => {
  it("renders label + needle position for hot reading", () => {
    temperatureState.data = {
      score: "85",
      label: "熱",
      average_change_percent: "2.10",
      source_date: "2026-05-28",
      index_count: 5,
    };
    render(<MarketTemperatureTile />);
    expect(screen.getByText(/熱/)).toBeInTheDocument();
    // The aria-valuenow attribute carries the score.
    const meter = screen.getByRole("meter");
    expect(meter.getAttribute("aria-valuenow")).toBe("85");
    expect(meter.getAttribute("aria-valuemax")).toBe("100");
  });

  it("renders 冷 label for cold reading", () => {
    temperatureState.data = {
      score: "15",
      label: "冷",
      average_change_percent: "-1.80",
      source_date: "2026-05-28",
      index_count: 5,
    };
    render(<MarketTemperatureTile />);
    expect(screen.getAllByText(/冷/).length).toBeGreaterThan(0);
  });
});

// ---- RankingsPanel -------------------------------------------------------

describe("RankingsPanel", () => {
  it("renders three columns with top movers", () => {
    moversState.data = {
      gainers: [
        {
          symbol: "2330",
          name: "TSMC",
          market: "TW_TWSE",
          close: "895.00",
          change: "35.00",
          change_percent: "4.07",
          volume: 45_000_000,
        },
      ],
      losers: [
        {
          symbol: "2317",
          name: "鴻海",
          market: "TW_TWSE",
          close: "142.00",
          change: "-5.50",
          change_percent: "-3.73",
          volume: 28_000_000,
        },
      ],
      most_active: [
        {
          symbol: "2891",
          name: "中信金",
          market: "TW_TWSE",
          close: "28.90",
          change: "-0.75",
          change_percent: "-2.53",
          volume: 42_000_000,
        },
      ],
      date: "2026-05-28",
    };
    render(<RankingsPanel />);
    expect(screen.getByText("漲幅排行")).toBeInTheDocument();
    expect(screen.getByText("跌幅排行")).toBeInTheDocument();
    expect(screen.getByText("成交量排行")).toBeInTheDocument();
    // One row per column.
    expect(screen.getByText("2330")).toBeInTheDocument();
    expect(screen.getByText("2317")).toBeInTheDocument();
    expect(screen.getByText("2891")).toBeInTheDocument();
  });

  it("renders skeleton rows when loading", () => {
    moversState.data = null;
    moversState.isLoading = true;
    render(<RankingsPanel />);
    // Headers still shown.
    expect(screen.getByText("漲幅排行")).toBeInTheDocument();
    // No data text either way.
    expect(screen.queryByText("2330")).toBeNull();
  });

  it("renders 無資料 placeholder when each column is empty post-load", () => {
    moversState.data = { gainers: [], losers: [], most_active: [], date: null };
    moversState.isLoading = false;
    render(<RankingsPanel />);
    const empties = screen.getAllByText("無資料");
    expect(empties.length).toBe(3);
  });
});
