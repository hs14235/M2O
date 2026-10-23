import { expect, type Page } from "@playwright/test";

// Let finite animations settle; mid-fade colours are not what users see at rest. Poll
// instead of awaiting each animation's finished promise: an animation cancelled
// because React removed or hid its element goes idle and that promise never settles.
// Two frames first, so a just-triggered animation exists before we check.
export async function settle(page: Page) {
  await page.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
  );
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .every(
        (animation) =>
          animation.playState !== "running" || animation.effect?.getTiming().iterations === Infinity,
      ),
  );
}

export async function enterDemo(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore the isolated demo" }).click();
  // Each demo workspace opens with its meetings already listed.
  await expect(page.getByRole("heading", { name: "Your meetings", exact: true })).toBeVisible();
}

/** Opens a listed meeting and continues from its transcript to People. */
export async function openMeeting(page: Page, title: string) {
  // A meeting row's name starts with its title, then its date and identifier.
  const name = new RegExp("^" + title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b");
  await page.getByRole("button", { name }).click();
  await page.getByRole("button", { name: "Continue to people", exact: true }).click();
  await expect(page).toHaveURL(/\/people$/);
}

export async function extractFixture(page: Page, title: string) {
  await openMeeting(page, title);
  await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Extract outcomes", exact: true }).click();
  await expect(page.getByText(/Job completed/)).toBeVisible({ timeout: 30000 });
  // The transcript lines become draft cards after the meeting reloads.
  await expect(page.getByRole("heading", { name: /draft outcomes? found/ })).toBeVisible();
}
