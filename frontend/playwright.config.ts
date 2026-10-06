import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e", timeout: 180000, workers: 1, fullyParallel: false,
  use: { baseURL: process.env.MTT_E2E_URL || "http://localhost:8080", headless: true, trace: "off", screenshot: "only-on-failure", ...(process.env.MTT_BROWSER_CHANNEL ? { channel: process.env.MTT_BROWSER_CHANNEL } : {}) },
  reporter: "list",
});
