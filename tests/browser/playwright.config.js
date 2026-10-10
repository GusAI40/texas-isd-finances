const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.', timeout: 30000, fullyParallel: false,
  use: { baseURL: process.env.TISD_BASE_URL || 'http://127.0.0.1:8787', screenshot: 'only-on-failure' },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } }
  ]
});
