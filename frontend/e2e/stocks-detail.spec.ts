import { test, expect } from "./setup";

/**
 * /stocks/[symbol] E2E.
 *
 * Stanley flagged a real bug: "/stocks/2330 render OK but data broken —
 * Daily Stats 全是 0 + 股票名 fallback 2" — meaning the company name
 * fell back to the path param ("2") when the company-info fetch failed
 * or returned empty. This spec exists specifically to prevent a regression
 * of that bug. We assert the page renders the SEEDED company NAME
 * ("台積電"), not just the symbol.
 *
 * Docker-only because the seed step provisions the stocks row.
 */

const isDocker = process.env.E2E_TARGET === "docker";

test.describe("/stocks/[symbol] page (docker e2e)", () => {
  test.skip(!isDocker, "requires E2E_TARGET=docker (seeded stocks table)");

  test(
    "renders the seeded company NAME for 2330 (regression: no fallback to '2')",
    async ({ page }) => {
      const response = await page.goto("/stocks/2330");
      expect(response?.status()).toBeLessThan(400);

      // Header chrome renders.
      await expect(page.locator("header")).toBeVisible();

      // The seed inserts Stock(symbol="2330", name="台積電"). The page's
      // /company/{symbol} call should resolve and the rendered title /
      // breadcrumb should contain the Chinese company name.
      //
      // This is the load-bearing assertion for the regression: prior
      // bug had the name fall back to the path segment "2" because
      // the /company endpoint silently returned an empty name.
      await expect(page.getByText("台積電").first()).toBeVisible({
        timeout: 15_000,
      });

      // Symbol still surfaces (basic sanity).
      await expect(page.getByText("2330").first()).toBeVisible();
    },
  );
});
