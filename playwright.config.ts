import { defineConfig, devices } from "@playwright/test";

const desktop = { viewport: { width: 1440, height: 900 } };
const visualTest = /visual\.spec\.ts/;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "test-results",
  snapshotPathTemplate: "{testDir}/{testFilePath}-snapshots/{arg}{ext}",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 7_500 },
  reporter: [["html", { outputFolder: "playwright-report", open: "never" }], ["line"]],
  use: {
    baseURL: "http://127.0.0.1:5010",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: "mkdir -p test-results && bash scripts/run-e2e-server.sh > test-results/e2e-server.log 2>&1",
    url: "http://127.0.0.1:5010/healthz",
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [
    { name: "visual-chromium", testMatch: visualTest, use: { ...devices["Desktop Chrome"], ...desktop } },
    { name: "chromium", testIgnore: visualTest, use: { ...devices["Desktop Chrome"], ...desktop } },
    { name: "firefox", testIgnore: visualTest, use: { ...devices["Desktop Firefox"], ...desktop } },
    { name: "webkit", testIgnore: visualTest, use: { ...devices["Desktop Safari"], ...desktop } },
    { name: "pixel-7", testIgnore: visualTest, use: { ...devices["Pixel 7"] } },
    { name: "iphone-13", testIgnore: visualTest, use: { ...devices["iPhone 13"] } },
    { name: "javascript-disabled", testIgnore: visualTest, use: { ...devices["Desktop Chrome"], ...desktop, javaScriptEnabled: false } },
    { name: "reduced-motion", testIgnore: visualTest, use: { ...devices["Desktop Chrome"], ...desktop, reducedMotion: "reduce" } },
    { name: "high-contrast", testIgnore: visualTest, use: { ...devices["Desktop Chrome"], ...desktop, forcedColors: "active" } },
    { name: "zoom-200", testIgnore: visualTest, use: { ...devices["Desktop Chrome"], viewport: { width: 720, height: 450 }, deviceScaleFactor: 2 } },
  ],
});
