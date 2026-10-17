import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e", timeout: 180000, workers: 1, fullyParallel: false,
  // Screenshot baselines only hold inside the pinned Playwright image (scripts/visual-docker.mjs).
  testIgnore: process.env.MTT_VISUAL === "1" ? [] : ["**/visual.spec.ts"],
  // Visual baselines: CSS animations are fast-forwarded, the caret hidden, and up to 0.1% of
  // pixels may differ to absorb anti-aliasing noise; layout or colour changes exceed that.
  expect: { toHaveScreenshot: { animations: "disabled", caret: "hide", maxDiffPixelRatio: 0.001 } },
  use: { baseURL: process.env.MTT_E2E_URL || "http://localhost:8080", headless: true, trace: "off", screenshot: "only-on-failure", ...(process.env.MTT_BROWSER_CHANNEL ? { channel: process.env.MTT_BROWSER_CHANNEL } : {}) },
  reporter: "list",
});
