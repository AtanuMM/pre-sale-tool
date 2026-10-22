import { expect, test } from '@playwright/test'

import { loginAsAdmin } from '../fixtures/auth'
import { adminEmail } from '../fixtures/env'

test.describe('Authentication', () => {
  test('redirects unauthenticated users to login', async ({ page }) => {
    await page.goto('/projects')
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  })

  test('admin can sign in and reach the app shell', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/projects')
    await expect(page.getByRole('heading', { name: 'Projects', level: 1 })).toBeVisible()
    await expect(page.getByRole('link', { name: 'New project' })).toBeVisible()
  })

  test('shows error on bad password', async ({ page }) => {
    await page.goto('/login')
    await page.locator('#email').fill(adminEmail)
    await page.locator('#password').fill('wrong-password-xyz')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('alert')).toContainText(/invalid email or password/i)
    await expect(page).toHaveURL(/\/login/)
  })
})
