import { test, expect } from "./setup";
import { mockAuth, fulfillJson } from "./fixtures/auth";

/**
 * /portfolio (Watchlist) E2E.
 *
 * The page is auth-gated client-side, so every test goes through mockAuth.
 * We mock:
 *   GET /api/v1/watchlist/         → list watchlist items
 *   GET /api/v1/prices/{symbol}    → per-row price strip
 *
 * Pricing endpoint is wildcarded because the page iterates `fetchPrices`
 * once per symbol. Returning canned OHLC keeps the row content stable.
 */

const MOCK_WATCHLIST_ITEMS = [
  { id: 1, symbol: "2330.TW", stock_name: "台積電", created_at: "2025-01-01T00:00:00Z" },
  { id: 2, symbol: "AAPL", stock_name: "Apple Inc.", created_at: "2025-01-02T00:00:00Z" },
];

const MOCK_PRICE_RES = {
  symbol: "2330.TW",
  data: [
    {
      date: "2025-05-23",
      open: "600",
      high: "660",
      low: "595",
      close: "650",
      volume: 12345678,
      change_percent: "1.56",
      market: "TW",
    },
  ],
};

async function mockWatchlistApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/watchlist/", (route) => {
    if (route.request().method() === "GET") {
      return fulfillJson(route, MOCK_WATCHLIST_ITEMS);
    }
    return fulfillJson(route, MOCK_WATCHLIST_ITEMS[0], 201);
  });

  // Per-symbol price strip. Wildcards swallow the `?limit=` query.
  await page.route("**/api/v1/prices/**", (route) =>
    fulfillJson(route, MOCK_PRICE_RES),
  );
}

test.describe("/portfolio watchlist page", () => {
  test("renders watchlist items from API", async ({ page }) => {
    await mockAuth(page, { tier: "pro" });
    await mockWatchlistApi(page);

    await page.goto("/portfolio");

    // Header label.
    await expect(
      page.getByRole("heading", { name: /自選股|Watchlist/i }),
    ).toBeVisible();
    // Both mocked symbols should render in the table.
    await expect(page.getByText("2330").first()).toBeVisible();
    await expect(page.getByText("AAPL").first()).toBeVisible();
  });

  test("shows Free-tier near-limit warning at 80% capacity", async ({ page }) => {
    // Free tier cap is 10 items, near-limit threshold is 8.
    const eightItems = Array.from({ length: 8 }).map((_, i) => ({
      id: i + 1,
      symbol: `SYM${i}`,
      stock_name: `Mock ${i}`,
      created_at: "2025-01-01T00:00:00Z",
    }));

    await mockAuth(page, { tier: "free" });
    await page.route("**/api/v1/watchlist/", (route) =>
      fulfillJson(route, eightItems),
    );
    await page.route("**/api/v1/prices/**", (route) =>
      fulfillJson(route, { symbol: "SYM0", data: [] }),
    );

    await page.goto("/portfolio");
    await expect(page.getByText(/接近上限.*8\/10|Free 上限/).first()).toBeVisible();
  });

  test("localStorage migration banner appears when legacy data exists", async ({
    page,
  }) => {
    await mockAuth(page, { tier: "pro" });
    await mockWatchlistApi(page);

    // Pre-seed legacy localStorage key BEFORE first paint. The page's
    // migration effect only fires if `hasLegacyWatchlist()` returns true.
    await page.addInitScript(() => {
      try {
        localStorage.setItem(
          "uni-seeker-watchlist",
          JSON.stringify(["2330.TW", "AAPL"]),
        );
      } catch {
        /* ignore */
      }
    });

    await page.goto("/portfolio");

    // Either the "syncing" spinner banner or the post-migration result
    // banner should appear. We match either copy.
    await expect(
      page
        .getByText(/正在將本機 Watchlist 同步至雲端|Watchlist 已從本機遷移/)
        .first(),
    ).toBeVisible();
  });

  test("EXPORT CSV triggers a download", async ({ page }) => {
    await mockAuth(page, { tier: "pro" });
    await mockWatchlistApi(page);

    await page.goto("/portfolio");

    // Wait until table populated so the export button is enabled.
    await expect(page.getByText("2330").first()).toBeVisible();

    // Listen for the download triggered by `a.click()` in downloadCSV.
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: /EXPORT CSV/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("watchlist.csv");
  });
});
