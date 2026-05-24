import { test as base } from "@playwright/test";

export const test = base.extend({
  page: async ({ page }, use) => {
    await page.addInitScript(() => {
      try {
        window.localStorage.setItem("uni-seeker-onboarded", "true");
        window.localStorage.setItem("uni-seeker-holdings-tour-shown", "true");
      } catch {
        /* swallow — strict cookie modes */
      }
    });
    await use(page);
  },
});

export { expect } from "@playwright/test";
