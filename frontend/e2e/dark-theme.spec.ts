import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Dark is a first-class theme, so it gets the same accessibility bar as light.
test.use({ colorScheme: "dark" });

async function accessible(page: Page) {
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((animation) => animation.effect?.getTiming().iterations !== Infinity)
        .map((animation) => animation.finished.catch(() => undefined)),
    ),
  );
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations,
  ).toEqual([]);
}

test("the dark theme meets WCAG AA across the visitor journey", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", "light");
  await accessible(page);
  await page.getByRole("button", { name: "Explore the isolated demo" }).click();
  await expect(page.getByRole("region", { name: "Synthetic demo session" })).toBeVisible();
  await accessible(page);
  await page.getByRole("button", { name: "Open Release readiness", exact: true }).click();
  await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Extract outcomes", exact: true }).click();
  await expect(page.getByText(/Job completed/)).toBeVisible({ timeout: 30000 });
  await accessible(page);
  await page.getByRole("button", { name: /Continue (to review|with unassigned people)/ }).click();
  await expect(page.getByRole("heading", { name: "Review what matters." })).toBeVisible();
  await accessible(page);
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByRole("link", { name: "Motion & layout", exact: true }).click();
  await page.getByRole("radio", { name: "Light" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("radio", { name: "System" }).click();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme");
  await accessible(page);
});
