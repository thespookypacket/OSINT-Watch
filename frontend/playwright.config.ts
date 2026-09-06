import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  workers: 1,
  timeout: 45000,
  outputDir: "/tmp/osint-watch-browser-results",
  use: {
    baseURL: process.env.WATCH_TEST_URL || "http://localhost:8080",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
  },
  reporter: [["list"]],
});
