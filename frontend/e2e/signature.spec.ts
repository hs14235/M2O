import { expect, test, type Page } from "@playwright/test";
import { enterDemo, settle } from "./support";

// The transcript-to-outcome moment: one view transition when motion is allowed, none
// in calm mode or with reduced motion, and the same end state every time. One demo
// session covers all three passes: demo starts are rate limited per address.
type Counted = { transitions: number; named: number };

async function countTransitions(page: Page) {
  await page.addInitScript(() => {
    const counted = window as unknown as Counted;
    counted.transitions = 0;
    counted.named = 0;
    const original = document.startViewTransition?.bind(document);
    if (!original) return;
    document.startViewTransition = ((options: ViewTransitionUpdateCallback | StartViewTransitionOptions) => {
      counted.transitions += 1;
      const update = typeof options === "function" ? options : options?.update;
      // When the update runs the old state has been captured; count the lines that took part.
      const wrapped = () => {
        counted.named = [...document.querySelectorAll<HTMLElement>("[data-line]")].filter((row) =>
          getComputedStyle(row).viewTransitionName.startsWith("m2o-o-"),
        ).length;
        return update?.();
      };
      return original(typeof options === "function" ? wrapped : { ...options, update: wrapped });
    }) as typeof document.startViewTransition;
  });
}

async function extract(page: Page, again: boolean) {
  await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
  await page
    .getByRole("button", { name: again ? "Extract outcomes again" : "Extract outcomes", exact: true })
    .click();
  await expect(page.getByText(/Job completed/)).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole("heading", { name: /draft outcomes? found/ })).toBeVisible();
  await settle(page);
}

// Every draft card ends fully visible, sharp and in place, whichever way it arrived.
async function expectEndState(page: Page) {
  const cards = page.locator("li:has(> a[href*='outcome='])");
  expect(await cards.count()).toBeGreaterThan(0);
  const styles = await cards.evaluateAll((items) =>
    items.map((item) => {
      const style = getComputedStyle(item);
      return { opacity: style.opacity, filter: style.filter, transform: style.transform };
    }),
  );
  for (const style of styles) expect(style).toEqual({ opacity: "1", filter: "none", transform: "none" });
  await expect(page.getByText("Transcript lines", { exact: true })).toBeVisible();
}

async function transitions(page: Page) {
  return page.evaluate(() => (window as unknown as Counted).transitions);
}

// Replays only for a revision that has not played it yet, so each pass forgets it first.
async function forgetMoment(page: Page, calm: boolean) {
  await page.evaluate((on) => {
    localStorage.removeItem("m2o-moment");
    if (on) localStorage.setItem("m2o-calm", "true");
    else localStorage.removeItem("m2o-calm");
  }, calm);
  await page.reload();
}

test("the transcript lines become draft cards once, and calm or reduced motion skip it", async ({ page }) => {
  await countTransitions(page);
  await enterDemo(page);
  await page.getByRole("button", { name: "Open Release readiness", exact: true }).click();
  await expect(page).toHaveURL(/\/people$/);
  await expect(page.getByRole("region", { name: "Transcript lines" })).toBeVisible();

  // Motion allowed: exactly one view transition, with at least one line morphing.
  await extract(page, false);
  expect(await transitions(page)).toBe(1);
  expect(await page.evaluate(() => (window as unknown as Counted).named)).toBeGreaterThan(0);
  await expectEndState(page);

  // Calm mode: no transition, the same end state.
  await forgetMoment(page, true);
  await expect(page.locator("html")).toHaveAttribute("data-motion", "calm");
  await extract(page, true);
  expect(await transitions(page)).toBe(0);
  await expectEndState(page);

  // The system reduced-motion setting: no transition either.
  await page.emulateMedia({ reducedMotion: "reduce" });
  await forgetMoment(page, false);
  await extract(page, true);
  expect(await transitions(page)).toBe(0);
  await expectEndState(page);
});
