import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { enterDemo, settle } from "./support";

// Phase 5: the full visitor journey from the keyboard alone, with the command menu
// (⌘K on Apple platforms, Ctrl+K elsewhere; ControlOrMeta matches both).
// One demo session for the whole file: demo starts are rate limited per address.

async function tabTo(page: Page, target: Locator, limit = 80) {
  // Disabled controls are skipped by Tab; wait like click() would (e.g. a queued job).
  await expect(target).toBeEnabled({ timeout: 30000 });
  for (let presses = 0; presses < limit; presses++) {
    if (await target.evaluate((element) => element === document.activeElement).catch(() => false)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error("Tab never reached the target");
}
// Every console error and uncaught exception, so a blocked inline style (CSP) or a
// React warning fails the journey instead of passing silently.
function watchConsole(page: Page, problems: string[]) {
  page.on("console", (message) => {
    // Script and CSP errors only: the signed-out landing page's session check is a 401.
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource"))
      problems.push("console: " + message.text());
  });
  page.on("pageerror", (error) => problems.push("pageerror: " + error.message));
}
async function openMenu(page: Page) {
  const menu = page.getByRole("dialog", { name: "Command menu" });
  // The shortcut listener attaches just after the first paint, so on a freshly
  // loaded page retry; only press while the menu is closed (the shortcut toggles).
  await expect(async () => {
    if (!(await menu.isVisible())) await page.keyboard.press("ControlOrMeta+K");
    await expect(menu).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 10000 });
  await expect(menu.getByRole("combobox")).toBeFocused();
  return menu;
}
async function accessible(page: Page) {
  await settle(page);
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations,
  ).toEqual([]);
}
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

test("a visitor completes the journey from the keyboard with the command menu", async ({ browser, page }) => {
  const problems: string[] = [];
  watchConsole(page, problems);
  await enterDemo(page);
  await expect(page.getByRole("heading", { name: "Meetings", exact: true, level: 1 })).toBeVisible();

  // Jump to Meetings from the menu; the page, not the menu's opener, gets focus.
  const menu = await openMenu(page);
  await page.keyboard.type("Meetings");
  await page.keyboard.press("Enter");
  await expect(menu).toBeHidden();
  await expect(page).toHaveURL(/\/meetings$/);
  await expect(page.locator("#main")).toBeFocused();

  // Open a synthetic meeting, extract and continue to review, by Tab and Enter only.
  await tabTo(page, page.getByRole("button", { name: "Open Release readiness", exact: true }));
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/people$/);
  await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
  await tabTo(page, page.getByRole("button", { name: "Extract outcomes", exact: true }));
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Job completed/)).toBeVisible({ timeout: 30000 });
  await tabTo(page, page.getByRole("button", { name: /Continue (to review|with unassigned people)/ }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Review", exact: true, level: 1 })).toBeVisible();

  // Search meetings by title and land on the meeting.
  await openMenu(page);
  await page.keyboard.type("Release");
  const result = page.getByRole("option", { name: /Release readiness/ });
  await expect(result.first()).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/meetings\/[^/]+\/transcript$/);

  // `?` lists the shortcuts; Escape closes the list.
  await page.locator("#main").focus();
  await page.keyboard.press("?");
  const help = page.getByRole("dialog", { name: "Keyboard shortcuts" });
  await expect(help).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(help).toBeHidden();

  // The open menu meets WCAG AA in light and in dark (a context sharing this session).
  await openMenu(page);
  await accessible(page);
  const dark = await browser.newContext({
    colorScheme: "dark",
    storageState: await page.context().storageState(),
  });
  try {
    const view = await dark.newPage();
    watchConsole(view, problems);
    await view.goto(page.url());
    await expect(view.getByRole("button", { name: /Search or jump/ })).toBeVisible({ timeout: 30000 });
    await openMenu(view);
    await accessible(view);
  } finally {
    await dark.close();
  }

  // Calm mode from the menu, back on the first page.
  await page.bringToFront();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Command menu" })).toBeHidden();
  await openMenu(page);
  await page.keyboard.type("calm mode on");
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "calm");
  await openMenu(page);
  expect(await runningFiniteAnimations(page)).toBe(0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Command menu" })).toBeHidden();
  expect(await runningFiniteAnimations(page)).toBe(0);
  expect(problems).toEqual([]);
});
