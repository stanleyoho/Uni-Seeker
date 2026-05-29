import { test, expect } from "./setup";

/**
 * Auth flow E2E (docker-only).
 *
 * Exercises the full real-stack auth contract:
 *   1. Register a brand-new user via the /login page's "register" tab.
 *      Email is timestamp-suffixed so re-runs don't collide on the
 *      seeded DB.
 *   2. Confirm the post-register redirect lands on /, the protected
 *      home shows the username / authenticated-only nav items.
 *   3. Log out by clearing the token (the app exposes logout via the
 *      header / settings, but we go through localStorage for a
 *      deterministic, UI-agnostic teardown).
 *   4. Re-visit a protected route and assert the unauthed UI shows
 *      (redirect to /login).
 *
 * Skips outside docker mode because the registration POST hits a real
 * backend.
 */

const isDocker = process.env.E2E_TARGET === "docker";

test.describe("Auth flow (docker e2e)", () => {
  test.skip(!isDocker, "requires E2E_TARGET=docker (real backend)");

  test("register → land on app → logout → see login again", async ({ page }) => {
    const stamp = Date.now();
    const email = `auth-e2e+${stamp}@example.com`;
    const password = "AuthE2E-Pw-1234";
    const username = `authe2e${stamp}`;

    // 1. Go to login page, switch to register tab.
    await page.goto("/login");
    await page.getByRole("button", { name: /register|註冊/i }).first().click();

    // 2. Fill the form. Email, username (register-only), password are
    //    all required inputs. The form uses real input[type] selectors.
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input[type="text"]').first().fill(username);
    await page.locator('input[type="password"]').fill(password);

    // 3. Submit. The form's submit button toggles label between login
    //    and register copy — accept either since translation strings
    //    may shift.
    await page.getByRole("button", { name: /register|sign up|註冊|登入/i }).last().click();

    // 4. After successful register the page navigates to "/" with a
    //    valid token in localStorage. The protected home should now
    //    show the standard authenticated nav.
    await page.waitForURL(/\/$|\/portfolio|\/holdings/, { timeout: 15_000 });
    await expect(page.locator("header")).toBeVisible();

    // 5. Sanity: localStorage carries the token now.
    const token = await page.evaluate(() => localStorage.getItem("auth_token"));
    expect(token, "auth_token should be set after register").toBeTruthy();

    // 6. Logout by clearing storage + reloading. Some pages expose a
    //    logout button in a menu; storage-clear is more robust against
    //    UI churn while still hitting the AuthProvider unmount path.
    await page.evaluate(() => {
      localStorage.removeItem("auth_token");
    });
    await page.goto("/portfolio");

    // 7. /portfolio is gated. The frontend has two equivalent "unauthed"
    //    surfaces:
    //      a) AuthProvider redirects to /login (URL change).
    //      b) The page renders its public-shell with a "請先登入" panel
    //         + a "GO TO LOGIN" CTA (URL stays at /portfolio, but the
    //         unauthed copy is on screen).
    //    Both are valid auth-gated states. Race the two so whichever
    //    fires first satisfies the assertion.
    await Promise.race([
      page.waitForURL(/\/login/, { timeout: 10_000 }),
      page
        .getByRole("link", { name: /GO TO LOGIN|登入|sign in/i })
        .first()
        .waitFor({ state: "visible", timeout: 10_000 }),
    ]);
  });
});
