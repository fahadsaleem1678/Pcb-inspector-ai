import { defineConfig } from '@playwright/test';
const python = process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python';
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  expect: { timeout: 10000 },
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5174',
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
  webServer: [
    {
      command: `"${python}" ../scripts/e2e_backend.py`,
      url: 'http://127.0.0.1:8011/ready',
      timeout: 30000,
    },
    {
      command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5174 --strictPort',
      url: 'http://127.0.0.1:5174',
      env: { PCB_API_PROXY: 'http://127.0.0.1:8011' },
      timeout: 30000,
    },
  ],
});
