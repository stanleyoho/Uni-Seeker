import { test, expect } from "./setup";
import { mockAuth, fulfillJson } from "./fixtures/auth";

/**
 * Phase 8 R.3 — virtualization correctness probe.
 *
 * Mocks the institutional API to return 200 holdings, then asserts that
 * the mobile card list only mounts a small window of cards (not all 200).
 * This is the "synthesise 200-row payload" evidence the R.3 spec asks
 * for. The desktop table is unchanged so we resize the viewport to
 * mobile (iPhone 13) to land on the virtualized card list path.
 */

const ROW_COUNT = 200;

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
];

function makeHoldings(n: number) {
  const out = [] as Array<Record<string, unknown>>;
  for (let i = 0; i < n; i++) {
    out.push({
      id: 1000 + i,
      cusip: String(i).padStart(9, "0"),
      name_of_issuer: `SYNTHETIC ISSUER ${i}`,
      value_usd: String(1_000_000_000 - i * 1_000_000),
      shares: String(1_000_000 - i * 100),
      put_call: null,
      investment_discretion: "SOLE",
      stock_id: null,
      stock_symbol: `SY${i}`,
    });
  }
  return out;
}

const MOCK_HOLDINGS_RES = {
  filing: {
    id: 11,
    filer_id: 42,
    report_period_end: "2025-03-31",
    form_type: "13F-HR",
  },
  holdings: makeHoldings(ROW_COUNT),
};

async function mockApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/institutional/filers", (route) => {
    if (route.request().method() === "GET") {
      return fulfillJson(route, [MOCK_FILER]);
    }
    return fulfillJson(route, MOCK_FILER, 201);
  });
  await page.route("**/api/v1/institutional/filers/*/filings**", (route) =>
    fulfillJson(route, MOCK_FILINGS),
  );
  await page.route("**/api/v1/institutional/filers/*/holdings**", (route) =>
    fulfillJson(route, MOCK_HOLDINGS_RES),
  );
  await page.route("**/api/v1/institutional/filers/*/diff**", (route) =>
    fulfillJson(route, { from: null, to: null, changes: [] }),
  );
  await page.route("**/api/v1/institutional/filers/search**", (route) =>
    fulfillJson(route, { results: [] }),
  );
  await page.route("**/api/v1/institutional/filers/*/refresh**", (route) =>
    fulfillJson(route, { filer_id: 42, new_filings: 0, new_holdings: 0, status: "ok" }),
  );
}

test.describe("/institutional virtualization", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page, { tier: "pro" });
    await mockApi(page);
  });

  test("card list mounts a small window for 200 holdings", async ({ page }) => {
    // iPhone 13 viewport (390 × 844) → md:hidden block is visible.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/institutional");

    // Wait until the holdings API has returned + a holdings row exists
    // anywhere in the DOM (both desktop + mobile trees mount React-side;
    // CSS picks which one paints). Picking the desktop tree's first <td>
    // is the cheapest "data has arrived" probe.
    await page.locator("td", { hasText: /^SY\d+$/ }).first().waitFor({
      state: "attached",
      timeout: 10_000,
    });

    // Now the mobile card list should also have rendered its virtual
    // items. Scope to the scroller so we don't accidentally match the
    // desktop table.
    const scroller = page.getByTestId(
      "institutional-holdings-card-list-scroll",
    );
    await scroller.waitFor({ state: "attached", timeout: 5_000 });

    // Wait for the virtualizer to mount at least one card. The
    // ResizeObserver fires async, so we may briefly see zero items.
    await expect
      .poll(
        async () => scroller.locator('[role="listitem"]').count(),
        { timeout: 5_000 },
      )
      .toBeGreaterThan(0);

    // Count mounted card rows inside the scroller. Virtualizer should
    // mount roughly (visible window / 132px) + 2 × overscan(5) cards.
    // We assert a hard upper bound well below the full 200.
    const mountedRows = await scroller.locator('[role="listitem"]').count();

    expect(mountedRows).toBeGreaterThan(0);
    expect(mountedRows).toBeLessThan(40); // would be 200 without virtualization
  });
});
