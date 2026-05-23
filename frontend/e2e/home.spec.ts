import { test, expect } from "./setup";

/**
 * Home page minimal smoke.
 *
 * Round 6 prototype had a <nav> with `More` dropdown linking to
 * /backtest + /scanner; current STRATOS header dropped both and
 * uses a <header> with /research, /portfolio, /holdings, etc.
 * These checks only assert the page loads + brand text renders +
 * primary nav links exist, leaving full navigation flows to the
 * dedicated page specs.
 */

test.describe("Homepage", () => {
  test("renders header with brand and core nav links", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("header")).toBeVisible();
    await expect(page.getByText("Uni-Seeker").first()).toBeVisible();
    await expect(page.locator('a[href="/portfolio"]').first()).toBeVisible();
    await expect(page.locator('a[href="/holdings"]').first()).toBeVisible();
    await expect(page.locator('a[href="/institutional"]').first()).toBeVisible();
  });

  test("navigates to /portfolio", async ({ page }) => {
    await page.goto("/");
    await page.locator('a[href="/portfolio"]').first().click();
    await expect(page).toHaveURL(/\/portfolio$/);
  });

  test("navigates to /holdings", async ({ page }) => {
    await page.goto("/");
    await page.locator('a[href="/holdings"]').first().click();
    await expect(page).toHaveURL(/\/holdings$/);
  });
});
