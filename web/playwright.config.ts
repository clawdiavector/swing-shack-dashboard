import { defineConfig, devices } from '@playwright/test'

const port = process.env.PLAYWRIGHT_WEB_PORT || process.env.VITE_DEV_PORT || '3249'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}/app/daily`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
