import { SettingsIcon, ShieldIcon, ToggleLeftIcon, UsersIcon } from 'lucide-react'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { getSettings } from '@/api/settings'
import { listRoles } from '@/api/roles'
import { listUsers } from '@/api/users'
import { IconChip } from '@/components/layout/IconChip'
import { PageHeader } from '@/components/layout/PageHeader'
import { StatCard } from '@/components/layout/StatCard'
import { WorkflowStepper } from '@/components/layout/WorkflowStepper'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { useAuth } from '@/auth/AuthContext'
import {
  PERMISSION_ROLE_MANAGE,
  PERMISSION_SETTINGS_MANAGE,
  PERMISSION_USER_MANAGE,
} from '@/lib/permissions'
import {
  groupPermissionsByArea,
  PERMISSION_AREA_LABELS,
  permissionLabel,
  type PermissionArea,
} from '@/lib/permissionLabels'
import { ChevronDownIcon } from 'lucide-react'

function timeOfDayGreeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

function formatTodayDate(): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date())
}

export function DashboardPage() {
  const { user, hasPermission } = useAuth()
  const greeting = useMemo(() => timeOfDayGreeting(), [])
  const today = useMemo(() => formatTodayDate(), [])

  const canUsers = hasPermission(PERMISSION_USER_MANAGE)
  const canRoles = hasPermission(PERMISSION_ROLE_MANAGE)
  const canSettings = hasPermission(PERMISSION_SETTINGS_MANAGE)

  const usersQuery = useQuery({
    queryKey: ['users', 'dashboard-total'],
    queryFn: () => listUsers({ limit: 1, offset: 0 }),
    enabled: canUsers,
  })

  const rolesQuery = useQuery({
    queryKey: ['roles', 'dashboard-count'],
    queryFn: listRoles,
    enabled: canRoles,
  })

  const settingsQuery = useQuery({
    queryKey: ['settings', 'dashboard'],
    queryFn: getSettings,
    enabled: canSettings,
  })

  if (!user) return null

  const grouped = groupPermissionsByArea(user.permissions)
  const areas = [...grouped.keys()] as PermissionArea[]

  const quickLinks = [
    {
      label: 'Users',
      description: 'Manage accounts and access',
      to: '/admin/users',
      icon: UsersIcon,
      tone: 'sky' as const,
      show: canUsers,
    },
    {
      label: 'Roles',
      description: 'Configure permission bundles',
      to: '/admin/roles',
      icon: ShieldIcon,
      tone: 'amber' as const,
      show: canRoles,
    },
    {
      label: 'Settings',
      description: 'Global workflow preferences',
      to: '/admin/settings',
      icon: SettingsIcon,
      tone: 'rose' as const,
      show: canSettings,
    },
  ].filter((l) => l.show)

  const showStats = canUsers || canRoles || canSettings

  return (
    <div className="space-y-8">
      <PageHeader
        title={`${greeting}, ${user.full_name.split(' ')[0] ?? user.full_name}`}
        description={today}
      />

      {showStats && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {canUsers && (
            <StatCard
              label="Total users"
              value={usersQuery.isPending ? '—' : (usersQuery.data?.total ?? 0)}
              icon={UsersIcon}
              tone="sky"
            />
          )}
          {canRoles && (
            <StatCard
              label="Roles"
              value={rolesQuery.isPending ? '—' : (rolesQuery.data?.length ?? 0)}
              icon={ShieldIcon}
              tone="amber"
            />
          )}
          {canSettings && (
            <StatCard
              label="Self-approval policy"
              value={
                settingsQuery.isPending
                  ? '—'
                  : settingsQuery.data?.allow_self_approval
                    ? 'On'
                    : 'Off'
              }
              icon={ToggleLeftIcon}
              tone="rose"
            />
          )}
        </div>
      )}

      <Card className="shadow-card">
        <CardHeader>
          <CardTitle className="text-base font-semibold">Workflow</CardTitle>
          <CardDescription>
            Eight-step delivery pipeline; scope analysis is live on each project workflow tab.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <WorkflowStepper />
        </CardContent>
      </Card>

      <Card className="shadow-card">
        <CardHeader>
          <CardTitle className="text-base font-semibold">Your access</CardTitle>
          <CardDescription>Permissions on your account, grouped by area.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {user.permissions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No permissions assigned.</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                {areas.map((area) => (
                  <Badge key={area} variant="secondary" className="text-xs">
                    {PERMISSION_AREA_LABELS[area]} {grouped.get(area)?.length ?? 0}
                  </Badge>
                ))}
              </div>
              <div className="space-y-1">
                {areas.map((area) => {
                  const codes = grouped.get(area) ?? []
                  return (
                    <Collapsible key={area} defaultOpen={area === 'admin' || area === 'project'}>
                      <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm font-medium hover:bg-muted/80">
                        <span>{PERMISSION_AREA_LABELS[area]}</span>
                        <ChevronDownIcon className="size-4 text-muted-foreground" />
                      </CollapsibleTrigger>
                      <CollapsibleContent className="px-3 pb-2">
                        <ul className="space-y-1 border-l border-border pl-3">
                          {codes.map((code) => (
                            <li key={code} className="text-sm text-muted-foreground">
                              {permissionLabel(code)}
                            </li>
                          ))}
                        </ul>
                      </CollapsibleContent>
                    </Collapsible>
                  )
                })}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {quickLinks.length > 0 && (
        <div>
          <h2 className="mb-4 text-base font-semibold text-foreground">Administration</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {quickLinks.map((link) => (
              <Card key={link.to} className="shadow-card">
                <CardHeader className="pb-2">
                  <div className="flex items-start gap-3">
                    <IconChip icon={link.icon} tone={link.tone} size="sm" />
                    <div className="min-w-0">
                      <CardTitle className="text-base">{link.label}</CardTitle>
                      <CardDescription className="mt-1">{link.description}</CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <Button asChild variant="outline" size="sm">
                    <Link to={link.to}>Open</Link>
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
