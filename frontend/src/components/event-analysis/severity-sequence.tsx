import { ArrowRight } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import type { SeverityStage } from '@/api/types'
import { cn } from '@/lib/utils'

const STAGES: { key: SeverityStage; label: string }[] = [
  { key: 'near_miss', label: 'Near Miss' },
  { key: 'serious', label: 'Serious Injury' },
  { key: 'fatal', label: 'Fatality' },
]

export type SeverityBadgeVariant = 'destructive' | 'warning' | 'success'

/** Maps a severity stage to the right badge color -- fatal reads as
 * destructive, serious as a warning, near-miss as a calm success,
 * consistent with how the rest of the app colors injury/fatality data. */
export function severityBadgeVariant(stage: SeverityStage): SeverityBadgeVariant {
  if (stage === 'fatal') return 'destructive'
  if (stage === 'serious') return 'warning'
  return 'success'
}

export const SEVERITY_LABELS: Record<SeverityStage, string> = {
  near_miss: 'Near Miss',
  serious: 'Serious Injury',
  fatal: 'Fatality',
}

function stageStyles(stage: SeverityStage, isCurrent: boolean): string {
  if (isCurrent) {
    return 'border-accent bg-accent/10 text-accent shadow-lg scale-110'
  }
  if (stage === 'fatal') {
    return 'border-destructive/40 bg-destructive/5 text-destructive'
  }
  if (stage === 'serious') {
    return 'border-warning/50 bg-warning/10 text-warning-foreground'
  }
  return 'border-border bg-card text-foreground'
}

export function SeveritySequence({
  currentStage,
  nearMissCount,
  seriousCount,
  fatalCount,
}: {
  currentStage: SeverityStage
  nearMissCount: number
  seriousCount: number
  fatalCount: number
}) {
  const counts: Record<SeverityStage, number> = {
    near_miss: nearMissCount,
    serious: seriousCount,
    fatal: fatalCount,
  }

  return (
    <div className="flex flex-wrap items-start justify-center gap-1 py-6">
      {STAGES.map((stage, i) => {
        const isCurrent = stage.key === currentStage
        const count = counts[stage.key]
        return (
          <div key={stage.key} className="flex items-start gap-1">
            <div className="flex w-28 flex-col items-center gap-2">
              <div className="flex h-6 items-center">
                {isCurrent && (
                  <Badge variant="warning" className="whitespace-nowrap">
                    YOU ARE HERE
                  </Badge>
                )}
              </div>
              <div
                className={cn(
                  'font-display flex size-20 items-center justify-center rounded-full border-4 text-2xl font-bold tabular-nums transition-transform',
                  stageStyles(stage.key, isCurrent),
                )}
              >
                {count}
              </div>
              <p className="text-center text-xs font-semibold tracking-wide uppercase">{stage.label}</p>
              <p className="text-muted-foreground text-center text-[0.7rem]">
                {count} case{count === 1 ? '' : 's'}
              </p>
            </div>
            {i < STAGES.length - 1 && (
              <ArrowRight className="text-muted-foreground/40 mt-9 size-6 shrink-0" />
            )}
          </div>
        )
      })}
    </div>
  )
}
