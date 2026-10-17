import { expect, test, type Page } from "@playwright/test";

// Calm mode and the system reduced-motion setting must stop motion from the very
// first paint, not only after React has started.
async function runningFiniteAnimations(page: Page) {
  return page.evaluate(
    () =>
      document
        .getAnimations()
        .filter(
          (animation) =>
            animation.playState === "running" && animation.effect?.getTiming().iterations !== Infinity,
        ).length,
  );
}
async function motionBeforeApp(page: Page) {
  // Read data-motion as soon as the document is parsed, before the app bundle runs.
  await page.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      (window as unknown as { motionAtLoad?: string }).motionAtLoad = document.documentElement.dataset.motion;
    });
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Explore the isolated demo" })).toBeVisible();
  return page.evaluate(() => (window as unknown as { motionAtLoad?: string }).motionAtLoad);
}

test("a saved calm preference applies before the first paint", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("m2o-calm", "true"));
  expect(await motionBeforeApp(page)).toBe("calm");
  expect(await runningFiniteAnimations(page)).toBe(0);
});

test("the system reduced-motion setting applies before the first paint", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await motionBeforeApp(page)).toBe("calm");
  expect(await runningFiniteAnimations(page)).toBe(0);
});

test("revealed content ends fully visible and sharp in every motion mode", async ({ page }) => {
  for (const calm of [false, true]) {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Explore the isolated demo" })).toBeVisible();
    // Outside the React root, so a re-render cannot remove it.
    await page.evaluate((on) => {
      if (on) document.documentElement.dataset.motion = "calm";
      else delete document.documentElement.dataset.motion;
      const group = document.createElement("div");
      group.className = "reveal-seq";
      group.innerHTML = "<p>One</p><p>Two</p><p>Three</p>";
      document.body.append(group);
    }, calm);
    const last = page.locator(".reveal-seq > p").last();
    await expect(last).toHaveCSS("opacity", "1");
    await expect(last).toHaveCSS("filter", "none");
    await expect(last).toHaveCSS("transform", "none");
  }
});
