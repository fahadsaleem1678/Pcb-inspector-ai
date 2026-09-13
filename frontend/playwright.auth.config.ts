import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  outputDir: './auth-test-results',
  testMatch: 'auth.spec.ts',
  workers: 1,
  timeout: 30000,
  expect: { timeout: 10000 },
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5175',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { browserName: 'chromium', viewport: { width: 1440, height: 1000 } } },
    {
      name: 'mobile',
      use: {
        browserName: 'chromium',
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: {
    command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5175 --strictPort',
    url: 'http://127.0.0.1:5175',
    timeout: 30000,
    env: {
      VITE_AUTH_MODE: 'cognito',
      VITE_COGNITO_USER_POOL_ID: 'us-east-1_TestPool',
      VITE_COGNITO_CLIENT_ID: 'publicclient',
      VITE_COGNITO_DOMAIN: 'https://pcb-test.auth.us-east-1.amazoncognito.com',
    },
  },
});
