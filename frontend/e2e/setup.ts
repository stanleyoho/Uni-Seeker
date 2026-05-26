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
    // eslint-disable-next-line react-hooks/rules-of-hooks -- `use` is the Playwright fixture callback (test.extend API), not React's use() hook.
    await use(page);
  },
});

export { expect } from "@playwright/test";
