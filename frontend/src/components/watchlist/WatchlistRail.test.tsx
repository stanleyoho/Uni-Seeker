// WatchlistRail tests — covers the auth-state branches:
//   - unauthenticated → "登入後追蹤" CTA
//   - authenticated + empty → "尚未追蹤任何標的" hint
//   - authenticated + items → list of QuoteRow links
//
// We mock the auth + watchlist API hooks so this test does not need real
// providers (AuthContext/QueryClient/I18nProvider) in the tree.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// ---- Mocks ---------------------------------------------------------------

const authState: {
  user: { username: string } | null;
  loading: boolean;
} = { user: null, loading: false };

vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({ ...authState, token: null, setToken: vi.fn(), logout: vi.fn() }),
}));

const watchlistState: {
  data: Array<{
    id: number;
    symbol: string;
    stock_name?: string | null;
    created_at: string;
  }>;
  isLoading: boolean;
} = { data: [], isLoading: false };

vi.mock("@/hooks/use-watchlist-api", () => ({
  useWatchlistApi: () => ({ ...watchlistState }),
}));

vi.mock("@/i18n/context", () => ({
  useI18n: () => ({
    t: { watchlist: { title: "自選股" } },
    locale: "zh-TW",
    setLocale: vi.fn(),
  }),
}));

// Import AFTER mocks so the component sees them.
import { WatchlistRail } from "./WatchlistRail";

beforeEach(() => {
  authState.user = null;
  authState.loading = false;
  watchlistState.data = [];
  watchlistState.isLoading = false;
});

describe("WatchlistRail", () => {
  it("renders the login CTA when the user is unauthenticated", () => {
    render(<WatchlistRail />);
    expect(screen.getByTestId("watchlist-rail-cta")).toBeInTheDocument();
    expect(screen.getByText(/登入後追蹤你的自選股/)).toBeInTheDocument();
    // CTA links to /login.
    const link = screen.getByRole("link", { name: /登入 \/ 註冊/ });
    expect(link.getAttribute("href")).toBe("/login");
  });

  it("renders the empty-state hint when the user is authed but list is empty", () => {
    authState.user = { username: "stanley" };
    render(<WatchlistRail />);
    expect(screen.getByTestId("watchlist-rail-empty")).toBeInTheDocument();
    expect(screen.getByText(/尚未追蹤任何標的/)).toBeInTheDocument();
  });

  it("renders one QuoteRow per watchlist item with the right href", () => {
    authState.user = { username: "stanley" };
    watchlistState.data = [
      { id: 1, symbol: "2330.TW", stock_name: "台積電", created_at: "2026-01-01T00:00:00Z" },
      { id: 2, symbol: "AAPL", stock_name: "Apple Inc.", created_at: "2026-01-02T00:00:00Z" },
    ];
    render(<WatchlistRail />);
    expect(screen.queryByTestId("watchlist-rail-empty")).toBeNull();
    expect(screen.queryByTestId("watchlist-rail-cta")).toBeNull();
    // TW suffix is stripped for display by QuoteRow.
    expect(screen.getByText("2330")).toBeInTheDocument();
    expect(screen.getByText("台積電")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
    // Each row should be a Link to /stocks/<symbol> (encoded).
    const tsmcLink = document.querySelector('a[href="/stocks/2330.TW"]');
    expect(tsmcLink).not.toBeNull();
    const aaplLink = document.querySelector('a[href="/stocks/AAPL"]');
    expect(aaplLink).not.toBeNull();
  });

  it("shows a skeleton placeholder while auth is loading", () => {
    authState.loading = true;
    render(<WatchlistRail />);
    expect(screen.getByTestId("watchlist-rail-skeleton")).toBeInTheDocument();
  });
});
