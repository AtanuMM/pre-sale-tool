import { expect, test } from '@playwright/test'

import { loginAsAdmin } from '../fixtures/auth'
import { liveGenerate } from '../fixtures/env'

test.describe('Project workflow', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('create project and open scope analysis step', async ({ page }) => {
    const stamp = Date.now()
    const projectName = `E2E Portal ${stamp}`
    const clientName = `E2E Client ${stamp}`

    await page.goto('/projects/new')
    await expect(page.getByRole('heading', { name: 'New project' })).toBeVisible()

    await page.locator('#proj-name').fill(projectName)
    await page.locator('#proj-client').fill(clientName)
    await page.locator('#intake-body').fill(
      'E2E intake: branded web portal with sign-in, dashboard, and reporting for internal users.',
    )
    await page.getByRole('button', { name: 'Create project' }).click()

    await page.waitForURL(/\/projects\/[0-9a-f-]+$/, { timeout: 60_000 })
    await expect(page.getByRole('heading', { name: projectName })).toBeVisible()

    await page.getByRole('button', { name: 'Workflow', exact: true }).click()
    await expect(page.getByRole('navigation', { name: 'Workflow steps' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Scope Analysis/i })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Generate' })).toBeVisible()
  })

  test('scope generation reaches in review when E2E_LIVE_GENERATE=1', async ({ page }) => {
    test.skip(!liveGenerate, 'Set E2E_LIVE_GENERATE=1 to run live Gemini scope generation')

    const stamp = Date.now()
    await page.goto('/projects/new')
    await page.locator('#proj-name').fill(`E2E Gen ${stamp}`)
    await page.locator('#proj-client').fill(`E2E Gen Client ${stamp}`)
    await page.locator('#intake-body').fill(
      'Scope: customer portal with authentication, profile management, and order history.',
    )
    await page.getByRole('button', { name: 'Create project' }).click()
    await page.waitForURL(/\/projects\/[0-9a-f-]+$/, { timeout: 60_000 })

    await page.getByRole('button', { name: 'Workflow', exact: true }).click()
    await page.getByRole('button', { name: 'Generate' }).click()

    await expect(page.getByText('Generating')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/In review|Approved|Executive summary/i)).toBeVisible({
      timeout: 180_000,
    })
  })
})
