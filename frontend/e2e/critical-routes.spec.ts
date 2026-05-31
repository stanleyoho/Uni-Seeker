import { test, expect } from "./setup";
import { mockAuth, fulfillJson } from "./fixtures/auth";

/**
 * /critical-routes E2E (PR: fix/critical-routes).
 *
 * Locks the five route fixes in this PR so they cannot silently
 * regress:
 *
 *   1. /portfolio                — must render the dashboard
 *                                  (KPIs + Positions + Watchlist
 *                                  preview), NOT the watchlist UI
 *                                  itself.
 *   2. /portfolio/watchlist      — the legacy watchlist UI moved here.
 *   3. /scanner                  — must permanent-redirect to /research.
 *   4. /login                    — must render the login form, NOT the
 *                                  stock-detail layout. Locks the bug
 *                                  the day-trader audit reported.
 *   5. /alerts CREATE NEW RULE   — must open the inline builder, NOT
 *                                  navigate elsewhere.
 *
 * All specs use the network-mock auth path so they run in the local
 * `next dev` mode without needing the docker backend. Tests that need
 * real data sit in their own dedicated suites (see
 * `portfolio-watchlist.spec.ts` for the docker leg).
 */

const MOCK_SUMMARY = {
  user_id: 1,
  base_currency: "TWD",
  total_market_value: "1000000",
  total_cost: "900000",
  total_unrealized_pnl: "100000",
  total_unrealized_pnl_pct: "11.11",
  total_realized_pnl: "0",
  total_dividends: "0",
  account_count: 1,
  position_count: 1,
};

const MOCK_POSITIONS_RES = {
  positions: [
    {
      symbol: "2330.TW",
      stock_name: "台積電",
      qty: "100",
      avg_cost: "600",
      last_price: "650",
      market_value: "65000",
      cost_basis: "60000",
      unrealized_pnl: "5000",
      unrealized_pnl_pct: "8.33",
      realized_pnl: "0",
      daily_change: "10",
      daily_change_pct: "1.56",
      currency: "TWD",
      market: "TW",
    },
  ],
};

const MOCK_WATCHLIST = [
  {
    id: 1,
    symbol: "2330.TW",
    stock_name: "台積電",
    created_at: "2025-01-01T00:00:00Z",
  },
  {
    id: 2,
    symbol: "AAPL",
    stock_name: "Apple Inc.",
    created_at: "2025-01-02T00:00:00Z",
  },
];

async function mockPortfolioDashboardApis(
  page: import("@playwright/test").Page,
) {
  await page.route("**/api/v1/holdings/summary**", (route) =>
    fulfillJson(route, MOCK_SUMMARY),
  );
  await page.route("**/api/v1/holdings/positions**", (route) =>
    fulfillJson(route, MOCK_POSITIONS_RES),
  );
  await page.route("**/api/v1/holdings/accounts**", (route) =>
    fulfillJson(route, []),
  );
  await page.route("**/api/v1/watchlist/", (route) =>
    fulfillJson(route, MOCK_WATCHLIST),
  );
  await page.route("**/api/v1/prices/**", (route) =>
    fulfillJson(route, { symbol: "MOCK", data: [] }),
  );
}

test.describe("critical routes — PR fix/critical-routes", () => {
  test("/portfolio renders the dashboard (KPIs + Positions + Watchlist)", async ({
    page,
  }) => {
    await mockAuth(page, { tier: "pro" });
    await mockPortfolioDashboardApis(page);

    await page.goto("/portfolio");

    // URL must stay on /portfolio — must NOT silently redirect.
    await expect(page).toHaveURL(/\/portfolio$/);

    // Dashboard title (not the watchlist's "Watchlist Management").
    await expect(
      page.getByRole("heading", { level: 1, name: /portfolio/i }),
    ).toBeVisible();

    // Positions panel header from the new dashboard.
    await expect(page.getByText(/^POSITIONS$/)).toBeVisible();

    // Watchlist preview panel header carries the count.
    await expect(page.getByText(/^WATCHLIST · \d+$/)).toBeVisible();

    // The first watchlist row links to the stock detail.
    const analyzeLink = page
      .getByRole("link", { name: /^ANALYZE$/ })
      .first();
    await expect(analyzeLink).toBeVisible();
    await expect(analyzeLink).toHaveAttribute("href", /\/stocks\//);
  });

  test("/portfolio/watchlist still renders the watchlist UI", async ({
    page,
  }) => {
    await mockAuth(page, { tier: "pro" });
    await mockPortfolioDashboardApis(page);

    await page.goto("/portfolio/watchlist");
    await expect(page).toHaveURL(/\/portfolio\/watchlist$/);

    // The relocated watchlist keeps its "Watchlist Management" header.
    await expect(
      page.getByRole("heading", { name: /watchlist management/i }),
    ).toBeVisible();
  });

  test("/scanner permanent-redirects to /research", async ({ page }) => {
    await mockAuth(page, { tier: "pro" });
    // Stub out the research-page data calls so it doesn't error mid-load.
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{}",
      }),
    );

    await page.goto("/scanner");

    // The redirect must land us on /research (NOT 404).
    await expect(page).toHaveURL(/\/research$/, { timeout: 10_000 });
    // And we should NOT see Next.js's 404 page chrome.
    await expect(page.getByText(/404|this page could not be found/i)).toHaveCount(0);
  });

  test("/login renders the login form, NOT a stock-detail page", async ({
    page,
  }) => {
    await page.goto("/login");
    await expect(page).toHaveURL(/\/login$/);

    // The login form has an email + password input.
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();

    // The stock-detail page exposes a `StockChart` container + timeframe
    // buttons. Their absence here proves we're not being shadowed.
    await expect(page.getByRole("button", { name: /^1M$/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^1Y$/ })).toHaveCount(0);
  });

  test("/alerts CREATE NEW RULE opens inline builder (no /heatmap nav)", async ({
    page,
  }) => {
    await mockAuth(page, { tier: "pro" });
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      }),
    );

    await page.goto("/alerts");
    await expect(page).toHaveURL(/\/alerts$/);

    const createBtn = page.getByRole("button", { name: /create new rule/i });
    await expect(createBtn).toBeVisible();

    await createBtn.click();

    // Must STILL be on /alerts — not bounced to /heatmap.
    await expect(page).toHaveURL(/\/alerts$/);
    // The inline builder panel must appear.
    await expect(
      page.getByPlaceholder(/name your alert rule/i),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /save & activate/i }),
    ).toBeVisible();

    // Re-clicking the CTA (now labeled CANCEL) closes the builder.
    await page.getByRole("button", { name: /^cancel$/i }).click();
    await expect(
      page.getByPlaceholder(/name your alert rule/i),
    ).not.toBeVisible();
    await expect(page).toHaveURL(/\/alerts$/);
  });
});
