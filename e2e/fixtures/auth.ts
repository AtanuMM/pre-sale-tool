import type { Page } from '@playwright/test'

import { adminEmail, adminPassword } from './env'

export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto('/login')
  await page.locator('#email').fill(adminEmail)
  await page.locator('#password').fill(adminPassword)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 30_000 })
  await page.waitForLoadState('networkidle')
}
