import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill(process.env.MTT_E2E_EMAIL!);
  await page.getByLabel("Password", { exact: true }).fill(process.env.MTT_E2E_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Make the next step clear." })).toBeVisible();
}
async function accessible(page: Page) {
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
}
test("compact stages, approved calendar, settings and reversible workspace frame", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);
  expect(await page.getByRole("navigation", { name: "Workspace pages" }).getByRole("link").allTextContents()).toEqual(["My day", "Meetings", "Audit", "Settings"]);
  await page.getByRole("combobox", { name: "Workspace", exact: true }).selectOption({ label: "Engineering delivery" });
  await page.getByRole("button", { name: "New meeting", exact: true }).click();
  await page.getByRole("button", { name: "Import latest Google Meet transcript" }).click();
  await expect(page.getByText("Google Meet setup is required.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Preview latest accessible/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Close import" }).click();
  await expect(page.getByRole("button", { name: "Import latest Google Meet transcript" })).toBeFocused();
  await page.getByRole("button", { name: "Load synthetic engineering example" }).click();
  await page.getByRole("button", { name: "Save transcript and continue" }).click();
  await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Extract outcomes", exact: true }).click();
  await expect(page.getByText(/Job completed/)).toBeVisible({ timeout: 120000 });
  const responsibility = "Synthetic calendar owner " + Date.now();
  await page.getByText("Add a person to this workspace", { exact: true }).click();
  await page.getByLabel("Participant name", { exact: true }).fill("Alex");
  await page.getByLabel("Responsibilities", { exact: true }).fill(responsibility);
  await page.getByRole("button", { name: "Add participant", exact: true }).click();
  const mention = page.locator(".mentions li").filter({ has: page.getByText("Alex", { exact: true }) });
  await mention.getByRole("combobox").selectOption({ label: "Alex · " + responsibility });
  await mention.getByRole("button", { name: "Confirm person" }).click();
  await expect(mention.getByText("Confirmed directory match")).toBeVisible();
  await page.getByRole("button", { name: /Continue (to review|with unassigned people)/ }).click();
  const steps = page.getByRole("navigation", { name: "Meeting steps" });
  expect(await steps.getByRole("button").allTextContents()).toEqual(["1Transcript", "2People", "3Review & Deliver", "4Calendar"]);
  const count = await page.getByLabel("Outcome to review").locator("option").count();
  const ids = await page.getByLabel("Outcome to review").locator("option").evaluateAll(options => options.map(option => (option as HTMLOptionElement).value));
  expect(count).toBeGreaterThanOrEqual(5);
  const today = new Date(), due = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  for (const [index, id] of ids.entries()) {
    await page.getByRole("navigation", { name: "Outcomes to review" }).getByRole("button").nth(index).click();
    const card = page.locator("article.outcome");
    if (index !== ids.length - 1) { await card.getByText("Review fields", { exact: true }).click(); await card.getByLabel("Due date", { exact: true }).fill(due); }
    await card.getByRole("button", { name: "Approve outcome" }).click();
    await expect(card.getByText(/approved · v/)).toBeVisible();
  }
  await page.getByRole("button", { name: "Prepare delivery", exact: true }).click();
  await expect(page).toHaveURL(/\/share/);
  await expect(steps.getByRole("button", { name: "Review & Deliver", exact: true })).toHaveAttribute("aria-current", "step");
  await page.getByRole("button", { name: "Review outcomes", exact: true }).click();
  await page.getByRole("button", { name: "View outcome calendar", exact: true }).click();
  await expect(page).toHaveURL(/\/calendar$/);
  await expect(page.getByText(new RegExp(count + " approved outcomes loaded"))).toBeVisible();
  await expect(page.locator(".arcana-cards article")).toHaveCount(count - 1);
  await expect(page.locator("article.outcome-arcana.action .arcana-owner")).toContainText("Alex · confirmed directory owner");
  await accessible(page); await page.screenshot({ path: "test-results/v2-calendar-desktop.png", fullPage: true });
  await page.getByRole("button", { name: "Undated · 1" }).click();
  await expect(page.getByRole("heading", { name: "The undated constellation" })).toBeVisible();
  await expect(page.locator(".arcana-owner")).toHaveText("Unassigned");
  await page.getByRole("button", { name: "Review outcome and date" }).click();
  await expect(page).toHaveURL(/\/review\?outcome=/);
  await expect(page.getByLabel("Outcome to review")).toHaveValue(ids.at(-1)!);
  await page.getByRole("button", { name: "View outcome calendar", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 }); await accessible(page);
  await page.screenshot({ path: "test-results/v2-calendar-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Hide header" }).focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Show header" })).toBeFocused();
  await page.getByRole("button", { name: "Hide sidebar" }).focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Show sidebar" })).toBeFocused();
  await expect(page.locator("#workspace-header")).toBeHidden(); await expect(page.locator("#workspace-sidebar")).toBeHidden();
  await page.reload(); await expect(page.getByRole("button", { name: "Show header" })).toBeVisible();
  await page.getByRole("button", { name: "Show header" }).click(); await page.getByRole("button", { name: "Show sidebar" }).click();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Confirmed directory" })).toBeVisible();
  await page.getByRole("link", { name: "Connections", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your Google Meet connection" })).toBeVisible();
  await page.getByRole("link", { name: "Motion & layout", exact: true }).click();
  await page.getByRole("button", { name: "Enable calm mode", exact: true }).last().click();
  await expect(page.locator("html")).toHaveAttribute("data-motion", "calm"); await accessible(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.getByRole("button", { name: "Reduced motion active" }).last()).toBeDisabled();
  await accessible(page); await page.screenshot({ path: "test-results/v2-settings-mobile-calm.png", fullPage: true });
});

test("server search preserves matching titles and exposes record context", async ({ page }) => {
  await login(page);
  const title = "Repeated synthetic planning " + Date.now();
  for (let index = 0; index < 2; index++) {
    await page.getByRole("button", { name: "New meeting", exact: true }).click();
    await page.getByLabel("Meeting title").fill(title);
    await page.getByLabel("Transcript text").fill("Decision: Keep the reviewed checklist.");
    await page.getByRole("button", { name: "Save transcript and continue" }).click();
    await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
    await page.getByRole("button", { name: "All meetings" }).click();
  }
  const request = page.waitForRequest(value => new URL(value.url()).searchParams.get("q") === title);
  await page.getByRole("searchbox", { name: "Find a meeting" }).fill(title); await request;
  await expect(page.locator(".meeting-list li")).toHaveCount(2);
  const ids = await page.locator(".meeting-identifier").allTextContents(); expect(new Set(ids).size).toBe(2);
  await expect(page.locator(".meeting-list time")).toHaveCount(2);
  await page.getByRole("button", { name: "Group matching titles" }).click();
  await expect(page.getByText(title + " · 2 loaded records")).toBeVisible();
  await page.getByText(title + " · 2 loaded records").click();
  await expect(page.locator(".meeting-list li")).toHaveCount(2);
  await accessible(page); await page.screenshot({ path: "test-results/v2-meeting-search-desktop.png", fullPage: true });
});

test("Google import UI contract with synthetic missing, processing and reused responses", async ({ page }) => {
  // Provider-specific responses are synthetic. Login, existing transcript save,
  // indexing and reopened meeting detail use the isolated local API and worker.
  await login(page);
  await page.getByRole("combobox", { name: "Workspace", exact: true }).selectOption({ label: "People operations" });
  await page.getByRole("button", { name: "New meeting", exact: true }).click();
  await page.getByLabel("Meeting title").fill("Synthetic Meet source");
  const transcript = "Alex: Action: Prepare the synthetic onboarding checklist.";
  await page.getByLabel("Transcript text").fill(transcript);
  await page.getByRole("button", { name: "Save transcript and continue" }).click();
  await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
  const existing = new URL(page.url()).pathname.split("/").at(-2)!;
  await page.getByRole("button", { name: "All meetings" }).click();
  await page.getByRole("button", { name: "New meeting", exact: true }).click();
  const target = await page.getByLabel("Meeting identifier").inputValue();
  await page.route("**/integrations/google-meet", route => route.fulfill({ json: { configured: true, can_import: true, setup_required: false, state: "connected", source_format: "meet_api_entries", transcription_required: true } }));
  let reads = 0, saves = 0;
  await page.route("**/imports/google-meet/preview", route => {
    expect(route.request().postDataJSON()).toEqual({}); reads++;
    if (reads <= 2) return route.fulfill({ status: reads === 1 ? 404 : 409, json: { error: reads === 1 ? "Latest meeting has no transcript" : "Latest transcript is still processing" } });
    return route.fulfill({ json: { preview_id: "synthetic-preview", payload_hash: "synthetic-exact-hash", transcript, expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(), source: { provider: "google_meet", format: "meet_api_entries", conference_record: "conferenceRecords/synthetic-latest", start_time: "2026-10-05T11:00:00Z", end_time: "2026-10-05T12:00:00Z", transcript_names: ["conferenceRecords/synthetic-latest/transcripts/one"] }, participants: [{ resource: "participants/synthetic", name: "Alex", confirmed: false }] } });
  });
  await page.route("**/imports/google-meet/synthetic-preview/save", route => {
    expect(route.request().postDataJSON()).toEqual({ payload_hash: "synthetic-exact-hash", title: "Latest Google Meet transcript", meeting_id: target, visibility: "restricted" }); saves++;
    return route.fulfill({ status: 202, json: { meeting_id: existing, job_id: null, reused: true, import_id: "synthetic-import" } });
  });
  await page.getByRole("button", { name: "Import latest Google Meet transcript" }).click();
  for (const message of ["Latest meeting has no transcript", "Latest transcript is still processing"]) {
    await page.getByRole("button", { name: "Preview latest accessible Google Meet transcript" }).click();
    await expect(page.getByRole("alert")).toHaveText(message);
    await expect(page.getByRole("button", { name: "Save this transcript and continue" })).toHaveCount(0);
  }
  await page.getByRole("button", { name: "Preview latest accessible Google Meet transcript" }).click();
  await expect(page.locator(".google-source-preview pre")).toHaveText(transcript);
  await page.getByText("Source and participant labels", { exact: true }).click();
  await expect(page.getByText("Participant labels are unconfirmed: Alex.")).toBeVisible();
  expect(await page.locator("form form").count()).toBe(0); await accessible(page);
  await page.setViewportSize({ width: 390, height: 844 }); await accessible(page);
  await page.screenshot({ path: "test-results/v2-meet-synthetic-preview-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Save this transcript and continue" }).click();
  await expect(page).toHaveURL(new RegExp("/" + existing + "/people$"));
  await expect(page.getByText("Synthetic Meet source", { exact: true })).toBeVisible();
  expect(reads).toBe(3); expect(saves).toBe(1);
});
