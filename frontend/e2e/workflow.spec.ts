import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function accessible(page: Page) {
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
}
async function login(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  await page.getByLabel("Email", { exact: true }).focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
  await page.getByLabel("Email", { exact: true }).fill(process.env.MTT_E2E_EMAIL!);
  await page.getByLabel("Password", { exact: true }).fill(process.env.MTT_E2E_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Make the next step clear." })).toBeVisible();
}
async function newExample(page: Page, workspace: string, department: string) {
  await page.getByRole("combobox", { name: "Workspace", exact: true }).selectOption({ label: workspace });
  await page.getByRole("button", { name: "New meeting", exact: true }).click();
  await expect(page).toHaveURL(/\/new\/transcript$/);
  await page.getByRole("button", { name: "Load synthetic " + department + " example" }).click();
  await expect(page.getByLabel("Transcript text")).toHaveValue(/Action/);
}
async function extract(page: Page) {
  await page.getByRole("button", { name: /Save (transcript|revision) and continue/ }).click();
  await expect(page).toHaveURL(/\/people$/);
  await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Extract outcomes", exact: true }).click();
  await expect(page.getByText(/Job completed/)).toBeVisible({ timeout: 120000 });
  await expect(page.locator(".mentions li").first()).toBeVisible({ timeout: 30000 });
}
async function review(page: Page) {
  await page.getByRole("button", { name: /Continue (to review|with unassigned people)/ }).click();
  await expect(page).toHaveURL(/\/review$/);
  await expect(page.locator("article.outcome")).toHaveCount(1);
}

test("Jira handoff UI with synthetic provider responses, exact approval and receipt recovery", async ({ page }) => {
  // Only provider-facing M2O endpoints are intercepted. Login, transcript,
  // extraction and outcome review still use the running local application.
  const destination = { project_key: "M2O", project_name: "Synthetic project", resource_url: "https://synthetic.atlassian.net", version: 2 };
  const fields = [{ id: "summary", name: "Summary", required: true, has_default: false, control: "text", options: [] }, { id: "description", name: "Description", required: false, has_default: false, control: "textarea", options: [] }, { id: "customfield_10", name: "Department", required: true, has_default: false, control: "select", options: [{ id: "11", name: "Engineering" }] }];
  let receipt: unknown[] = [], approvalCount = 0, lastAction = "create";
  await page.route("**/api/workspaces/*/integrations", async route => {
    const response = await route.fetch(); const catalog = await response.json();
    await route.fulfill({ json: catalog.map((item: { id: string }) => item.id === "jira" ? { ...item, status: "connected", can_preview: true, can_publish: true } : item) });
  });
  await page.route("**/integrations/jira/metadata*", route => route.fulfill({ json: { destination, issue_types: [{ id: "10001", name: "Task" }], fields: new URL(route.request().url()).searchParams.has("issue_type_id") || new URL(route.request().url()).searchParams.has("issue_key") ? fields : [], issue: new URL(route.request().url()).searchParams.has("issue_key") ? { key: "M2O-12", fields: { issuetype: { id: "10001" }, summary: "Prior issue title" } } : null } }));
  await page.route("**/meetings/*/jira/deliveries", route => route.fulfill({ json: receipt }));
  await page.route("**/meetings/*/jira/preview", route => {
    const body = route.request().postDataJSON(); lastAction = body.action;
    expect(body.expected_item_version).toBe(2); expect(body.fields).toEqual({ customfield_10: "11" });
    return route.fulfill({ json: { id: "synthetic-proposal", action: body.action, destination, payload_hash: "a".repeat(64), expires_at: new Date(Date.now() + 60000).toISOString(), payload: { fields: { summary: "Synthetic exact Jira outcome", description: { type: "doc", version: 1, content: [] }, customfield_10: { id: "11" } } } } });
  });
  await page.route("**/jira/proposals/*/approve", route => {
    expect(route.request().postDataJSON()).toEqual({ payload_hash: "a".repeat(64), retry_rejected: false }); approvalCount += 1;
    receipt = [{ operation_id: "synthetic-operation-" + approvalCount, action: lastAction, state: "completed", project_key: "M2O", item_version: 2, result: { status: lastAction === "create" ? "created" : "updated", issue_key: "M2O-12", url: "https://synthetic.atlassian.net/browse/M2O-12" } }];
    return route.fulfill({ status: 202, json: { job_id: "synthetic-job" } });
  });
  await page.route("**/jobs/synthetic-job", route => route.fulfill({ json: { id: "synthetic-job", kind: "jira_publish", state: "completed", result: { state: "completed" }, error_code: null } }));
  await login(page); await newExample(page, "Engineering delivery", "engineering"); await extract(page); await review(page);
  const action = page.locator("article.action"); await action.getByRole("button", { name: "Approve outcome" }).click();
  await expect(action.getByText(/approved · v2/)).toBeVisible(); const title = await action.getByRole("heading").innerText();
  await page.getByRole("button", { name: "Continue to handoff" }).click();
  await page.getByRole("checkbox", { name: title, exact: true }).check(); await page.getByRole("radio", { name: /Jira/ }).check();
  await page.getByRole("button", { name: "Continue to preparation" }).click();
  await page.getByRole("button", { name: "Find available issue types" }).click(); await page.getByRole("combobox", { name: "Issue type", exact: true }).selectOption("10001");
  await page.getByRole("button", { name: "Load issue fields" }).click(); await page.getByRole("combobox", { name: "Department (required)", exact: true }).selectOption("11");
  await page.getByRole("button", { name: "Generate exact Jira preview" }).click(); await page.getByText("Inspect stored payload & snapshot hash").click(); await expect(page.getByText(/Snapshot hash:/)).toBeVisible(); await page.getByText("Inspect stored payload & snapshot hash").click();
  await accessible(page); await page.screenshot({ path: "test-results/jira-preview-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 }); expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  await accessible(page); await page.screenshot({ path: "test-results/jira-preview-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Approve exact preview and create Jira issue" }).click();
  await expect(page.getByRole("link", { name: "Open M2O-12 in Jira" })).toBeVisible(); expect(approvalCount).toBe(1);
  await page.reload();
  await expect(page.getByRole("link", { name: "Open M2O-12 in Jira" })).toBeVisible();
  await page.getByRole("button", { name: "Back to preparation" }).click(); await page.getByRole("button", { name: "Back to selection" }).click();
  await page.getByRole("checkbox", { name: title, exact: true }).check(); await page.getByRole("button", { name: "Continue to preparation" }).click();
  await page.getByRole("combobox", { name: "Jira action", exact: true }).selectOption("update"); await page.getByLabel("Existing issue key").fill("M2O-12");
  await page.getByRole("button", { name: "Load existing issue and editable fields" }).click(); await page.getByRole("combobox", { name: "Department (required)", exact: true }).selectOption("11");
  await page.getByRole("button", { name: "Generate exact Jira preview" }).click();
  await expect(page.getByText(/This replaces the issue title and description/)).toBeVisible();
  await page.getByRole("button", { name: "Approve exact preview and update Jira issue" }).click();
  await expect(page.getByText("update · M2O · outcome version 2")).toBeVisible(); expect(approvalCount).toBe(2);
});

test("department themes, calm mode and persistent daily execution plan", async ({ page }) => {
  await login(page);
  for (const [name, department] of [["People Operations", "hr"], ["Finance Control", "finance"], ["Engineering", "engineering"]]) {
    await page.getByRole("group", { name: "Department experiences" }).getByRole("button", { name, exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-department", department);
    await expect(page.getByRole("region", { name: name + " experience" })).toBeVisible();
    await accessible(page);
    await page.screenshot({ path: "test-results/theme-" + department + ".png", fullPage: true });
  }
  await page.getByRole("button", { name: "Enable calm mode", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-motion", "calm");
  await page.reload();
  await expect(page.getByRole("button", { name: "Calm mode on" })).toHaveAttribute("aria-pressed", "true");
  await newExample(page, "Engineering delivery", "engineering");
  await extract(page); await review(page);
  const title = "Plan regression " + Date.now();
  const action = page.locator("article.action");
  await action.getByText("Review fields", { exact: true }).click();
  await action.getByLabel("Title", { exact: true }).fill(title);
  await action.getByRole("button", { name: "Approve outcome" }).click();
  await expect(action.getByText(/approved · v2/)).toBeVisible();
  await page.getByRole("link", { name: "My day", exact: true }).click();
  await page.getByLabel("Find reviewed work").fill(title);
  const candidate = page.locator(".plan-candidates li").filter({ hasText: title });
  await candidate.getByRole("button", { name: "Add to this day" }).click();
  const card = page.locator(".plan-card").filter({ hasText: title });
  await expect(card).toBeVisible();
  await card.getByLabel("Progress for " + title).selectOption("done");
  await page.reload(); await page.getByText(/Completed in this plan/).click();
  await expect(card.getByLabel("Progress for " + title)).toHaveValue("done");
  await accessible(page);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  await accessible(page);
  await page.screenshot({ path: "test-results/mobile-daily-plan.png", fullPage: true });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.getByRole("button", { name: "Reduced motion active" })).toBeDisabled();
  await expect(page.locator(".scene-sphere")).toHaveCSS("animation-name", "none");
});

test("guided department flows, local handoff, optional GitHub preview and deep links", async ({ page }) => {
  await page.goto("/");
  await accessible(page);
  await login(page);
  for (const [workspace, department] of [["Engineering delivery", "engineering"], ["People operations", "hr"], ["Finance controls", "finance"]]) {
    await newExample(page, workspace, department);
    await expect(page.getByRole("heading", { name: "Bring the conversation." })).toBeVisible();
    await expect(page.getByLabel("GitHub repository")).toHaveCount(0);
    await accessible(page);
    await extract(page);
    await accessible(page);
    await review(page);
    await expect(page.getByText("0 of 5 approved.", { exact: false })).toBeVisible();
    await accessible(page);
    const action = page.locator("article.action");
    await action.getByRole("button", { name: "Approve outcome" }).click();
    await expect(action.getByText(/approved · v2/)).toBeVisible();
    const reviewedTitle = await action.getByRole("heading").innerText();
    const reviewUrl = page.url();
    await page.reload();
    await expect(page).toHaveURL(reviewUrl);
    await expect(page.getByRole("heading", { name: reviewedTitle, exact: true })).toBeVisible();
    await expect(page.locator("article.outcome")).toHaveCount(1);
    await page.getByRole("button", { name: "Continue to handoff" }).click();
    await expect(page).toHaveURL(/\/share$/);
    await expect(page.getByRole("radio", { name: /Local handoff/ })).toBeChecked();
    await expect(page.getByRole("radio", { name: /Jira/ })).toBeDisabled();
    await expect(page.getByRole("radio", { name: /Slack/ })).toBeDisabled();
    await expect(page.getByLabel("GitHub repository")).toHaveCount(0);
    await page.getByRole("checkbox", { name: reviewedTitle, exact: true }).check();
    await page.getByRole("button", { name: "Continue to preparation" }).click();
    await page.getByRole("button", { name: "Prepare handoff" }).click();
    await expect(page.getByText("Handoff ready", { exact: false })).toBeVisible();
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download handoff" }).click()]);
    expect(download.suggestedFilename()).toMatch(/-reviewed-outcomes\.md$/);
    await page.getByRole("button", { name: "Back to preparation" }).click(); await page.getByRole("button", { name: "Back to selection" }).click();
    await page.getByRole("radio", { name: /GitHub/ }).check(); await page.getByRole("button", { name: "Continue to preparation" }).click();
    const disclosure = page.getByRole("checkbox", { name: /I approve sharing/ }); if (await disclosure.count()) await disclosure.check();
    await page.getByRole("button", { name: "Generate exact preview" }).click();
    await page.getByText("Inspect stored payload & snapshot hash").click(); await expect(page.getByText(/Snapshot hash:/)).toBeVisible(); await page.getByText("Inspect stored payload & snapshot hash").click();
    await expect(page.getByRole("button", { name: /Approve exact preview and publish/ })).toBeDisabled();
    await page.getByRole("button", { name: "Back to preparation" }).click(); await page.getByRole("button", { name: "Back to selection" }).click();
    await page.getByRole("checkbox", { name: reviewedTitle, exact: true }).uncheck();
    await expect(page.getByText(/Snapshot hash/)).toHaveCount(0);
    await page.getByRole("radio", { name: /Local handoff/ }).check();
    await accessible(page);
    await page.goBack(); await expect(page).toHaveURL(/handoff=choose&provider=github/);
    await expect(page.getByRole("radio", { name: /GitHub/ })).toBeChecked();
    await page.getByRole("button", { name: "Back to review" }).click(); await expect(page).toHaveURL(/\/review$/);
    await expect(page.locator("article.outcome")).toHaveCount(1);
    await page.getByRole("button", { name: "All meetings" }).click();
  }
  await page.getByRole("link", { name: "Settings", exact: true }).click(); await page.getByRole("link", { name: "Connections", exact: true }).click();
  await expect(page).toHaveURL(/\/settings\/connections$/);
  await expect(page.getByRole("heading", { name: "Choose tools for the work." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect Jira", exact: true })).toBeDisabled();
  await expect(page.getByRole("heading", { name: "Your LinkedIn connection" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect my LinkedIn account" })).toBeDisabled();
  await accessible(page);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  await accessible(page);
  await page.screenshot({ path: "test-results/mobile-connections.png", fullPage: true });
});

test("ambiguous people, navigation guards and retained review across revisions", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  const unique = Date.now().toString(36), engineerRole = "Engineer-" + unique;
  for (const role of [engineerRole, "People lead-" + unique]) {
    await page.getByLabel("Name", { exact: true }).fill("Alex");
    await page.getByLabel("Role or relevant responsibilities").fill(role);
    await page.getByRole("button", { name: "Confirm and add participant" }).click();
    await expect(page.getByText(role, { exact: true })).toBeVisible();
  }
  await accessible(page);
  await page.getByRole("link", { name: "Meetings", exact: true }).click();
  await newExample(page, "Engineering delivery", "engineering");
  const unsaved = await page.getByLabel("Transcript text").inputValue(), newUrl = page.url();
  page.once("dialog", dialog => dialog.dismiss());
  await page.goBack();
  await expect(page).toHaveURL(newUrl);
  await expect(page.getByLabel("Transcript text")).toHaveValue(unsaved);
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("combobox", { name: "Workspace", exact: true }).selectOption({ label: "Finance controls" });
  await expect(page.getByRole("combobox", { name: "Workspace", exact: true })).toHaveValue(await page.getByRole("option", { name: "Engineering delivery" }).getAttribute("value"));
  await extract(page);
  await expect(page.getByText("Ambiguous name: multiple directory matches")).toBeVisible();
  const mention = page.locator(".mentions li").filter({ has: page.getByText("Alex", { exact: true }) });
  await mention.getByRole("combobox").selectOption({ label: "Alex · " + engineerRole });
  await mention.getByRole("button", { name: "Confirm person" }).click();
  await expect(mention.getByText("Confirmed directory match")).toBeVisible();
  await review(page);
  const action = page.locator("article.action");
  await expect(action.locator("p.muted")).toContainText("Confirmed owner");
  await action.getByText("Review fields", { exact: true }).click();
  await action.getByLabel("Title", { exact: true }).fill("Human review preserved across revisions");
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("button", { name: "Next outcome" }).click();
  await expect(action.getByLabel("Title", { exact: true })).toHaveValue("Human review preserved across revisions");
  await action.getByRole("button", { name: "Approve outcome" }).click();
  await expect(action.getByRole("heading", { name: "Human review preserved across revisions" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  await accessible(page);
  await page.screenshot({ path: "test-results/mobile-review.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: "test-results/desktop-review.png", fullPage: true });
  await page.getByRole("button", { name: "Transcript", exact: true }).click();
  await page.getByLabel("Transcript text").fill("Decision: Adopt the updated review checklist.");
  await page.getByRole("button", { name: "Save revision and continue" }).click();
  await expect(page.getByText("Revision 2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Transcript", exact: true }).click();
  await page.getByText("Transcript history and evidence search", { exact: true }).click();
  await page.getByRole("button", { name: "View transcript v1" }).click();
  await expect(page.getByText(/Human review preserved across revisions · approved/)).toBeVisible();
});
