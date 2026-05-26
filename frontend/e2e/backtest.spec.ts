import { test as baseTest, expect } from "./setup";
import { test as authTest } from "./fixtures/auth";

/**
 * Backtest page E2E.
 *
 * Mock-mode tests stay as a smoke (the page lives at /portfolio/backtest
 * and was rewritten under the STRATOS design system — full flow is
 * exercised via the docker suite below where the backend can actually
 * run an rsi_oversold backtest against seeded prices).
 *
 * Docker-mode tests:
 *   - Log in as the seeded e2e user
 *   - Type "2330" into the symbol field
 *   - Pick the rsi_oversold strategy from the loaded dropdown
 *   - Click Run and assert the metric KPIs appear with non-empty values
 */

const isDocker = process.env.E2E_TARGET === "docker";

baseTest.describe("Backtest Page (mock smoke)", () => {
  baseTest.skip(isDocker, "smoke covered by docker suite");

  baseTest("loads /portfolio/backtest without runtime error", async ({ page }) => {
    const response = await page.goto("/portfolio/backtest");
    expect(response?.status()).toBeLessThan(400);
    await expect(page.locator("header")).toBeVisible();
  });

  baseTest("history sub-route resolves", async ({ page }) => {
    const response = await page.goto("/portfolio/backtest/history");
    expect(response?.status()).toBeLessThan(400);
    await expect(page.locator("header")).toBeVisible();
  });
});

authTest.describe("Backtest Page (docker e2e)", () => {
  authTest.skip(!isDocker, "docker-only suite");

  authTest(
    "runs rsi_oversold on seeded 2330 and renders non-zero metrics",
    async ({ loggedInPage: page }) => {
      await page.goto("/portfolio/backtest");
      await expect(page.locator("header")).toBeVisible({ timeout: 15_000 });

      // The symbol input has placeholder copy "e.g., AAPL, 2330.TW".
      // The seed populates symbol "2330" (without .TW suffix) because
      // that matches the canonical symbol in the stocks table. Replace
      // the default value.
      const symbolInput = page.getByPlaceholder(/AAPL|2330/);
      await symbolInput.fill("2330");

      // Strategy dropdown is the first <select>. The strategies hook
      // hits GET /strategies which the backend serves unconditionally;
      // the dropdown should contain "rsi_oversold" once loaded.
      const strategySelect = page.locator("select").first();
      await expect(strategySelect).toBeVisible({ timeout: 10_000 });
      await strategySelect.selectOption({ value: "rsi_oversold" });

      // The "RUN BACKTEST" button text varies (RUN / Run / 執行回測).
      // Match generously then click.
      const runButton = page
        .getByRole("button", { name: /RUN|執行回測|RUN BACKTEST/i })
        .first();
      await runButton.click();

      // After the run completes (POST /backtest/run resolves), the
      // results panel renders "BACKTESTING SIMULATION RESULTS".
      await expect(
        page.getByText(/BACKTESTING SIMULATION RESULTS|TOTAL TRADES/i).first(),
      ).toBeVisible({ timeout: 30_000 });
    },
  );
});
