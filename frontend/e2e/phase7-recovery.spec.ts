import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function enter(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore the isolated demo" }).click();
  await expect(page.getByRole("region", { name: "Synthetic demo session" })).toBeVisible();
}
async function openFixture(page: Page) {
  await page.getByRole("button", { name: "Open Release readiness", exact: true }).click();
  await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
}
async function reviewAction(page: Page) {
  await openFixture(page);
  await page.getByRole("button", { name: "Extract outcomes", exact: true }).click();
  await expect(page.getByText(/Job completed/)).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: /Continue (to review|with unassigned people)/ }).click();
  const action = page.locator("article.action");
  await action.getByRole("button", { name: "Approve outcome" }).click();
  await expect(action.locator(".badge")).toContainText("approved");
  return action.getByRole("heading").innerText();
}
async function accessible(page: Page) {
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
}

test("a failed status read recovers the real extraction without another write", async ({ page }) => {
  await enter(page); await openFixture(page);
  let writes = 0, interrupted = false;
  page.on("request", request => { if (request.method() === "POST" && new URL(request.url()).pathname.endsWith("/extract")) writes += 1; });
  await page.route("**/api/workspaces/*/jobs/*", async route => {
    if (!interrupted) { interrupted = true; await route.fulfill({ status: 503, json: { error: "Synthetic status-read interruption", request_id: "synthetic-status" } }); }
    else await route.continue();
  });
  await page.getByRole("button", { name: "Extract outcomes", exact: true }).click();
  await expect(page.getByText(/Its current status is unknown/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await accessible(page);
  await page.screenshot({ path: "test-results/phase7-job-read-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Read job status again" }).click();
  await expect(page.getByText(/Job completed/)).toBeVisible({ timeout: 30000 });
  expect(writes).toBe(1);
});

test("a real local handoff response cannot navigate after Back and Forward", async ({ page }) => {
  await enter(page); const title = await reviewAction(page);
  await page.getByRole("button", { name: "Continue to handoff" }).click();
  await page.getByRole("checkbox", { name: title, exact: true }).check();
  const chooseUrl = page.url();
  await page.getByRole("button", { name: "Continue to preparation" }).click();
  let release!: () => void, intercepted!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  const started = new Promise<void>(resolve => { intercepted = resolve; });
  await page.route("**/api/workspaces/*/meetings/*/export", async route => {
    const response = await route.fetch();
    intercepted(); await waiting;
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Prepare handoff" }).click(); await started;
  await page.goBack(); await expect(page).toHaveURL(chooseUrl);
  await expect(page.getByRole("heading", { name: "Choose the next home." })).toBeVisible();
  await page.goForward(); await expect(page).toHaveURL(/handoff=configure/);
  release();
  await expect(page.getByRole("button", { name: "Prepare handoff" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Download handoff" })).toHaveCount(0);
  await page.unroute("**/api/workspaces/*/meetings/*/export");
  await page.getByRole("button", { name: "Prepare handoff" }).click();
  await expect(page).toHaveURL(/handoff=preview/);
  await expect(page.getByRole("button", { name: "Download handoff" })).toBeVisible();
});

test("an accepted private save recovers by GET after a synthetic read failure", async ({ page }) => {
  test.skip(!process.env.MTT_E2E_EMAIL || !process.env.MTT_E2E_PASSWORD || !process.env.MTT_LIFECYCLE_FIXTURE, "Requires the disposable synthetic lifecycle fixture");
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill(process.env.MTT_E2E_EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(process.env.MTT_E2E_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "New meeting", exact: true }).click();
  await page.getByLabel("Meeting title").fill("Phase 7 synthetic read recovery");
  await page.getByLabel("Transcript text").fill("Alex: Action: prepare a synthetic checklist.");
  let id = "", writes = 0, interrupted = false;
  page.on("request", request => { if (request.method() === "POST" && new URL(request.url()).pathname.endsWith("/index")) { id = request.postDataJSON().meeting_id; writes += 1; } });
  await page.route("**/api/workspaces/*/meetings/*", async route => {
    if (id && !interrupted && route.request().method() === "GET" && new URL(route.request().url()).pathname.endsWith("/meetings/" + id)) {
      interrupted = true; await route.fulfill({ status: 503, json: { error: "Synthetic post-save read interruption", request_id: "synthetic-save" } });
    } else await route.continue();
  });
  await page.getByRole("button", { name: "Save transcript and continue" }).click();
  await expect(page.getByText(/Your transcript save was accepted/)).toBeVisible();
  await expect(page.getByLabel("Transcript text")).toBeDisabled();
  await accessible(page);
  await page.screenshot({ path: "test-results/phase7-accepted-save-desktop.png", fullPage: true });
  await page.getByRole("button", { name: "Load saved transcript" }).click();
  await expect(page).toHaveURL(/\/people$/);
  await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
  expect(writes).toBe(1);
});

test("an accepted personal change recovers without repeating its PATCH", async ({ page }) => {
  await enter(page); const title = await reviewAction(page);
  await page.getByRole("link", { name: "My day", exact: true }).click();
  await page.getByLabel("Find reviewed work").fill(title);
  await page.locator(".plan-candidates li").filter({ hasText: title }).getByRole("button", { name: "Add to this day" }).click();
  const card = page.locator(".plan-card").filter({ hasText: title });
  let writes = 0, interrupted = false;
  page.on("request", request => { if (request.method() === "PATCH" && new URL(request.url()).pathname.endsWith("/plan")) writes += 1; });
  await page.route("**/api/workspaces/*/plan?*", async route => {
    if (writes && !interrupted) { interrupted = true; await route.fulfill({ status: 503, json: { error: "Synthetic plan read interruption", request_id: "synthetic-plan" } }); }
    else await route.continue();
  });
  await card.getByLabel("Progress for " + title).selectOption("done");
  await expect(page.getByText(/Your plan change was accepted/)).toBeVisible();
  await expect(card.getByLabel("Progress for " + title)).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 }); await accessible(page);
  await page.screenshot({ path: "test-results/phase7-plan-recovery-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Load current plan" }).click();
  await expect(page.getByText("Room to breathe.")).toBeVisible();
  expect(writes).toBe(1);
});
