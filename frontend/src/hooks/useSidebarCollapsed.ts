import { useCallback, useEffect, useState } from 'react'

export const SIDEBAR_COLLAPSED_KEY = 'scopedesk-sidebar-collapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  } catch {
    return false
  }
}

export function useSidebarCollapsed() {
  const [collapsed, setCollapsedState] = useState(readCollapsed)

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? 'true' : 'false')
    } catch {
      /* ignore */
    }
  }, [collapsed])

  const setCollapsed = useCallback((value: boolean) => {
    setCollapsedState(value)
  }, [])

  const toggleCollapsed = useCallback(() => {
    setCollapsedState((c) => !c)
  }, [])

  return { collapsed, setCollapsed, toggleCollapsed }
}
