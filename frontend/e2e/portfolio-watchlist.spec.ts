import { test as baseTest, expect } from "./setup";
import { test as authTest, mockAuth, fulfillJson } from "./fixtures/auth";

/**
 * /portfolio (Watchlist) E2E.
 *
 * Dual-mode:
 *   - Mock: keeps the original page.route-driven coverage so the
 *     watchlist UI can be iterated on without a backend.
 *   - Docker: real-stack add/remove flow against the seeded user.
 *     The seed inserts ONE watchlist item (2330). We add a second
 *     symbol, assert it shows up, then delete it.
 */

const isDocker = process.env.E2E_TARGET === "docker";

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
  await page.route("**/api/v1/prices/**", (route) =>
    fulfillJson(route, MOCK_PRICE_RES),
  );
}

// ── Mock-mode suite ─────────────────────────────────────────────────────────

baseTest.describe("/portfolio watchlist page (mock mode)", () => {
  baseTest.skip(isDocker, "covered by docker suite");

  baseTest("renders watchlist items from API", async ({ page }) => {
    await mockAuth(page, { tier: "pro" });
    await mockWatchlistApi(page);

    await page.goto("/portfolio/watchlist");

    await expect(
      page.getByRole("heading", { name: /自選股|Watchlist/i }),
    ).toBeVisible();
    await expect(page.getByText("2330").first()).toBeVisible();
    await expect(page.getByText("AAPL").first()).toBeVisible();
  });

  baseTest("shows Free-tier near-limit warning at 80% capacity", async ({ page }) => {
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

    await page.goto("/portfolio/watchlist");
    await expect(page.getByText(/接近上限.*8\/10|Free 上限/).first()).toBeVisible();
  });

  baseTest("localStorage migration banner appears when legacy data exists", async ({
    page,
  }) => {
    await mockAuth(page, { tier: "pro" });
    await mockWatchlistApi(page);

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

    await page.goto("/portfolio/watchlist");

    await expect(
      page
        .getByText(/正在將本機 Watchlist 同步至雲端|Watchlist 已從本機遷移/)
        .first(),
    ).toBeVisible();
  });

  baseTest("EXPORT CSV triggers a download", async ({ page }) => {
    await mockAuth(page, { tier: "pro" });
    await mockWatchlistApi(page);

    await page.goto("/portfolio/watchlist");
    await expect(page.getByText("2330").first()).toBeVisible();

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: /EXPORT CSV/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("watchlist.csv");
  });
});

// ── Docker-backed suite (E2E-3) ─────────────────────────────────────────────

authTest.describe("/portfolio watchlist page (docker e2e)", () => {
  authTest.skip(!isDocker, "docker-only suite");

  authTest(
    "renders the seeded 2330 watchlist row, then removes it",
    async ({ loggedInPage: page }) => {
      // Why no add-AAPL leg? The portfolio page no longer ships an
      // in-page "add symbol" input — adding to the watchlist now goes
      // through the FOLLOW button on /stocks/[symbol]. The cross-page
      // add/remove round-trip is exercised by the dedicated stock
      // detail spec; here we keep the contract focused on the seed
      // shape that this page is supposed to render, plus the remove
      // mutation which IS reachable in-page.
      //
      // Route history: pre-PR-115, `/portfolio` rendered the watchlist
      // UI inline. Post-PR-115, `/portfolio` is the dashboard and the
      // canonical watchlist surface moved to `/portfolio/watchlist`.
      // The in-page remove affordance lives on that child route.
      await page.goto("/portfolio/watchlist");

      // The page's H1 uses the i18n'd watchlist title (`自選股` under
      // zh-TW, "Watchlist Management" as the English fallback). Accept
      // both so we don't break the spec when the default locale flips.
      await expect(
        page.getByRole("heading", {
          level: 1,
          name: /Watchlist Management|自選股|Watchlist/i,
        }),
      ).toBeVisible({ timeout: 15_000 });

      // Seed inserts a 2330 watchlist row.
      await expect(page.getByText("2330").first()).toBeVisible({
        timeout: 15_000,
      });

      // Remove 2330 in-row. Each row's "Actions" cell has a trash
      // affordance with an accessible name like
      // `Remove 2330 from watchlist` (the icon button also exposes a
      // /title/, so the regex catches both legacy "DELETE"/"移除" copy
      // and the current STRATOS a11y label).
      //
      // The action cell is `opacity-0 group-hover:opacity-100` — visible
      // to the a11y tree (Playwright treats opacity:0 as visible) but
      // hovering the row first is more faithful to user intent and keeps
      // the assertion robust if the cell ever switches to display:none.
      const row2330 = page.locator("tr").filter({ hasText: "2330" }).first();
      await row2330.hover();
      const deleteBtn = row2330
        .getByRole("button", {
          name: /Remove .* from watchlist|DELETE|刪除|移除|REMOVE|×/i,
        })
        .first();
      await deleteBtn.click();

      // 2330 should disappear from the list (DELETE /watchlist/{id}
      // resolves, the list invalidates and re-fetches without it).
      await expect(page.getByText("2330").first()).toBeHidden({
        timeout: 15_000,
      });
    },
  );
});
