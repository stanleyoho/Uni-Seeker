import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vitest baseline for Next 15 / React 19. Component-level tests that need
// AuthContext / ThemeContext / TanStack Query providers are intentionally
// out of scope here — see the PR description for the follow-up plan.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Mirror tsconfig.json: "@/*" -> "./src/*"
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    // jsdom defaults to `about:blank`, which is an opaque origin and rejects
    // localStorage access with "opaque origins" — our api-client and watchlist
    // migration both depend on real localStorage, so anchor to a real URL.
    environmentOptions: {
      jsdom: { url: "http://localhost/" },
    },
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: [
      "node_modules/**",
      ".next/**",
      "e2e/**",
      "playwright.config.ts",
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "json-summary"],
      exclude: [
        "node_modules/**",
        ".next/**",
        "e2e/**",
        "playwright.config.ts",
        "vitest.config.ts",
        "vitest.setup.ts",
        "next.config.ts",
        "postcss.config.mjs",
        "eslint.config.mjs",
        "src/lib/api/generated/**",
      ],
    },
  },
});
