import { expect, test, type Locator, type Page } from "@playwright/test";
import { enterDemo, extractFixture, settle } from "./support";

// Screenshot comparison for the main visitor screens. Baselines are Linux renders
// (see docs/LOCAL_DEVELOPMENT.md); update them only through `npm run test:visual:update`.
const variants = [
  { colorScheme: "light", size: "desktop", viewport: { width: 1280, height: 720 } },
  { colorScheme: "light", size: "mobile", viewport: { width: 390, height: 844 } },
  { colorScheme: "dark", size: "desktop", viewport: { width: 1280, height: 720 } },
  { colorScheme: "dark", size: "mobile", viewport: { width: 390, height: 844 } },
] as const;
// Dates rendered by the browser come from this fixed instant, not today.
const frozen = new Date("2026-10-15T14:00:00Z");

// One demo session captures every variant: demo starts are rate limited per address,
// and the browser suite already starts several. Each variant reloads, so the layout is
// what a visitor at that size first sees and job status comes fresh from the server.
async function snapAll(page: Page, screen: string, ready: Locator) {
  for (const { colorScheme, size, viewport } of variants) {
    await page.emulateMedia({ colorScheme });
    await page.setViewportSize(viewport);
    await page.reload();
    await expect(ready).toBeVisible({ timeout: 30000 });
    // Server-issued times (demo expiry, job timestamps) change every run, and their text
    // width would move the layout around them, so fix the text and mask the box.
    await page.locator("time").evaluateAll((times) => {
      for (const time of times) time.textContent = "Oct 15, 2:00 PM";
    });
    await settle(page);
    await expect(page).toHaveScreenshot(`${screen}-${colorScheme}-${size}.png`, {
      fullPage: true,
      mask: [page.locator("time")],
    });
  }
  await page.setViewportSize(variants[0].viewport);
  await page.emulateMedia({ colorScheme: variants[0].colorScheme });
}

test("visitor screens match their baselines in both themes and sizes", async ({ page }) => {
  await page.clock.setFixedTime(frozen);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Explore the isolated demo" })).toBeVisible();
  await snapAll(page, "landing", page.getByRole("button", { name: "Explore the isolated demo" }));

  // Engineering is the demo's first workspace.
  await enterDemo(page);
  await expect(page.locator("html")).toHaveAttribute("data-department", "engineering");
  await snapAll(page, "demo-home", page.getByRole("heading", { name: "Make the next step clear." }));

  const workspace = new URL(page.url()).pathname.split("/")[2];
  await extractFixture(page, "Release readiness");
  // After a reload the People step shows its returning-visitor view (no live job banner).
  await snapAll(page, "people", page.getByLabel("Directory match for Alex"));

  await page.getByRole("button", { name: /Continue (to review|with unassigned people)/ }).click();
  await expect(page.getByRole("heading", { name: "Review what matters." })).toBeVisible();
  await snapAll(page, "review", page.getByRole("heading", { name: "Review what matters." }));

  await page.goto(`/workspaces/${workspace}/settings/motion`);
  await expect(page.getByRole("radio", { name: "System" })).toBeVisible();
  await snapAll(page, "settings-motion", page.getByRole("radio", { name: "System" }));
});
