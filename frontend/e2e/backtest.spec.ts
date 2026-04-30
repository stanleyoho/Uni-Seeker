import { test, expect } from "./setup";

test.describe("Backtest Page", () => {
  test("should show strategy builder tab by default", async ({ page }) => {
    await page.goto("/backtest");
    await expect(page.getByText("策略建構")).toBeVisible();
    await expect(page.getByText("ma_crossover")).toBeVisible();
  });

  test("should switch tabs", async ({ page }) => {
    await page.goto("/backtest");
    await page.click("text=歷史紀錄");
    await expect(page.getByText("回測標的")).toBeVisible();
  });
});
