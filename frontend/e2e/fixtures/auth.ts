import type { Page } from "@playwright/test";

/**
 * Shared E2E auth/mocking helpers.
 *
 * These helpers cover the cross-cutting concerns every authenticated page
 * test needs:
 *   - Pre-seed the canonical `auth_token` localStorage key so the AuthProvider
 *     short-circuits the unauthed-redirect logic before the first React
 *     commit. Must be called via `addInitScript` BEFORE `page.goto` so the
 *     value is present at hydration.
 *   - Mock `GET /api/v1/auth/me` (called by AuthProvider) so the user
 *     resolves with a deterministic tier without ever touching the real
 *     backend.
 *
 * Usage:
 *   await mockAuth(page);            // default Pro tier
 *   await mockAuth(page, { tier: "free" });
 *
 * Important: call this BEFORE `page.goto(...)`. `addInitScript` only fires
 * on subsequent navigations, and `page.route` must be registered before the
 * intercepted request fires.
 */
export interface MockAuthOptions {
  /** User tier as the backend returns it. Defaults to `"pro"`. */
  tier?: string;
  /** Numeric user id. Defaults to `1`. */
  userId?: number;
  /** Email field on the mocked /auth/me response. */
  email?: string;
}

export async function mockAuth(
  page: Page,
  opts: MockAuthOptions = {},
): Promise<void> {
  const { tier = "pro", userId = 1, email = "test@example.com" } = opts;

  // Seed localStorage BEFORE any app script runs. AuthProvider reads the
  // token synchronously inside its mount effect; without this, the first
  // render path treats the user as unauthed.
  await page.addInitScript(() => {
    try {
      localStorage.setItem("auth_token", "fake-jwt-token");
    } catch {
      /* private-mode browsers; tests just skip this branch. */
    }
  });

  // AuthProvider calls fetchMe → GET /auth/me. Path under default API_BASE
  // is http://localhost:8000/api/v1/auth/me; the glob handles whatever
  // host the dev server resolves to.
  await page.route("**/api/v1/auth/me", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: userId,
        email,
        tier,
        created_at: "2025-01-01T00:00:00Z",
      }),
    });
  });
}

/**
 * Convenience: fulfill a route with JSON. Cuts down on the boilerplate
 * of building `{ status, contentType, body: JSON.stringify(...) }` in
 * every test.
 */
export async function fulfillJson(
  route: import("@playwright/test").Route,
  json: unknown,
  status = 200,
): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(json),
  });
}
