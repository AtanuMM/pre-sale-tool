import { MoonIcon, SunIcon } from 'lucide-react'
import { useRef } from 'react'

import { Button } from '@/components/ui/button'
import { useTheme } from '@/theme/ThemeContext'

export function ThemeToggleButton() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'
  const buttonRef = useRef<HTMLButtonElement>(null)

  function handleClick() {
    const el = buttonRef.current
    if (el) {
      const rect = el.getBoundingClientRect()
      toggleTheme({
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
      })
      return
    }
    toggleTheme()
  }

  return (
    <Button
      ref={buttonRef}
      type="button"
      variant="outline"
      size="icon"
      data-theme-toggle
      onClick={handleClick}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {isDark ? <SunIcon className="size-4" /> : <MoonIcon className="size-4" />}
    </Button>
  )
}
