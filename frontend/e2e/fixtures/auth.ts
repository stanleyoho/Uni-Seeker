import { test as base, type Page } from "@playwright/test";

/**
 * Shared E2E auth/mocking helpers.
 *
 * Two-mode auth surface:
 *
 *   1. `mockAuth(page)` — pure client-side mock. Seeds the auth_token
 *      localStorage key and intercepts GET /api/v1/auth/me at the
 *      network layer so AuthProvider resolves with a deterministic
 *      tier WITHOUT ever talking to a backend. This is the path the
 *      legacy specs (and the institutional-virtualization mechanics
 *      spec) use — they exercise frontend wiring in isolation.
 *
 *   2. `loggedInPage` fixture — REAL login against the dockerized
 *      backend seeded by `backend/scripts/seed_e2e_data.py`. POSTs
 *      `/api/v1/auth/login` with the canonical test user, stashes
 *      the returned JWT in localStorage, then navigates to the
 *      target page. Tests that assert backend behavior (real KPIs,
 *      real watchlist, real 13F holdings) MUST use this fixture so
 *      the assertion path exercises the full stack.
 *
 * Both helpers are co-located in this file because they share the
 * same localStorage key (`auth_token`) and the same /auth/me contract;
 * splitting them would invite drift.
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

/**
 * Seed credentials for the dockerized E2E backend. Kept in lockstep
 * with `backend/scripts/seed_e2e_data.py` — any change here MUST be
 * mirrored there.
 */
export const E2E_SEED_USER = {
  email: "e2e@example.com",
  password: "e2e-test-pw",
} as const;

/**
 * Backend base URL the browser will hit when `E2E_TARGET=docker`.
 * Mirrors `NEXT_PUBLIC_API_URL` in docker-compose.e2e.yml. Note that
 * playwright tests run in NodeJS so we can hit the backend host port
 * directly to log in, BUT the resulting token still has to land in
 * localStorage scoped to the frontend origin (http://localhost:3002),
 * which is why the login flow does a `page.addInitScript` write rather
 * than a fetch from inside the page.
 */
const E2E_BACKEND_URL =
  process.env.E2E_BACKEND_URL || "http://localhost:8001/api/v1";

/**
 * POST /auth/login against the dockerized backend and return the JWT.
 * Throws on any non-200 — letting the test fail fast with a clear
 * error rather than silently proceeding with an empty token.
 */
async function loginAgainstE2EBackend(): Promise<string> {
  const res = await fetch(`${E2E_BACKEND_URL}/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(E2E_SEED_USER),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `E2E login failed: status=${res.status} body=${body.slice(0, 200)}`,
    );
  }
  const data = (await res.json()) as { access_token?: string };
  if (!data.access_token) {
    throw new Error(`E2E login returned no access_token: ${JSON.stringify(data)}`);
  }
  return data.access_token;
}

/**
 * Extended Playwright test with a `loggedInPage` fixture.
 *
 * The fixture:
 *   1. Performs a real POST /auth/login against the seeded backend.
 *   2. Injects the resulting JWT into localStorage via `addInitScript`
 *      so the first React render picks it up.
 *   3. Pre-seeds the onboarded flag so tour/intro modals stay out of
 *      the way.
 *   4. Returns a Page that callers can `goto(...)` from.
 *
 * Specs that need a real authenticated stack import `test` from this
 * file and destructure `{ loggedInPage }` from the fixture object.
 * Specs that prefer the legacy mock path can keep importing `test`
 * from `./setup` instead.
 *
 * Skip behavior: when `E2E_TARGET` is NOT "docker", the fixture
 * skips the test rather than failing — the seeded backend simply
 * isn't there in local-dev mode, and pretending otherwise would
 * mask the skip in CI logs.
 */
export const test = base.extend<{ loggedInPage: Page }>({
  loggedInPage: async ({ page }, use) => {
    if (process.env.E2E_TARGET !== "docker") {
      test.skip(true, "loggedInPage requires E2E_TARGET=docker (seeded backend)");
      // Unreachable, but TypeScript wants `use` called once.
      // eslint-disable-next-line react-hooks/rules-of-hooks -- `use` is the Playwright fixture callback, not React's use() hook.
      await use(page);
      return;
    }
    const token = await loginAgainstE2EBackend();
    await page.addInitScript((injected: string) => {
      try {
        localStorage.setItem("auth_token", injected);
        localStorage.setItem("uni-seeker-onboarded", "true");
        localStorage.setItem("uni-seeker-holdings-tour-shown", "true");
      } catch {
        /* swallow — strict cookie modes */
      }
    }, token);
    // eslint-disable-next-line react-hooks/rules-of-hooks -- `use` is the Playwright fixture callback, not React's use() hook.
    await use(page);
  },
});

export { expect } from "@playwright/test";
