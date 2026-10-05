import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ThemeToggleButton } from '@/components/layout/ThemeToggleButton'
import { ThemeProvider } from './ThemeContext'
import { THEME_STORAGE_KEY } from './themeStorage'
import * as viewTransition from './viewTransitionTheme'

describe('theme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  afterEach(() => {
    cleanup()
  })

  it('defaults to light when no saved preference', async () => {
    render(
      <ThemeProvider>
        <ThemeToggleButton />
      </ThemeProvider>,
    )
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    await waitFor(() => {
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    })
    expect(screen.getByRole('button', { name: 'Switch to dark mode' })).toBeInTheDocument()
  })

  it('toggle switches html class and saves preference', async () => {
    const user = userEvent.setup()
    const spy = vi.spyOn(viewTransition, 'applyThemeWithTransition')
    render(
      <ThemeProvider>
        <ThemeToggleButton />
      </ThemeProvider>,
    )

    await waitFor(() => {
      expect(spy).not.toHaveBeenCalled()
    })

    await user.click(screen.getByRole('button', { name: 'Switch to dark mode' }))
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(spy).toHaveBeenCalled()
    spy.mockRestore()
  })
})
