import { Card } from '@/components/ui/card'
import type { StatsOut } from '@/api/types'

function StatCard({
  label,
  value,
  accent,
}: {
  label: string
  value: string
  accent?: 'warning' | 'destructive'
}) {
  return (
    <Card className="gap-1 px-5 py-4">
      <p className="text-muted-foreground text-[0.7rem] font-medium tracking-wide uppercase">
        {label}
      </p>
      <p
        className={
          'font-display font-mono text-2xl font-semibold tabular-nums ' +
          (accent === 'warning'
            ? 'text-warning'
            : accent === 'destructive'
              ? 'text-destructive'
              : 'text-foreground')
        }
      >
        {value}
      </p>
    </Card>
  )
}

export function StatCardsRow({ stats, isLoading }: { stats?: StatsOut; isLoading: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <StatCard label="Total Reports" value={isLoading ? '—' : stats!.total_reports.toLocaleString()} />
      <StatCard
        label="Injuries"
        value={isLoading ? '—' : stats!.total_injuries.toLocaleString()}
        accent="warning"
      />
      <StatCard
        label="Fatalities"
        value={isLoading ? '—' : stats!.total_fatalities.toLocaleString()}
        accent="destructive"
      />
      <StatCard
        label="Need Review"
        value={isLoading ? '—' : stats!.human_review_required.toLocaleString()}
        accent="warning"
      />
      <StatCard
        label="Avg. Confidence"
        value={isLoading || stats!.avg_confidence === null ? '—' : stats!.avg_confidence.toFixed(2)}
      />
    </div>
  )
}
