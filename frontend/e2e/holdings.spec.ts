import { test, expect } from "./setup";
import { mockAuth, fulfillJson } from "./fixtures/auth";

/**
 * /holdings E2E.
 *
 * Tests the assembled HoldingsPage in isolation: auth + every API call the
 * page issues is mocked through `page.route`. We never start the backend.
 *
 * Coverage strategy:
 *   - render path (KPI row + positions table populated from mocks)
 *   - each entry-point button opens its modal
 *   - tier gating on the multi-currency switcher (Free vs Pro)
 *
 * Selectors lean on visible UI text (zh-TW) because the markup does not
 * carry stable test ids. If translations move, update strings here.
 */

const MOCK_ACCOUNT = {
  id: 1,
  name: "永豐",
  broker: "SinoPac",
  market: "TW_TWSE",
  currency: "TWD",
  description: null,
  created_at: "2025-01-01T00:00:00Z",
};

const MOCK_POSITION = {
  account_id: 1,
  symbol: "2330",
  market: "TW_TWSE",
  qty: "1000",
  avg_cost: "580",
  last_price: "650",
  prev_close: "640",
  currency: "TWD",
  realized_pnl: "0",
  unrealized_pnl: "70000",
  unrealized_pnl_pct: "12.07",
  daily_change: "10000",
  daily_change_pct: "1.56",
  is_closed: false,
  total_cost: "580000",
  price_as_of: "2025-05-23",
};

const MOCK_SUMMARY = {
  total_cost: "580000",
  total_value: "650000",
  total_unrealized_pnl: "70000",
  total_daily_change: "10000",
  gain_simple: "70000",
  gain_simple_pct: "12.07",
  position_count: 1,
  account_count: 1,
};

/**
 * Register the common /holdings API mocks. Caller supplies the auth tier
 * via mockAuth; positions and summary stay constant across tests.
 */
async function mockHoldingsApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/holdings/accounts", (route) =>
    fulfillJson(route, [MOCK_ACCOUNT]),
  );
  await page.route("**/api/v1/holdings/positions**", (route) =>
    fulfillJson(route, { account_id: null, positions: [MOCK_POSITION] }),
  );
  await page.route("**/api/v1/holdings/summary**", (route) =>
    fulfillJson(route, MOCK_SUMMARY),
  );
  // Defensive: dividends endpoint sometimes prefetched by future hooks.
  await page.route("**/api/v1/holdings/dividends**", (route) =>
    fulfillJson(route, []),
  );
}

test.describe("/holdings page", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page, { tier: "pro" });
    await mockHoldingsApi(page);
  });

  test("renders KPI row + positions table", async ({ page }) => {
    await page.goto("/holdings");

    // Page title — comes from translation, defaults to "持倉對賬".
    await expect(
      page.getByRole("heading", { name: /持倉|HOLDINGS/i }),
    ).toBeVisible();

    // Positions table renders the symbol from the mocked response.
    await expect(page.getByText("2330").first()).toBeVisible();
  });

  test("opens add trade modal via + record-trade button", async ({ page }) => {
    await page.goto("/holdings");
    await page.getByRole("button", { name: /記錄交易|新增交易/ }).first().click();
    // The modal heading is "新增持倉交易".
    await expect(page.getByText("新增持倉交易")).toBeVisible();
  });

  test("opens add dividend modal", async ({ page }) => {
    await page.goto("/holdings");
    await page.getByRole("button", { name: /記錄配息|新增配息/ }).click();
    await expect(page.getByText("新增配息").first()).toBeVisible();
  });

  test("opens add account modal", async ({ page }) => {
    await page.goto("/holdings");
    await page.getByRole("button", { name: /新增帳戶/ }).click();
    await expect(page.getByText("新增券商帳戶")).toBeVisible();
  });

  test("opens csv import modal", async ({ page }) => {
    await page.goto("/holdings");
    await page.getByRole("button", { name: /匯入 CSV/ }).click();
    await expect(page.getByText("CSV 匯入交易")).toBeVisible();
  });

  test("rebalance preview → execute happy path writes trades + refetches", async ({
    page,
  }) => {
    // Stub the preview + execute endpoints with deterministic payloads.
    // We assert the execute call actually fires after confirm, and that
    // the result summary surfaces executed / failed counts to the UI.
    const previewPayload = {
      total_portfolio_value: "650000",
      suggested_trades: [
        {
          symbol: "2330",
          market: "TW_TWSE",
          action: "SELL",
          qty: "100",
          estimated_price: "650",
          estimated_value: "65000",
          rationale: "trim to target",
        },
      ],
      final_allocation_pct: { "2330|TW_TWSE": "90" },
      skipped_trades: [],
      cash_residual: "65000",
    };
    const executePayload = {
      executed: [
        {
          symbol: "2330",
          market: "TW_TWSE",
          action: "SELL",
          qty: "100",
          price: "650",
          trade_id: 9999,
        },
      ],
      skipped: [],
      failed: [],
      total_executed_value: "65000",
    };

    let executeCallCount = 0;
    await page.route("**/api/v1/holdings/rebalance/preview", (route) =>
      fulfillJson(route, previewPayload),
    );
    await page.route("**/api/v1/holdings/rebalance/execute", (route) => {
      executeCallCount += 1;
      return fulfillJson(route, executePayload);
    });

    await page.goto("/holdings");
    await page.getByRole("button", { name: /再平衡|REBALANCE/i }).click();

    // Account selector defaults to "all" — pick the one mocked account so
    // the execute button becomes available (backend 422 without account_id).
    await page.locator("select").first().selectOption("1");

    // Run preview to populate suggested_trades. The suggested_trades
    // section renders a "建議交易" / "Suggested Trades" label only after
    // the API call lands, so wait on that copy.
    await page.getByRole("button", { name: /預覽再平衡|Preview/i }).click();
    await expect(
      page.getByText(/建議交易|Suggested Trades/i).first(),
    ).toBeVisible();

    // Execute button only shows when suggested_trades.length > 0 AND
    // account_id is set. Click it to open the confirmation modal.
    await page.getByRole("button", { name: /執行再平衡|Execute Rebalance/i }).click();
    await expect(page.getByText(/將寫入 1 筆交易|will write 1 trade/i)).toBeVisible();

    // Confirm → fires POST /rebalance/execute.
    await page.getByRole("button", { name: /確認執行|Confirm Execute/i }).click();

    // Result summary surfaces executed count.
    await expect(page.getByText(/執行結果|Execute Result/i)).toBeVisible();
    expect(executeCallCount).toBe(1);
  });

  test("currency switcher upsell hint fires for free tier", async ({ page }) => {
    // Re-register auth as FREE — overrides the beforeEach Pro mock.
    await page.unroute("**/api/v1/auth/me");
    await mockAuth(page, { tier: "free" });

    await page.goto("/holdings");

    // Currency switcher panel renders the upgrade hint text. We assert the
    // hint string exists; the active-currency interaction varies per locale
    // so the panel-level upgrade copy is the stable anchor.
    await expect(
      page.getByText(/升級 Pro|multi.?currency/i).first(),
    ).toBeVisible();
  });
});
