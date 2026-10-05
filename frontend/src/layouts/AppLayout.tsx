import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { AppSidebar } from '@/components/layout/AppSidebar'
import { AppTopBar } from '@/components/layout/AppTopBar'
import { Sheet, SheetContent } from '@/components/ui/sheet'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useSidebarCollapsed } from '@/hooks/useSidebarCollapsed'
import { ROUTE_TITLES } from '@/lib/navConfig'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export function AppLayout() {
  const { collapsed, toggleCollapsed } = useSidebarCollapsed()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [isMd, setIsMd] = useState(
    typeof window !== 'undefined' ? window.matchMedia('(min-width: 768px)').matches : true,
  )
  const location = useLocation()
  const pageTitle = ROUTE_TITLES[location.pathname]
  useDocumentTitle(pageTitle)

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)')
    const onChange = () => setIsMd(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!mobileOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMobileOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mobileOpen])

  return (
    <TooltipProvider delayDuration={0}>
      <div className="flex h-svh overflow-hidden bg-background">
        {isMd ? (
          <AppSidebar collapsed={collapsed} />
        ) : (
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetContent side="left" className="w-60 p-0">
              <AppSidebar collapsed={false} onNavigate={() => setMobileOpen(false)} />
            </SheetContent>
          </Sheet>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <AppTopBar
            showMenuButton={!isMd}
            onMenuClick={() => setMobileOpen(true)}
            onSidebarToggle={toggleCollapsed}
          />
          <main className="flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-[1400px] p-6">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </TooltipProvider>
  )
}
