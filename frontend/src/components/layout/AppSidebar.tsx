import {
  LayoutDashboardIcon,
  FolderKanbanIcon,
  UsersIcon,
  ShieldIcon,
  SettingsIcon,
} from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useAuth } from '@/auth/AuthContext'
import { NAV_GROUPS, type NavItemConfig } from '@/lib/navConfig'
import { userInitials } from '@/lib/userInitials'

const ICONS: Record<string, typeof LayoutDashboardIcon> = {
  Dashboard: LayoutDashboardIcon,
  Projects: FolderKanbanIcon,
  Users: UsersIcon,
  Roles: ShieldIcon,
  Settings: SettingsIcon,
}

type AppSidebarProps = {
  collapsed: boolean
  onNavigate?: () => void
}

function NavItem({
  item,
  collapsed,
  onNavigate,
}: {
  item: NavItemConfig
  collapsed: boolean
  onNavigate?: () => void
}) {
  const { hasPermission } = useAuth()
  const location = useLocation()

  if (item.type === 'link' && item.permission && !hasPermission(item.permission)) {
    return null
  }

  const Icon = ICONS[item.label] ?? LayoutDashboardIcon

  if (item.type === 'disabled') {
    const inner = (
      <div
        className={cn(
          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-muted opacity-80',
          collapsed && 'justify-center px-2',
        )}
        aria-disabled
      >
        <Icon className="size-4 shrink-0" />
        {!collapsed && (
          <>
            <span className="flex-1 text-sidebar-foreground">{item.label}</span>
            <Badge variant="secondary" className="border-sidebar-border bg-sidebar-hover text-[10px] text-sidebar-muted">
              {item.badge}
            </Badge>
          </>
        )}
      </div>
    )
    if (collapsed) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{inner}</TooltipTrigger>
          <TooltipContent side="right">
            {item.label} ({item.badge})
          </TooltipContent>
        </Tooltip>
      )
    }
    return inner
  }

  const isActive =
    item.to === '/'
      ? location.pathname === '/'
      : location.pathname.startsWith(item.to)

  const link = (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      onClick={onNavigate}
      aria-current={isActive ? 'page' : undefined}
      className={cn(
        'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium',
        collapsed && 'justify-center px-2',
        isActive
          ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-xs'
          : 'text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground',
      )}
    >
      <Icon className="size-4 shrink-0" />
      {!collapsed && <span>{item.label}</span>}
    </NavLink>
  )

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{link}</TooltipTrigger>
        <TooltipContent side="right">{item.label}</TooltipContent>
      </Tooltip>
    )
  }

  return link
}

export function AppSidebar({ collapsed, onNavigate }: AppSidebarProps) {
  const { hasPermission, user } = useAuth()

  return (
    <aside
      className={cn(
        'flex h-full shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-150',
        collapsed ? 'w-16' : 'w-60',
      )}
    >
      <div
        className={cn(
          'flex h-14 items-center border-b border-sidebar-border px-4',
          collapsed && 'justify-center px-2',
        )}
      >
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
            S
          </div>
          {!collapsed && (
            <span className="truncate font-semibold tracking-tight text-sidebar-foreground">
              ScopeDesk
            </span>
          )}
        </div>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto p-3">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter((item) => {
            if (item.type === 'disabled') return true
            if (item.type === 'link' && item.permission) {
              return hasPermission(item.permission)
            }
            return true
          })
          if (items.length === 0) return null
          return (
            <div key={group.label}>
              {!collapsed && (
                <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-sidebar-muted">
                  {group.label}
                </p>
              )}
              <div className="space-y-1">
                {items.map((item) => (
                  <NavItem
                    key={item.label}
                    item={item}
                    collapsed={collapsed}
                    onNavigate={onNavigate}
                  />
                ))}
              </div>
            </div>
          )
        })}
      </nav>
      {user && (
        <div className="border-t border-sidebar-border p-3">
          <div
            className={cn(
              'flex items-center gap-3 rounded-lg bg-sidebar-hover px-3 py-2',
              collapsed && 'justify-center px-2',
            )}
          >
            <div
              className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
              aria-hidden
            >
              {userInitials(user.full_name, user.email)}
            </div>
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-sidebar-foreground">
                  {user.full_name}
                </p>
                <p className="truncate text-xs text-sidebar-muted">{user.email}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  )
}
