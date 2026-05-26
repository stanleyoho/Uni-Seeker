import { defineConfig, devices } from "@playwright/test";

/**
 * Two execution modes:
 *
 * 1. Default (local dev): `npx playwright test`
 *    Spawns `next dev -p 3001` and runs specs against http://localhost:3001.
 *    Specs that mock API at the network layer (`page.route(...)`) work
 *    out of the box. Specs that need real backend data fall back to the
 *    network mocks they ship with.
 *
 * 2. E2E-3 docker stack: `E2E_TARGET=docker npx playwright test`
 *    Targets the dockerized frontend on http://localhost:3002 (see
 *    `docker-compose.e2e.yml`). webServer is omitted because compose
 *    already owns the lifecycle and `next dev` would race with the
 *    container on 3001. baseURL flips to 3002.
 *
 * The mode switch is intentionally an env var (not a separate config
 * file) so the same spec set runs unchanged in both places — the only
 * difference is whether the auth/data fixtures hit a real backend or
 * a `page.route` mock. Tests that need real backend gate themselves on
 * `process.env.E2E_TARGET === "docker"` and skip otherwise.
 */
const isDocker = process.env.E2E_TARGET === "docker";
const baseURL = isDocker ? "http://localhost:3002" : "http://localhost:3001";

export default defineConfig({
  testDir: "./e2e",
  // Docker boot + first-request hydration can push tests past 30s; bump
  // when targeting docker only.
  timeout: isDocker ? 60_000 : 30_000,
  retries: 1,
  use: {
    baseURL,
    trace: "on-first-retry",
    // Capture screenshots only on failure so CI artifacts stay small.
    screenshot: "only-on-failure",
    // Record video on failed-retry attempts so CI artifact upload
    // surfaces them to the PR.
    video: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  // Only spawn next dev when targeting local. Under docker the
  // frontend container already serves on :3002 and starting `next dev`
  // here would collide with whatever else is running on 3001.
  webServer: isDocker
    ? undefined
    : {
        command: "npx next dev -p 3001",
        port: 3001,
        reuseExistingServer: true,
      },
});
