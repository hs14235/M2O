// Regenerates public/og-image.png, the 1200×627 link-preview card, from the current app:
// the brand mark and copy on the left, a real Review screenshot from the synthetic demo on
// the right. Run against a demo-mode stack (npm run test:visual:demo:keep serves :8090):
//   node scripts/og-image.mjs [http://localhost:8090]
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const base = process.argv[2] || "http://localhost:8090";
const browser = await chromium.launch();

// 1. A Review screen with one approval, so the meter shows progress.
const app = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
await app.goto(base + "/");
await app.getByRole("button", { name: "Explore the isolated demo" }).click();
await app.getByRole("button", { name: "Open Release readiness", exact: true }).click();
await app.getByText("Transcript indexing ready").waitFor({ timeout: 30000 });
await app.getByRole("button", { name: "Extract outcomes", exact: true }).click();
await app.getByRole("heading", { name: /draft outcomes? found/ }).waitFor({ timeout: 30000 });
await app.getByRole("button", { name: /Continue (to review|with unassigned people)/ }).click();
await app.locator("article.outcome").getByRole("button", { name: "Approve outcome" }).click();
await app.locator("article.outcome .badge").filter({ hasText: "approved" }).waitFor();
await app.mouse.move(5, 715);
// Open on the Review heading and its meter, with the outcome list and card below.
await app
  .getByRole("heading", { name: "Review", exact: true, level: 1 })
  .evaluate((heading) => window.scrollTo(0, heading.getBoundingClientRect().top + window.scrollY - 90));
await app.waitForTimeout(1500);
const shot = await app.screenshot({ clip: { x: 230, y: 0, width: 1050, height: 720 } });
await app.close();

// 2. The card.
const mark = readFileSync(resolve(frontend, "public/brand-mark.png")).toString("base64");
const card = await browser.newPage({ viewport: { width: 1200, height: 627 } });
await card.setContent(`<!doctype html><html><head><style>
  * { box-sizing: border-box; margin: 0; }
  body { width: 1200px; height: 627px; overflow: hidden; font-family: "Segoe UI", system-ui, sans-serif;
    background: radial-gradient(90% 120% at 0% 0%, #fdf4f8 0%, #f6f5fd 45%, #f1faf6 100%); color: #251c40; }
  .bar { height: 10px; background: linear-gradient(90deg, #b83479, #08725c 50%, #573dc0); }
  .left { position: absolute; left: 70px; top: 92px; width: 520px; }
  .left img { height: 150px; display: block; }
  h1 { margin-top: 34px; font-size: 76px; font-weight: 800; letter-spacing: -0.03em; line-height: 1; }
  h2 { margin-top: 10px; font-size: 34px; font-weight: 600; color: #573dc0; }
  p { margin-top: 30px; font-size: 27px; line-height: 1.35; color: #3b3256; }
  small { position: absolute; left: 70px; bottom: 44px; font-size: 22px; color: #6b6380; }
  .shot { position: absolute; right: -40px; top: 120px; width: 600px; border-radius: 18px; overflow: hidden;
    box-shadow: 0 30px 70px #251c4033, 0 0 0 1px #251c4014; }
  .shot img { width: 100%; display: block; }
</style></head><body>
  <div class="bar"></div>
  <div class="left">
    <img src="data:image/png;base64,${mark}" alt="">
    <h1>M2O</h1>
    <h2>Meeting 2 Outcomes</h2>
    <p>Turn meeting transcripts into reviewed, source-linked next steps for your team.</p>
  </div>
  <div class="shot"><img src="data:image/png;base64,${shot.toString("base64")}" alt=""></div>
  <small>Live synthetic demo · m2o-synthetic-demo.onrender.com</small>
</body></html>`);
await card.waitForTimeout(300);
await card.screenshot({ path: resolve(frontend, "public/og-image.png") });
await browser.close();
console.log("Wrote public/og-image.png");
