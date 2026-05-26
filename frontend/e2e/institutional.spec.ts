import { test as baseTest, expect } from "./setup";
import { test as authTest, mockAuth, fulfillJson } from "./fixtures/auth";

/**
 * /institutional E2E.
 *
 * Mock-mode (legacy): network-layer mocks for the full 13F surface area.
 * Docker-mode (E2E-3): real backend with the seeded Berkshire subscription.
 *
 * The seed inserts:
 *   - F13Filer  : BERKSHIRE HATHAWAY INC (CIK 0001067983)
 *   - F13Filing : 1 row, form_type=13F-HR
 *   - F13Holding: APPLE INC (5,500,000 shares, $1.1B value)
 *   - F13UserSubscription: e2e user → Berkshire
 *
 * The docker-mode test asserts the filer card shows up, drilling into
 * it reveals the seeded AAPL holding with NON-ZERO share count.
 */

const isDocker = process.env.E2E_TARGET === "docker";

const MOCK_FILER = {
  id: 42,
  cik: "0001067983",
  name: "BERKSHIRE HATHAWAY INC",
  ticker: null,
  latest_filing_date: "2025-03-31",
  is_subscribed: true,
};

const MOCK_FILINGS = [
  { id: 11, filer_id: 42, report_period_end: "2025-03-31", form_type: "13F-HR" },
  { id: 10, filer_id: 42, report_period_end: "2024-12-31", form_type: "13F-HR" },
];

const MOCK_HOLDINGS_RES = {
  filing: {
    id: 11,
    filer_id: 42,
    report_period_end: "2025-03-31",
    form_type: "13F-HR",
  },
  holdings: [
    {
      id: 901,
      cusip: "037833100",
      name_of_issuer: "APPLE INC",
      value_usd: "1100000000",
      shares: "5500000",
      put_call: null,
      investment_discretion: "SOLE",
      stock_id: 1,
      stock_symbol: "AAPL",
    },
  ],
};

const MOCK_DIFF = {
  from: { id: 10, report_period_end: "2024-12-31" },
  to: { id: 11, report_period_end: "2025-03-31" },
  changes: [
    {
      cusip: "037833100",
      ticker: "AAPL",
      issuer_name: "APPLE INC",
      from_shares: "5000000",
      to_shares: "5500000",
      delta_shares: "500000",
      delta_pct: "10.0",
      from_value_usd: "1000000000",
      to_value_usd: "1100000000",
      kind: "increased",
    },
  ],
};

async function mockInstitutionalApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/institutional/filers", (route) => {
    if (route.request().method() === "GET") {
      return fulfillJson(route, [MOCK_FILER]);
    }
    return fulfillJson(route, MOCK_FILER, 201);
  });

  await page.route("**/api/v1/institutional/filers/search**", (route) =>
    fulfillJson(route, {
      results: [
        {
          cik: "0001067983",
          name: "BERKSHIRE HATHAWAY INC",
          source: "edgar",
          is_subscribed: false,
        },
      ],
    }),
  );

  await page.route(
    "**/api/v1/institutional/filers/*/filings**",
    (route) => fulfillJson(route, MOCK_FILINGS),
  );

  await page.route(
    "**/api/v1/institutional/filers/*/holdings**",
    (route) => fulfillJson(route, MOCK_HOLDINGS_RES),
  );

  await page.route(
    "**/api/v1/institutional/filers/*/diff**",
    (route) => fulfillJson(route, MOCK_DIFF),
  );

  await page.route(
    "**/api/v1/institutional/filers/*/refresh**",
    (route) =>
      fulfillJson(route, {
        filer_id: 42,
        new_filings: 0,
        new_holdings: 0,
        status: "ok",
      }),
  );
}

// ── Mock-mode suite (legacy) ────────────────────────────────────────────────

baseTest.describe("/institutional page (mock mode)", () => {
  baseTest.skip(isDocker, "covered by docker suite");

  baseTest.beforeEach(async ({ page }) => {
    await mockAuth(page, { tier: "pro" });
    await mockInstitutionalApi(page);
  });

  baseTest("renders header + subscribed filer entry", async ({ page }) => {
    await page.goto("/institutional");
    await expect(
      page.getByRole("heading", { name: /機構持倉|13F/i }),
    ).toBeVisible();
    await expect(page.getByText(/BERKSHIRE/i).first()).toBeVisible();
  });

  baseTest("empty state surfaces the subscribe CTA", async ({ page }) => {
    await page.unroute("**/api/v1/institutional/filers");
    await page.route("**/api/v1/institutional/filers", (route) =>
      fulfillJson(route, []),
    );

    await page.goto("/institutional");
    await expect(
      page.getByRole("button", { name: /訂閱機構|基金/ }).first(),
    ).toBeVisible();
  });

  baseTest("selecting a filer shows its holdings snapshot", async ({ page }) => {
    await page.goto("/institutional");
    await expect(page.getByText("AAPL").first()).toBeVisible();
    await expect(
      page.getByText(/QUARTER-OVER-QUARTER|QoQ/i).first(),
    ).toBeVisible();
  });

  baseTest("opens search modal from + 訂閱機構/基金 button", async ({ page }) => {
    await page.goto("/institutional");
    await page
      .getByRole("button", { name: /訂閱機構|基金/ })
      .first()
      .click();
    await expect(
      page.getByText(/輸入至少 2 字元|搜尋中|EDGAR/).first(),
    ).toBeVisible();
  });

  baseTest("opens bulk subscribe modal", async ({ page }) => {
    await page.goto("/institutional");
    await page.getByRole("button", { name: /批次訂閱/ }).click();
    await expect(
      page.getByText(/批次訂閱機構|批次訂閱/).first(),
    ).toBeVisible();
  });

  baseTest("switches between holdings / timeline / top movers tabs", async ({
    page,
  }) => {
    await page.goto("/institutional");
    await expect(page.getByText("AAPL").first()).toBeVisible();
    await page.getByRole("button", { name: /Top Movers|movers/i }).click();
    await expect(page.getByText(/TOP MOVERS/i).first()).toBeVisible();
    await page
      .getByRole("button", { name: /^Holdings$|HOLDINGS$|^持倉快照$/i })
      .first()
      .click();
    await expect(
      page.getByText(/HOLDINGS SNAPSHOT|holdings/i).first(),
    ).toBeVisible();
  });
});

// ── Docker-backed suite (E2E-3) ─────────────────────────────────────────────

authTest.describe("/institutional page (docker e2e)", () => {
  authTest.skip(!isDocker, "docker-only suite");

  authTest(
    "shows the seeded Berkshire subscription with AAPL holding > 0 shares",
    async ({ loggedInPage: page }) => {
      await page.goto("/institutional");

      // Filer list renders the seeded Berkshire subscription.
      await expect(page.getByText(/BERKSHIRE/i).first()).toBeVisible({
        timeout: 15_000,
      });

      // First filer auto-selects on mount → /holdings call resolves →
      // the AAPL row should appear. The seed inserts 5,500,000 shares
      // so the shares column should NOT read 0.
      await expect(page.getByText("APPLE INC").first()).toBeVisible({
        timeout: 15_000,
      });

      // Assert SOMEWHERE on the page the seeded share count surfaces.
      // Locale formatting varies (5,500,000 vs 5500000 vs 5.5M); match
      // any of those. This protects against a regression where the
      // holdings endpoint silently returns zeros.
      const body = page.locator("body");
      await expect(body).toContainText(/5[,.]?500[,.]?000|5\.5M|5,500,000/i);
    },
  );
});
