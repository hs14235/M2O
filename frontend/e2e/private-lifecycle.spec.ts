import { readFileSync } from "node:fs";
import { expect, test, type Locator, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

interface Fixture { url: string; schema: string; email: string; password: string; workspaces: { id: string; name: string; department: string }[]; recovery: { email: string; password: string; url: string } }
let fixture: Fixture;
// The installed runner otherwise saves automatic failure-page accessibility snapshots.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";
test.use({ screenshot: "off", trace: "off", video: "off" });
test.skip(!process.env.MTT_LIFECYCLE_FIXTURE, "Requires the coordinator's disposable synthetic lifecycle runtime.");
test.beforeAll(() => {
  fixture = JSON.parse(readFileSync(process.env.MTT_LIFECYCLE_FIXTURE!, "utf8"));
  if (fixture.url !== "http://127.0.0.1:19080" || process.env.MTT_E2E_URL !== fixture.url || !/^m2o_browser_[a-f0-9]{32}$/.test(fixture.schema)) throw new Error("Lifecycle tests require the designated disposable local runtime.");
});
async function signIn(page: Page, account: { email: string; password: string }) {
  await page.goto("/");
  await expect(page.getByLabel("Email", { exact: true })).toBeVisible();
  await privateFill(page.getByLabel("Email", { exact: true }), account.email);
  await privateFill(page.getByLabel("Password", { exact: true }), account.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Make the next step clear." })).toBeVisible();
}
async function privateFill(input: Locator, value: string) {
  try { await input.fill(value, { timeout: 10000 }); }
  catch { throw new Error("Private field entry failed; the value has been withheld."); }
}
async function link(page: Page, path: "/invite" | "/recover", privateUrl: string) {
  await page.goto(path);
  await expect(page.getByRole("heading", { name: path === "/invite" ? "Join an invited workspace" : "Recover your account" })).toBeVisible();
  const token = new URLSearchParams(new URL(privateUrl).hash.slice(1)).get("token");
  if (!token) throw new Error("Synthetic lifecycle link is missing its fragment.");
  await page.evaluate(value => { window.location.hash = new URLSearchParams({ token: value! }).toString(); }, token);
  await expect.poll(() => new URL(page.url()).hash).toBe("");
  const input = page.getByLabel(path === "/invite" ? "Private invitation link or token" : "Private recovery link or token");
  await expect.poll(async () => (await input.inputValue()) === token).toBe(true);
}
async function issue(page: Page, email: string, workspace: Fixture["workspaces"][number], role: string) {
  await page.getByRole("combobox", { name: "Workspace", exact: true }).selectOption(workspace.id);
  await page.getByRole("link", { name: "Settings", exact: true }).click(); await page.getByRole("link", { name: "Access", exact: true }).click();
  await expect(page.getByLabel("Initial password for a new account")).toHaveCount(0);
  await privateFill(page.getByLabel("Invitation email"), email);
  await page.getByLabel("Invited role").selectOption(role);
  await page.getByRole("button", { name: "Create private invitation link" }).click();
  const input = page.getByLabel("One-time invitation link"); await expect(input).toBeVisible();
  return input.inputValue();
}
async function accessible(page: Page) {
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations.map(item => ({ id: item.id, impact: item.impact }))).toEqual([]);
}

test("new invitation recipient chooses credentials, exports own data and deletes their own account", async ({ page, browser, baseURL }) => {
  await signIn(page, fixture);
  const email = "invited-" + Date.now() + "@example.test", password = "Synthetic-invitation-pass-123!";
  const url = await issue(page, email, fixture.workspaces.find(item => item.department === "engineering")!, "editor");
  const context = await browser.newContext({ baseURL });
  try {
    const recipient = await context.newPage(); await link(recipient, "/invite", url);
    await recipient.getByRole("button", { name: "Review invitation" }).click();
    await recipient.getByLabel("Your name").fill("Synthetic invited recipient");
    await privateFill(recipient.getByLabel("New password", { exact: true }), password); await privateFill(recipient.getByLabel("Confirm new password", { exact: true }), password);
    await accessible(recipient);
    await recipient.getByRole("button", { name: "Accept workspace invitation" }).click();
    await expect(recipient.getByRole("heading", { name: "Invitation accepted." })).toBeVisible();
    await expect(recipient.getByRole("button", { name: "Go to sign in" })).toBeVisible();
    await signIn(recipient, { email, password });
    await expect(recipient.getByRole("link", { name: "Access & audit" })).toHaveCount(0);
    await recipient.getByRole("link", { name: "Settings", exact: true }).click(); await recipient.getByRole("link", { name: "Privacy & data" }).click();
    const [download] = await Promise.all([recipient.waitForEvent("download"), recipient.getByRole("button", { name: "Download my account data" }).click()]);
    expect(download.suggestedFilename()).toBe("m2o-account-export.json");
    expect(await download.failure()).toBeNull();
    await recipient.getByText("Review account deletion", { exact: true }).click();
    await recipient.getByLabel("Type DELETE MY ACCOUNT").fill("DELETE MY ACCOUNT");
    await privateFill(recipient.getByLabel("Your password for account deletion"), password);
    await recipient.getByRole("button", { name: "Delete confirmed account" }).click();
    await expect(recipient.getByText(/Your account was deactivated and anonymized/)).toBeVisible();
    expect((await context.request.get("/api/me")).status()).toBe(401);
    expect((await page.context().request.get("/api/me")).status()).toBe(200);
  } finally { await context.close(); }
});

test("an existing recipient signs in to accept without replacing their password", async ({ page, browser, baseURL }) => {
  await signIn(page, fixture);
  const workspace = fixture.workspaces.find(item => item.department === "hr")!;
  const url = await issue(page, fixture.recovery.email, workspace, "reviewer");
  const context = await browser.newContext({ baseURL });
  try {
    const recipient = await context.newPage(); await link(recipient, "/invite", url);
    await recipient.getByRole("button", { name: "Review invitation" }).click();
    await expect(recipient.getByLabel("New password", { exact: true })).toHaveCount(0);
    await privateFill(recipient.getByLabel("Password", { exact: true }), fixture.recovery.password);
    await recipient.getByRole("button", { name: "Sign in as invited person" }).click();
    await recipient.getByRole("button", { name: "Accept workspace invitation" }).click();
    await expect(recipient.getByRole("heading", { name: "Invitation accepted." })).toBeVisible();
    await recipient.getByRole("button", { name: "Open workspace" }).click();
    await expect(recipient.getByRole("combobox", { name: "Workspace", exact: true })).toHaveValue(workspace.id);
  } finally { await context.close(); }
});

test("operator-assisted recovery revokes old sessions and rejects link replay", async ({ page, browser, baseURL }) => {
  const old = await browser.newContext({ baseURL });
  try {
    await signIn(await old.newPage(), fixture.recovery);
    await link(page, "/recover", fixture.recovery.url);
    const password = "Synthetic-recovered-password-123!";
    await privateFill(page.getByLabel("Recovery account email"), fixture.recovery.email);
    await privateFill(page.getByLabel("New password", { exact: true }), password); await privateFill(page.getByLabel("Confirm new password", { exact: true }), password);
    await page.getByRole("button", { name: "Reset password and revoke previous access" }).click();
    await expect(page.getByRole("heading", { name: "Password reset." })).toBeVisible();
    expect((await old.request.get("/api/me")).status()).toBe(401);
    await signIn(page, { email: fixture.recovery.email, password });
    await link(page, "/recover", fixture.recovery.url);
    await privateFill(page.getByLabel("Recovery account email"), fixture.recovery.email);
    await privateFill(page.getByLabel("New password", { exact: true }), password); await privateFill(page.getByLabel("Confirm new password", { exact: true }), password);
    await page.getByRole("button", { name: "Reset password and revoke previous access" }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Password reset." })).toHaveCount(0);
  } finally { await old.close(); }
});

test("private transcript indexing, workspace export and exact confirmed erasure preserve other workspaces", async ({ page }) => {
  await signIn(page, fixture);
  const workspace = fixture.workspaces.find(item => item.department === "finance")!;
  await page.getByRole("combobox", { name: "Workspace", exact: true }).selectOption(workspace.id);
  await page.getByRole("button", { name: "New meeting", exact: true }).click();
  await page.getByLabel("Meeting title").fill("Synthetic privacy lifecycle");
  await page.getByLabel("Transcript text").fill("Alex: Action: I will reconcile the synthetic ledger by Friday.");
  await page.getByRole("button", { name: "Save transcript and continue" }).click();
  await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
  await page.getByRole("link", { name: "Settings", exact: true }).click(); await page.getByRole("link", { name: "Privacy & data" }).click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download workspace data" }).click()]);
  expect(download.suggestedFilename()).toBe("m2o-workspace-export.json"); expect(await download.failure()).toBeNull();
  await accessible(page);
  await page.getByText("Erase this local workspace", { exact: true }).click();
  await page.getByLabel("Type the current workspace name").fill(workspace.name);
  await privateFill(page.getByLabel("Your password for workspace erasure"), fixture.password);
  await page.getByRole("button", { name: "Erase confirmed local workspace" }).click();
  await expect(page.getByText(/Local workspace content erased\.|Erasure is pending/)).toBeVisible();
  for (let attempt = 0; attempt < 3 && await page.getByText(/Erasure is pending/).isVisible(); attempt++) {
    await page.getByRole("button", { name: "Refresh privacy status" }).click();
    await privateFill(page.getByLabel("Your password for workspace erasure"), fixture.password);
    await page.getByRole("button", { name: "Retry confirmed workspace erasure" }).click();
  }
  await expect(page.getByText("Local workspace content erased.")).toBeVisible();
  await expect(page.getByText(/External tool content was not erased/)).toBeVisible();
  expect((await page.context().request.get("/api/workspaces/" + fixture.workspaces.find(item => item.department === "engineering")!.id + "/meetings")).status()).toBe(200);
  await page.reload();
  await expect(page.getByText(/Workspace privacy status could not be loaded/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Erase confirmed local workspace" })).toHaveCount(0);
});
