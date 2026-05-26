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

    await page.goto("/portfolio");

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

    await page.goto("/portfolio");
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

    await page.goto("/portfolio");

    await expect(
      page
        .getByText(/正在將本機 Watchlist 同步至雲端|Watchlist 已從本機遷移/)
        .first(),
    ).toBeVisible();
  });

  baseTest("EXPORT CSV triggers a download", async ({ page }) => {
    await mockAuth(page, { tier: "pro" });
    await mockWatchlistApi(page);

    await page.goto("/portfolio");
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
    "renders the seeded 2330 watchlist item, then add → remove AAPL round-trip",
    async ({ loggedInPage: page }) => {
      await page.goto("/portfolio");

      await expect(
        page.getByRole("heading", { name: /自選股|Watchlist/i }),
      ).toBeVisible({ timeout: 15_000 });

      // Seed inserts a 2330 watchlist row.
      await expect(page.getByText("2330").first()).toBeVisible({
        timeout: 15_000,
      });

      // Add AAPL. The page has an input + "ADD" button — exact copy
      // varies; we match by placeholder + role generously.
      const addInput = page
        .locator('input[type="text"]')
        .filter({ hasNot: page.locator(":disabled") })
        .first();
      await addInput.fill("AAPL");
      await page
        .getByRole("button", { name: /^\s*(\+\s*)?ADD\b|新增|加入/i })
        .first()
        .click();

      // Wait for AAPL to appear (POST /watchlist returns the new row,
      // the list invalidates and re-fetches).
      await expect(page.getByText("AAPL").first()).toBeVisible({
        timeout: 15_000,
      });

      // Remove AAPL. Each row has a delete affordance — match the row
      // containing "AAPL" and click its delete button.
      // Look for a button with "DELETE" or trash icon labelled "remove"
      // in the row's vicinity. Fallback: any button in the AAPL row.
      const aaplRow = page
        .locator("tr,div")
        .filter({ hasText: "AAPL" })
        .first();
      const deleteBtn = aaplRow
        .getByRole("button", { name: /DELETE|刪除|移除|remove|REMOVE|×/i })
        .first();
      await deleteBtn.click();

      // AAPL should disappear from the list.
      await expect(page.getByText("AAPL").first()).toBeHidden({
        timeout: 15_000,
      });
    },
  );
});
