import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { settle } from "./support";

// The style guide is a separate page (styleguide.html) served under the same
// content security policy as the app, so it must work without inline scripts.

function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

async function accessible(page: Page) {
  await settle(page);
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations,
  ).toEqual([]);
}

test("the style guide is served with the security headers and loads cleanly", async ({ page }) => {
  const errors = watchErrors(page);
  const response = await page.goto("/styleguide.html");
  expect(response?.status()).toBe(200);
  expect(response?.headers()["content-security-policy"]).toContain("script-src 'self'");
  await expect(page.getByRole("heading", { level: 1, name: "Style guide" })).toBeVisible();
  await expect(page.getByRole("table", { name: /Contrast of the checked pairs/ })).not.toContainText("Fail");
  await settle(page);
  expect(errors).toEqual([]);
});

for (const colorScheme of ["light", "dark"] as const) {
  test.describe(`${colorScheme} system theme`, () => {
    test.use({ colorScheme });
    test("the style guide meets WCAG AA", async ({ page }) => {
      await page.goto("/styleguide.html");
      await expect(page.getByRole("heading", { level: 1, name: "Style guide" })).toBeVisible();
      await accessible(page);
    });
  });
}

test("the style guide meets WCAG AA after choosing Dark", async ({ page }) => {
  await page.goto("/styleguide.html");
  await page.getByRole("radio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await accessible(page);
});

test("calm mode leaves no animation running on the style guide", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("m2o-calm", "true"));
  await page.goto("/styleguide.html");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "calm");
  await expect(page.getByText("Motion is off. The demos show their end state.")).toBeVisible();
  await page.getByRole("button", { name: "Replay demos" }).click();
  // Two frames, so the remounted demos exist; calm mode allows no animation at all.
  await page.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
  );
  const running = await page.evaluate(
    () => document.getAnimations().filter((animation) => animation.playState === "running").length,
  );
  expect(running).toBe(0);
});
