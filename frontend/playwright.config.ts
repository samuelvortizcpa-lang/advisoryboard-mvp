import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
const isLocal = baseURL.startsWith("http://localhost");

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 1,
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  webServer: isLocal
    ? {
        command: "npm run dev",
        port: 3000,
        timeout: 120_000,
        reuseExistingServer: true,
      }
    : undefined,
});
