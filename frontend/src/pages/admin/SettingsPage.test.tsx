import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SettingsPage } from './SettingsPage'

vi.mock('@/api/settings', () => ({
  getSettings: vi.fn().mockResolvedValue({ allow_self_approval: true }),
  updateSettings: vi.fn(),
}))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SettingsPage />
    </QueryClientProvider>,
  )
}

describe('SettingsPage', () => {
  it('enables Save when switch changes', async () => {
    const user = userEvent.setup()
    renderPage()

    const save = await screen.findByRole('button', { name: 'Save changes' })
    expect(save).toBeDisabled()

    await user.click(screen.getByRole('switch'))
    expect(save).toBeEnabled()
  })
})
