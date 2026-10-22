import { expect, test } from '@playwright/test'

import { loginAsAdmin } from '../fixtures/auth'

test.describe('Admin users', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('lists users and opens create sheet', async ({ page }) => {
    await page.goto('/admin/users')
    await expect(page.getByRole('heading', { name: 'Users', level: 1 })).toBeVisible()
    await expect(page.getByPlaceholder('Search users…')).toBeVisible()
    await page.getByRole('button', { name: 'Create user' }).click()
    await expect(page.getByText('Add an account and assign roles.')).toBeVisible()
    await expect(page.locator('#u-email')).toBeVisible()
  })
})
