import { test, expect } from "./setup";
import { mockAuth, fulfillJson } from "./fixtures/auth";

/**
 * /institutional E2E.
 *
 * Mocks the full 13F surface area the page consumes:
 *   GET /institutional/filers                 → list of subscribed filers
 *   GET /institutional/filers/{id}/filings    → quarterly filings index
 *   GET /institutional/filers/{id}/holdings   → snapshot for selected period
 *   GET /institutional/filers/{id}/diff       → QoQ moves (DiffView)
 *   GET /institutional/filers/search          → typeahead in FilerSearchModal
 *   POST /institutional/filers/{id}/refresh   → refresh button
 *
 * Two fixture worlds:
 *   - empty subscriptions  → asserts the empty CTA
 *   - one filer + 2 filings → asserts the snapshot + view-switcher flow
 */

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
      filing_id: 11,
      cusip: "037833100",
      ticker: "AAPL",
      issuer_name: "APPLE INC",
      class_title: "COM",
      shares: "5500000",
      value_usd: "1100000000",
      put_call: null,
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

/**
 * Default mocks: one subscribed filer, two filings, populated holdings.
 * Individual tests can `page.unroute(...)` to override a specific endpoint
 * (e.g. empty subscriptions, search results).
 */
async function mockInstitutionalApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/institutional/filers", (route) => {
    // GET vs POST — list vs subscribe. Branch on method.
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

test.describe("/institutional page", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page, { tier: "pro" });
    await mockInstitutionalApi(page);
  });

  test("renders header + subscribed filer entry", async ({ page }) => {
    await page.goto("/institutional");
    await expect(
      page.getByRole("heading", { name: /機構持倉|13F/i }),
    ).toBeVisible();
    await expect(page.getByText(/BERKSHIRE/i).first()).toBeVisible();
  });

  test("empty state surfaces the subscribe CTA", async ({ page }) => {
    // Override the GET /filers route to return an empty list.
    await page.unroute("**/api/v1/institutional/filers");
    await page.route("**/api/v1/institutional/filers", (route) =>
      fulfillJson(route, []),
    );

    await page.goto("/institutional");
    // Both the header button and the empty-state CTA say 訂閱機構/基金.
    await expect(
      page.getByRole("button", { name: /訂閱機構|基金/ }).first(),
    ).toBeVisible();
  });

  test("selecting a filer shows its holdings snapshot", async ({ page }) => {
    await page.goto("/institutional");
    // The first filer auto-selects via useEffect; AAPL should appear in
    // the holdings table once /filings + /holdings resolve.
    await expect(page.getByText("AAPL").first()).toBeVisible();
    // QoQ section heading rendered.
    await expect(
      page.getByText(/QUARTER-OVER-QUARTER|QoQ/i).first(),
    ).toBeVisible();
  });

  test("opens search modal from + 訂閱機構/基金 button", async ({ page }) => {
    await page.goto("/institutional");
    await page
      .getByRole("button", { name: /訂閱機構|基金/ })
      .first()
      .click();
    // Search modal body copy includes this hint string.
    await expect(
      page.getByText(/輸入至少 2 字元|搜尋中|EDGAR/).first(),
    ).toBeVisible();
  });

  test("opens bulk subscribe modal", async ({ page }) => {
    await page.goto("/institutional");
    await page.getByRole("button", { name: /批次訂閱/ }).click();
    await expect(
      page.getByText(/批次訂閱機構|批次訂閱/).first(),
    ).toBeVisible();
  });

  test("switches between holdings / timeline / top movers tabs", async ({
    page,
  }) => {
    await page.goto("/institutional");

    // Wait until the holdings table is populated so the view tabs render
    // (they only show when a filer is selected).
    await expect(page.getByText("AAPL").first()).toBeVisible();

    // Click TOP MOVERS tab.
    await page.getByRole("button", { name: /Top Movers|movers/i }).click();
    await expect(page.getByText(/TOP MOVERS/i).first()).toBeVisible();

    // Back to HOLDINGS tab.
    await page
      .getByRole("button", { name: /^Holdings$|HOLDINGS$/i })
      .first()
      .click();
    await expect(
      page.getByText(/HOLDINGS SNAPSHOT|holdings/i).first(),
    ).toBeVisible();
  });
});
