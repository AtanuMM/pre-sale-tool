import {
  PERMISSION_PROJECT_VIEW,
  PERMISSION_ROLE_MANAGE,
  PERMISSION_SETTINGS_MANAGE,
  PERMISSION_USER_MANAGE,
} from '@/lib/permissions'

export type NavItemConfig =
  | {
      type: 'link'
      label: string
      to: string
      permission?: string
    }
  | {
      type: 'disabled'
      label: string
      badge: string
    }

export type NavGroup = {
  label: string
  items: NavItemConfig[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Workspace',
    items: [
      { type: 'link', label: 'Dashboard', to: '/' },
      {
        type: 'link',
        label: 'Projects',
        to: '/projects',
        permission: PERMISSION_PROJECT_VIEW,
      },
    ],
  },
  {
    label: 'Administration',
    items: [
      { type: 'link', label: 'Users', to: '/admin/users', permission: PERMISSION_USER_MANAGE },
      { type: 'link', label: 'Roles', to: '/admin/roles', permission: PERMISSION_ROLE_MANAGE },
      {
        type: 'link',
        label: 'Settings',
        to: '/admin/settings',
        permission: PERMISSION_SETTINGS_MANAGE,
      },
    ],
  },
]

export const ROUTE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/projects': 'Projects',
  '/projects/new': 'New project',
  '/admin/users': 'Users',
  '/admin/roles': 'Roles',
  '/admin/settings': 'Settings',
  '/403': 'Forbidden',
}
