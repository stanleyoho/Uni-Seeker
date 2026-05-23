import { test, expect } from "./setup";

/**
 * Backtest page minimal smoke.
 *
 * The page lives at /portfolio/backtest now (Round 6 had it at
 * /backtest with `策略建構` / `ma_crossover` strings — those were
 * superseded by the STRATOS rewrite). This spec only asserts the
 * route resolves; full strategy-flow coverage belongs in a future
 * mock-driven spec once the UI stabilises.
 */

test.describe("Backtest Page", () => {
  test("loads /portfolio/backtest without runtime error", async ({ page }) => {
    const response = await page.goto("/portfolio/backtest");
    expect(response?.status()).toBeLessThan(400);
    // Header still renders -> base layout did not crash.
    await expect(page.locator("header")).toBeVisible();
  });

  test("history sub-route resolves", async ({ page }) => {
    const response = await page.goto("/portfolio/backtest/history");
    expect(response?.status()).toBeLessThan(400);
    await expect(page.locator("header")).toBeVisible();
  });
});
