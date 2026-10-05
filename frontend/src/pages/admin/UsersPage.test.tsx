import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { TooltipProvider } from '@/components/ui/tooltip'
import { filterUsers } from '@/lib/filterUsers'
import type { UserAdmin, UserListResponse } from '@/api/types'
import { UsersPage } from './UsersPage'

vi.mock('@/api/users', () => ({
  listUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  resetUserPassword: vi.fn(),
}))

vi.mock('@/api/roles', () => ({
  listRoles: vi.fn().mockResolvedValue([{ id: 'r1', name: 'Admin' }]),
}))

import { listUsers } from '@/api/users'

const mockUsers: UserAdmin[] = [
  {
    id: '1',
    email: 'active@example.com',
    full_name: 'Active User',
    is_active: true,
    last_login_at: null,
    roles: [{ id: 'r1', name: 'Admin' }],
  },
  {
    id: '2',
    email: 'inactive@example.com',
    full_name: 'Inactive User',
    is_active: false,
    last_login_at: null,
    roles: [{ id: 'r1', name: 'Admin' }],
  },
  {
    id: '3',
    email: 'other@example.com',
    full_name: 'Other Person',
    is_active: true,
    last_login_at: null,
    roles: [{ id: 'r1', name: 'Admin' }],
  },
]

describe('filterUsers', () => {
  it('filters by search and status', () => {
    expect(filterUsers(mockUsers, 'inactive@', 'all')).toHaveLength(1)
    expect(filterUsers(mockUsers, '', 'inactive')).toHaveLength(1)
    expect(filterUsers(mockUsers, '', 'active')).toHaveLength(2)
  })
})

describe('UsersPage search', () => {
  it('narrows visible rows when searching', async () => {
    vi.mocked(listUsers).mockResolvedValue({ total: 3, items: mockUsers } as UserListResponse)
    const user = userEvent.setup()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <UsersPage />
        </TooltipProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Active User')).toBeInTheDocument()
    await user.type(screen.getByPlaceholderText('Search users…'), 'inactive@')
    expect(screen.queryByText('Active User')).not.toBeInTheDocument()
    expect(screen.getByText('Inactive User')).toBeInTheDocument()
  })
})
