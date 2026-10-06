import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function accessible(page: Page) {
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
}
async function enter(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore the isolated demo" }).click();
  await expect(page.getByRole("region", { name: "Synthetic demo session" })).toBeVisible();
  await expect(page.getByRole("button", { name: "New meeting", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Access & audit" })).toHaveCount(0);
}
async function extractFixture(page: Page, title: string) {
  await page.getByRole("button", { name: "Open " + title, exact: true }).click();
  await expect(page).toHaveURL(/\/people$/);
  await expect(page.getByText("Transcript indexing ready")).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Extract outcomes", exact: true }).click();
  await expect(page.getByText(/Job completed/)).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(/Rule-based extraction/)).toBeVisible();
  await expect(page.getByText("Add a person to this workspace")).toHaveCount(0);
}

test("real isolated visitor journeys across departments, exact local handoff and personal execution", async ({ page }) => {
  await enter(page);
  for (const [department, name, fixture] of [["engineering", "Engineering", "Release readiness"], ["hr", "People Operations", "Onboarding coordination"], ["finance", "Finance Control", "Month-end controls"]]) {
    await page.getByRole("group", { name: "Department experiences" }).getByRole("button", { name, exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-department", department);
    await accessible(page);
    await page.screenshot({ path: "../docs/media/visitor-" + department + "-entry.png", fullPage: true });
    await extractFixture(page, fixture);
    if (department === "hr") {
      await page.setViewportSize({ width: 390, height: 844 });
      await accessible(page);
      await page.screenshot({ path: "../docs/media/visitor-mobile-people.png", fullPage: true });
      await page.setViewportSize({ width: 1280, height: 720 });
    }
    const alex = page.getByLabel("Directory match for Alex");
    const choice = await alex.locator("option").evaluateAll(options => (options.find(option => (option as HTMLOptionElement).value) as HTMLOptionElement).value);
    await alex.selectOption(choice);
    await page.locator(".mentions li").filter({ has: alex }).getByRole("button", { name: "Confirm person" }).click();
    await expect(page.getByText("Confirmed directory match", { exact: true })).toHaveCount(1);
    await page.getByRole("button", { name: /Continue (to review|with unassigned people)/ }).click();
    const action = page.locator("article.action");
    const before = Number((await action.locator(".badge").innerText()).match(/v(\d+)/)![1]);
    await action.getByRole("button", { name: "Approve outcome" }).click();
    await expect(action.locator(".badge")).toHaveText("approved · v" + (before + 1));
    const title = await action.getByRole("heading").innerText();
    await expect(page.getByRole("button", { name: "Mark done" })).toHaveCount(0);
    await accessible(page);
    await page.screenshot({ path: "../docs/media/visitor-" + department + "-review.png", fullPage: true });
    await page.getByRole("button", { name: "Continue to handoff" }).click();
    await page.getByRole("checkbox", { name: title, exact: true }).check();
    await page.getByRole("button", { name: "Continue to preparation" }).click();
    await page.getByRole("button", { name: "Prepare handoff" }).click();
    await expect(page).toHaveURL(/handoff=preview/);
    await accessible(page);
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download handoff" }).click()]);
    expect(download.suggestedFilename()).toMatch(/-reviewed-outcomes\.md$/);
    await expect(page).toHaveURL(/handoff=receipt/);
    await page.reload();
    await expect(page.getByText(/A refresh does not prove that a file was saved/)).toBeVisible();
    await page.getByRole("button", { name: "Continue to My day" }).click();
    await page.getByLabel("Find reviewed work").fill(title);
    await page.locator(".plan-candidates li").filter({ hasText: title }).getByRole("button", { name: "Add to this day" }).click();
    const card = page.locator(".plan-card").filter({ hasText: title });
    await card.getByLabel("Progress for " + title).selectOption("done");
    await expect(page.getByText("Room to breathe.")).toBeVisible();
    await page.reload(); await page.getByText(/Completed in this plan/).click();
    await expect(card.getByLabel("Progress for " + title)).toHaveValue("done");
    await accessible(page);
    await page.screenshot({ path: "../docs/media/visitor-" + department + "-my-day.png", fullPage: true });
    await page.getByRole("link", { name: "Meetings", exact: true }).click();
  }
});

test("independent browser visitors cannot access each other's workspace or upload custom transcripts", async ({ browser, baseURL }) => {
  const first = await browser.newContext({ baseURL }), second = await browser.newContext({ baseURL });
  try {
    const a = await first.newPage(), b = await second.newPage(); await enter(a); await enter(b);
    const firstSpace = new URL(a.url()).pathname.split("/")[2], secondSpace = new URL(b.url()).pathname.split("/")[2];
    expect(firstSpace).not.toBe(secondSpace);
    const denied = await second.request.get("/api/workspaces/" + firstSpace + "/meetings");
    expect([403, 404]).toContain(denied.status());
    const csrf = (await second.cookies()).find(cookie => cookie.name === "mtt_csrf")!.value;
    const upload = await second.request.post("/api/workspaces/" + secondSpace + "/index", { headers: { Origin: new URL(b.url()).origin, "X-CSRF-Token": csrf }, data: { meeting_id: "custom", title: "Synthetic denied input", transcript: "Alex: Action: This must not be accepted.", visibility: "workspace", timezone: "UTC" } });
    expect(upload.status()).toBe(403);
    await b.getByRole("link", { name: "Settings", exact: true }).click(); await b.getByRole("link", { name: "Connections", exact: true }).click();
    await expect(b.getByRole("heading", { name: "Explore without connecting live accounts" })).toBeVisible();
    await expect(b.getByRole("button", { name: "Connect Slack" })).toHaveCount(0);
    await expect(b.getByRole("button", { name: "Bind GitHub repository" })).toHaveCount(0);
    await accessible(b);
  } finally { await first.close(); await second.close(); }
});

test("a no-action conversation has an honest empty review and reduced-motion static presentation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const mediaRequests: string[] = []; page.on("request", request => { if (request.url().endsWith(".mp4")) mediaRequests.push(request.url()); });
  await enter(page);
  await expect(page.getByRole("button", { name: "Reduced motion active" })).toBeDisabled();
  await expect(page.locator(".studio-media img")).toBeVisible();
  await extractFixture(page, "A quiet check-in");
  await page.getByRole("button", { name: /Continue (to review|with unassigned people)/ }).click();
  await expect(page.locator("article.outcome")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Approve outcome" })).toHaveCount(0);
  expect(mediaRequests).toEqual([]);
  await accessible(page);
});

test("authored media plays and loops, pause survives department changes, and tools reflow at boundary widths", async ({ page }) => {
  await enter(page);
  const video = page.locator(".studio-media video");
  await expect(video).toHaveJSProperty("paused", false);
  await expect(page.locator(".studio-media")).toHaveAttribute("data-playing", "true");
  await video.evaluate(node => { const media = node as HTMLVideoElement; media.currentTime = media.duration - .2; });
  await expect.poll(() => video.evaluate(node => (node as HTMLVideoElement).currentTime)).toBeLessThan(.6);
  await page.getByRole("button", { name: "Pause studio motion" }).click();
  await expect(video).toHaveJSProperty("paused", true);
  await page.getByRole("group", { name: "Department experiences" }).getByRole("button", { name: "People Operations", exact: true }).click();
  await expect(page.getByRole("button", { name: "Play studio motion" })).toBeVisible();
  await expect(video).not.toHaveAttribute("src");
  await page.getByRole("button", { name: "Open Onboarding coordination" }).click();
  for (const width of [850, 851, 1179, 1180, 390]) {
    await page.setViewportSize({ width, height: 844 });
    const trigger = page.getByRole("button", { name: "People tools", exact: true });
    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator(".bubble-panel")).toHaveCSS("opacity", "1");
    const geometry = await page.evaluate(() => {
      const tools = document.querySelector(".context-bubble")!.getBoundingClientRect();
      const panel = document.querySelector(".step-panel")!.getBoundingClientRect();
      return { overflow: document.documentElement.scrollWidth > innerWidth + 1, overlap: tools.left < panel.right && tools.right > panel.left && tools.top < panel.bottom && tools.bottom > panel.top };
    });
    expect(geometry).toEqual({ overflow: false, overlap: false });
    await page.keyboard.press("Escape");
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await expect(trigger).toBeFocused();
    await accessible(page);
  }
  await page.reload();
  await expect(page.getByRole("heading", { name: "Put people in context." })).toBeVisible();
  await page.screenshot({ path: "../docs/media/visitor-mobile-people.png", fullPage: true });
});
