import path from 'node:path'
import { fileURLToPath } from 'node:url'

import dotenv from 'dotenv'
import { defineConfig, devices } from '@playwright/test'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..')

dotenv.config({ path: path.join(__dirname, '.env') })
// Prefer backend admin credentials unless e2e/.env sets E2E_ADMIN_* explicitly.
dotenv.config({ path: path.join(repoRoot, 'backend', '.env'), override: true })

const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5174'
const apiURL = process.env.E2E_API_URL ?? 'http://localhost:8001'
// Always start dedicated servers so VITE_API_BASE_URL and CORS match this run.
const reuse = process.env.E2E_REUSE_SERVERS === '1'

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `bash "${path.join(repoRoot, 'scripts/e2e-start-backend.sh')}"`,
      url: `${apiURL}/health`,
      reuseExistingServer: reuse,
      timeout: 180_000,
      env: {
        ...process.env,
        E2E_API_PORT: new URL(apiURL).port || '8001',
        E2E_FRONTEND_PORT: new URL(baseURL).port || '5174',
        ALLOWED_ORIGINS: `http://localhost:${new URL(baseURL).port || '5174'},http://127.0.0.1:${new URL(baseURL).port || '5174'},http://localhost:5173,http://127.0.0.1:5173`,
      },
    },
    {
      command: `npm run dev -- --host localhost --port ${new URL(baseURL).port || '5174'}`,
      cwd: path.join(repoRoot, 'frontend'),
      url: baseURL,
      reuseExistingServer: reuse,
      timeout: 120_000,
      env: {
        ...process.env,
        VITE_API_BASE_URL: apiURL,
      },
    },
  ],
})
