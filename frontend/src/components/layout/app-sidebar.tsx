import { Link, useRouterState } from '@tanstack/react-router'
import { Anchor, LayoutList, Radar, ScrollText, TrendingUp } from 'lucide-react'

import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/incidents', label: 'Incidents', icon: LayoutList },
  { to: '/patterns', label: 'Causal Patterns', icon: Radar },
  { to: '/briefs', label: 'Intelligence Briefs', icon: ScrollText },
  { to: '/event-analysis', label: 'Event Analysis', icon: TrendingUp },
] as const

export function AppSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })

  return (
    <aside className="bg-sidebar text-sidebar-foreground flex w-64 shrink-0 flex-col border-r border-sidebar-border">
      <div className="flex items-center gap-3 px-6 py-6">
        <div className="bg-sidebar-primary flex size-9 items-center justify-center rounded-md">
          <Anchor className="text-sidebar-primary-foreground size-5" strokeWidth={2.25} />
        </div>
        <div>
          <div className="font-display text-lg leading-none font-semibold tracking-tight">
            iMaritime
          </div>
          <div className="text-sidebar-foreground/55 mt-1 text-[0.7rem] tracking-wide uppercase">
            Safety Intelligence
          </div>
        </div>
      </div>

      <nav className="flex flex-col gap-0.5 px-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
          const active = pathname === to || pathname.startsWith(`${to}/`)
          return (
            <Link
              key={to}
              to={to}
              className={cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                active
                  ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                  : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground',
              )}
            >
              <Icon className="size-4" strokeWidth={2} />
              {label}
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}
