import { test as baseTest, expect } from "./setup";
import { test as authTest, mockAuth, fulfillJson } from "./fixtures/auth";

/**
 * /holdings E2E.
 *
 * Dual-mode by design:
 *   - Local dev (`E2E_TARGET` unset): use `mockAuth` + `page.route` to
 *     exercise the assembled HoldingsPage in isolation. Backend never
 *     starts. This preserves the original spec coverage for developers
 *     iterating on the frontend.
 *   - E2E-3 docker (`E2E_TARGET=docker`): use the `loggedInPage`
 *     fixture so the page hits the real Postgres-backed backend with
 *     the e2e seed user. Assertions also check that KPI numbers
 *     reflect the seeded BUY 1000 @ 580 trade on 2330.
 *
 * Tests that don't make sense in docker mode (e.g. the rebalance
 * preview-with-fake-payload flow) stay mock-only and gate themselves
 * via `test.skip(isDocker, ...)`.
 */

const isDocker = process.env.E2E_TARGET === "docker";

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
  await page.route("**/api/v1/holdings/dividends**", (route) =>
    fulfillJson(route, []),
  );
}

// ── Mock-mode suite (legacy) ────────────────────────────────────────────────

baseTest.describe("/holdings page (mock mode)", () => {
  baseTest.skip(isDocker, "mock-mode suite — covered by docker suite below");

  baseTest.beforeEach(async ({ page }) => {
    await mockAuth(page, { tier: "pro" });
    await mockHoldingsApi(page);
  });

  baseTest("renders KPI row + positions table", async ({ page }) => {
    await page.goto("/holdings");
    await expect(
      page.getByRole("heading", { name: /持倉|HOLDINGS/i }),
    ).toBeVisible();
    await expect(page.getByText("2330").first()).toBeVisible();
  });

  baseTest("opens add trade modal via + record-trade button", async ({ page }) => {
    await page.goto("/holdings");
    await page.getByRole("button", { name: /記錄交易|新增交易/ }).first().click();
    await expect(page.getByText("新增持倉交易")).toBeVisible();
  });

  baseTest("opens add dividend modal", async ({ page }) => {
    await page.goto("/holdings");
    await page.getByRole("button", { name: /記錄配息|新增配息/ }).click();
    await expect(page.getByText("新增配息").first()).toBeVisible();
  });

  baseTest("opens add account modal", async ({ page }) => {
    await page.goto("/holdings");
    await page.getByRole("button", { name: /新增帳戶/ }).click();
    await expect(page.getByText("新增券商帳戶")).toBeVisible();
  });

  baseTest("opens csv import modal", async ({ page }) => {
    await page.goto("/holdings");
    await page.getByRole("button", { name: /匯入 CSV/ }).click();
    await expect(page.getByText("CSV 匯入交易")).toBeVisible();
  });

  baseTest("rebalance preview → execute happy path writes trades + refetches", async ({
    page,
  }) => {
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
    await page.locator("select").first().selectOption("1");
    await page.getByRole("button", { name: /預覽再平衡|Preview/i }).click();
    await expect(
      page.getByText(/建議交易|Suggested Trades/i).first(),
    ).toBeVisible();
    await page.getByRole("button", { name: /執行再平衡|Execute Rebalance/i }).click();
    await expect(page.getByText(/將寫入 1 筆交易|will write 1 trade/i)).toBeVisible();
    await page.getByRole("button", { name: /確認執行|Confirm Execute/i }).click();
    await expect(page.getByText(/執行結果|Execute Result/i)).toBeVisible();
    expect(executeCallCount).toBe(1);
  });

  baseTest("currency switcher upsell hint fires for free tier", async ({ page }) => {
    await page.unroute("**/api/v1/auth/me");
    await mockAuth(page, { tier: "free" });
    await page.goto("/holdings");
    await expect(
      page.getByText(/升級 Pro|multi.?currency/i).first(),
    ).toBeVisible();
  });
});

// ── Docker-backed suite (E2E-3) ─────────────────────────────────────────────

authTest.describe("/holdings page (docker e2e)", () => {
  authTest.skip(!isDocker, "docker-only suite — runs when E2E_TARGET=docker");

  authTest(
    "renders real KPI numbers reflecting seeded BUY 1000 @ 580 on 2330",
    async ({ loggedInPage: page }) => {
      await page.goto("/holdings");

      // Page chrome present.
      await expect(
        page.getByRole("heading", { name: /持倉|HOLDINGS/i }),
      ).toBeVisible({ timeout: 15_000 });

      // The seed inserts one trade: BUY 1000 shares of 2330 @ 580 TWD.
      // The positions table should render the symbol AND the cost basis
      // 580 (or its formatted variant). We assert the symbol is present
      // first (cheap), then look for the cost number anywhere in the
      // surrounding row container.
      await expect(page.getByText("2330").first()).toBeVisible({
        timeout: 15_000,
      });

      // KPI summary endpoint computes total_cost from the trade. Seed →
      // total_cost = 580 * 1000 = 580,000. We accept any formatting that
      // contains "580" because locale separators differ (580,000 vs
      // 580000 vs 580K).
      const body = page.locator("body");
      await expect(body).toContainText(/580[,.]?000|580K|580,?000\s*TWD/i);
    },
  );

  authTest(
    "opens the record-trade modal (smoke for authenticated UI)",
    async ({ loggedInPage: page }) => {
      await page.goto("/holdings");
      await page
        .getByRole("button", { name: /記錄交易|新增交易/ })
        .first()
        .click();
      await expect(page.getByText("新增持倉交易")).toBeVisible();
    },
  );
});
