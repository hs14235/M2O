import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";
import { enterDemo, extractFixture, settle } from "./support";

// Screenshot comparison for the main visitor screens. Baselines are Linux renders
// (see docs/LOCAL_DEVELOPMENT.md); update them only through `npm run test:visual:update`.
const desktop = { viewport: { width: 1280, height: 720 } };
// A phone-class context, so touch and coarse-pointer styles apply, not just a narrow window.
const mobile = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true };
const variants = [
  { colorScheme: "light", size: "desktop", device: desktop },
  { colorScheme: "light", size: "mobile", device: mobile },
  { colorScheme: "dark", size: "desktop", device: desktop },
  { colorScheme: "dark", size: "mobile", device: mobile },
] as const;
// Server-issued times (demo expiry, saved and job timestamps) change every run, and so
// does their format: the demo expiry gains a date once it falls on another day. A fixed
// box (the style below) did not hold that width, so baselines taken before midnight UTC
// failed after it. Replacing the text with one constant keeps the width identical; the
// mask still hides it.
async function pinTimes(view: Page) {
  await view.locator("time").evaluateAll((times) => {
    for (const time of times) time.textContent = "Oct 1, 12:00 PM";
  });
}
// The style option injects a <style> tag, which the app's CSP (style-src 'self') blocks,
// so screenshot contexts bypass CSP; the other browser specs check the real policy.
const fixedTimes =
  "time { display: inline-block !important; width: 9em !important; overflow: hidden !important; white-space: nowrap !important; vertical-align: bottom !important; }";

// One demo session captures every variant: demo starts are rate limited per address.
// Each variant opens the current page in a fresh context that shares the session
// cookies, so the layout is what a visitor on that device first sees.
async function snapAll(browser: Browser, page: Page, screen: string, ready: (view: Page) => Locator) {
  const storageState = await page.context().storageState();
  for (const { colorScheme, size, device } of variants) {
    const context = await browser.newContext({ ...device, colorScheme, storageState, bypassCSP: true });
    try {
      const view = await context.newPage();
      await view.goto(page.url());
      await expect(ready(view)).toBeVisible({ timeout: 30000 });
      await settle(view);
      await pinTimes(view);
      await expect(view).toHaveScreenshot(`${screen}-${colorScheme}-${size}.png`, {
        fullPage: true,
        mask: [view.locator("time")],
        style: fixedTimes,
      });
    } finally {
      await context.close();
    }
  }
}

test("visitor screens match their baselines in both themes and sizes", async ({ browser, page }) => {
  await page.setViewportSize(desktop.viewport);
  await page.goto("/");
  const explore = (view: Page) => view.getByRole("button", { name: "Explore the isolated demo" });
  await expect(explore(page)).toBeVisible();
  await snapAll(browser, page, "landing", explore);

  // Engineering is the demo's first workspace.
  await enterDemo(page);
  await expect(page.locator("html")).toHaveAttribute("data-department", "engineering");
  await snapAll(browser, page, "demo-home", (view) =>
    view.getByRole("heading", { name: "Make the next step clear." }),
  );

  const workspace = new URL(page.url()).pathname.split("/")[2];
  await extractFixture(page, "Release readiness");
  // Opened fresh, the People step shows its returning-visitor view (no live job banner).
  await snapAll(browser, page, "people", (view) => view.getByLabel("Directory match for Alex"));

  await page.getByRole("button", { name: /Continue (to review|with unassigned people)/ }).click();
  const review = (view: Page) => view.getByRole("heading", { name: "Review what matters." });
  await expect(review(page)).toBeVisible();
  await snapAll(browser, page, "review", review);

  await page.goto(`/workspaces/${workspace}/settings/motion`);
  const system = (view: Page) => view.getByRole("radio", { name: "System" });
  await expect(system(page)).toBeVisible();
  await snapAll(browser, page, "settings-motion", system);
});

// The style guide needs no demo session, so each variant simply opens the page.
test("the style guide matches its baselines in both themes and sizes", async ({ browser, baseURL }) => {
  for (const { colorScheme, size, device } of variants) {
    const context = await browser.newContext({ ...device, colorScheme });
    try {
      const view = await context.newPage();
      await view.goto(new URL("/styleguide.html", baseURL).href);
      await expect(view.getByRole("heading", { level: 1, name: "Style guide" })).toBeVisible();
      await settle(view);
      await expect(view).toHaveScreenshot(`styleguide-${colorScheme}-${size}.png`, { fullPage: true });
    } finally {
      await context.close();
    }
  }
});
