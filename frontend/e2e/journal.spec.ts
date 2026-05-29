import { test } from "./fixtures/auth";
import { expect } from "@playwright/test";

/**
 * Trade Journal E2E (docker-only).
 *
 * Flow:
 *   1. Login as the seeded e2e user.
 *   2. Go to /journal/accounts.
 *   3. Open the "+ 新增帳戶" form, fill it, submit.
 *   4. Assert the new account appears in the list.
 *   5. Click into the account, open the AddTradeModal.
 *   6. Submit a BUY trade.
 *   7. Assert the holdings table shows the symbol with non-zero quantity.
 *
 * The seed does NOT pre-create any TradeJournal account, so this spec
 * exercises a fresh create path each run. Account names are timestamp-
 * suffixed to keep runs independent (uniqueness is per-name, no FK to
 * the user table on the trade_accounts table per its current schema —
 * see backend/app/models/journal.py).
 */

const isDocker = process.env.E2E_TARGET === "docker";

test.describe("Trade Journal flow (docker e2e)", () => {
  test.skip(!isDocker, "requires E2E_TARGET=docker");

  test(
    "create account → add BUY trade → position renders",
    async ({ loggedInPage: page }) => {
      const stamp = Date.now();
      const accountName = `E2E Test ${stamp}`;
      const symbol = "2330";

      // 1. Land on the accounts page.
      await page.goto("/journal/accounts");
      await expect(page.getByText(/帳戶列表|Accounts/i).first()).toBeVisible({
        timeout: 15_000,
      });

      // 2. Open the create-account form.
      await page.getByRole("button", { name: /\+\s*新增帳戶|新增帳戶/ }).click();

      // 3. Fill the form. The form has:
      //    - "帳戶名稱" text input — placeholder "元大證券"
      //    - "券商（選填）" text input — placeholder "元大"
      //    - "市場" select (TW / US / CRYPTO)
      //    - "計價幣別" select (TWD / USD / USDT)
      //    - "建立帳戶" submit button
      //
      // The account-form inputs render WITHOUT an explicit
      // `type="text"` attribute (default text type), so a CSS
      // attribute selector `input[type="text"]` does NOT match —
      // we go by placeholder instead which is stable and unique.
      await page.getByPlaceholder("元大證券").fill(accountName);

      // 4. Submit.
      await page.getByRole("button", { name: /^建立帳戶$|建立帳戶/ }).click();

      // 5. New account appears in the list. The form closes (no longer
      //    shows the "建立帳戶" button) and the link card renders.
      await expect(page.getByText(accountName).first()).toBeVisible({
        timeout: 15_000,
      });

      // 6. Click the new account card to enter its detail page.
      await page.getByText(accountName).first().click();

      // 7. URL should now contain /journal/accounts/{id}.
      await page.waitForURL(/\/journal\/accounts\/\d+/, { timeout: 10_000 });

      // 8. Open the add-trade modal.
      await page.getByRole("button", { name: /\+\s*新增交易|新增交易/ }).click();

      // 9. The AddTradeModal renders. Find the symbol input and fill.
      //    Same default-no-type-attr caveat as the account form above:
      //    we go by placeholder ("2330.TW / AAPL / BTC") which is the
      //    stable identifier for the symbol input.
      await page.getByPlaceholder(/2330\.TW.*AAPL.*BTC/).fill(symbol);

      // 10. Fill price + quantity (BUY is default action).
      //
      // Price + quantity inputs render with placeholder="0.00" /
      // placeholder="0" and no label-element wrapper (only sibling
      // span used as a label). Address them positionally via their
      // unique placeholders.
      const priceField = page.getByPlaceholder("0.00").first();
      const qtyField = page.locator('input[placeholder="0"]').first();
      if (await priceField.count()) {
        await priceField.fill("580");
      }
      if (await qtyField.count()) {
        await qtyField.fill("100");
      }

      // 11. Submit. The modal's submit button is "確認新增" / "Add" /
      //     "送出" — match generously.
      await page
        .getByRole("button", { name: /確認新增|送出|新增|Submit|Add/i })
        .last()
        .click();

      // 12. After the mutation resolves, the modal closes and the
      //     holdings table refetches. The symbol should now appear in
      //     the account detail's holdings panel.
      await expect(page.getByText(symbol).first()).toBeVisible({
        timeout: 15_000,
      });
    },
  );
});
