import { test, expect } from "./setup";

test.describe("Homepage", () => {
  test("should load and show title", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("nav")).toBeVisible();
    await expect(page.getByText("Uni-Seeker")).toBeVisible();
  });

  test("should navigate to backtest page", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/backtest"]');
    await expect(page).toHaveURL("/backtest");
    await expect(page.getByText("策略回測")).toBeVisible();
  });

  test("should navigate to scanner page", async ({ page }) => {
    await page.goto("/");
    // Scanner is in More dropdown
    await page.click("text=More");
    await page.click('a[href="/scanner"]');
    await expect(page).toHaveURL("/scanner");
  });
});
