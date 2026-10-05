import { MenuIcon, PanelLeftIcon } from 'lucide-react'
import { useLocation } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { ThemeToggleButton } from '@/components/layout/ThemeToggleButton'
import { UserMenu } from '@/components/layout/UserMenu'
import { ROUTE_TITLES } from '@/lib/navConfig'

type AppTopBarProps = {
  onMenuClick: () => void
  onSidebarToggle: () => void
  showMenuButton: boolean
}

export function AppTopBar({ onMenuClick, onSidebarToggle, showMenuButton }: AppTopBarProps) {
  const { pathname } = useLocation()
  const title = ROUTE_TITLES[pathname] ?? 'ScopeDesk'

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      {showMenuButton ? (
        <Button type="button" variant="ghost" size="icon" onClick={onMenuClick} aria-label="Open menu">
          <MenuIcon className="size-5" />
        </Button>
      ) : (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onSidebarToggle}
          aria-label="Toggle sidebar"
        >
          <PanelLeftIcon className="size-5" />
        </Button>
      )}
      <h2 className="flex-1 truncate text-sm font-medium text-foreground">{title}</h2>
      <ThemeToggleButton />
      <UserMenu />
    </header>
  )
}
