import { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { AlertTriangle, TrendingUp } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useGroups } from '@/api/queries'
import type { GroupableField } from '@/api/types'

export const Route = createFileRoute('/patterns')({
  component: PatternsPage,
})

const GROUP_OPTIONS: { value: GroupableField; label: string }[] = [
  { value: 'casual_signature', label: 'Causal Signature' },
  { value: 'operation_type', label: 'Operation Type' },
  { value: 'vessel_type', label: 'Vessel Type' },
]

function PatternsPage() {
  const [groupBy, setGroupBy] = useState<GroupableField>('casual_signature')
  const { data: groups, isLoading } = useGroups({ group_by: groupBy, limit: 20 })

  const maxCount = groups && groups.length > 0 ? groups[0].count : 1

  return (
    <div className="mx-auto max-w-[1100px] space-y-6 px-8 py-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Causal Patterns</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            How many times has this pattern appeared in the global record?
          </p>
        </div>
        <Select value={groupBy} onValueChange={(v) => setGroupBy(v as GroupableField)}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {GROUP_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                Group by {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      )}

      {!isLoading && groups && groups.length === 0 && (
        <Card className="text-muted-foreground p-10 text-center text-sm">
          No grouped data yet for this field.
        </Card>
      )}

      <div className="space-y-3">
        {groups?.map((group) => (
          <Card key={group.value} className="gap-3 p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-display text-lg leading-tight font-semibold">{group.value}</p>
                <p className="text-muted-foreground mt-1 text-xs">
                  {group.earliest_date && group.latest_date
                    ? `${group.earliest_date} — ${group.latest_date}`
                    : 'Date range unknown'}
                  {group.avg_confidence !== null && ` · avg. confidence ${group.avg_confidence.toFixed(2)}`}
                </p>
              </div>
              <div className="text-right">
                <div className="font-display font-mono text-3xl leading-none font-bold tabular-nums">
                  {group.count}
                </div>
                <p className="text-muted-foreground text-[0.65rem] tracking-wide uppercase">
                  incidents recorded
                </p>
              </div>
            </div>

            <div className="bg-muted h-1.5 overflow-hidden rounded-full">
              <div
                className="bg-accent h-full rounded-full"
                style={{ width: `${Math.max(4, (group.count / maxCount) * 100)}%` }}
              />
            </div>

            <div className="flex flex-wrap gap-2 pt-1">
              {group.total_injuries > 0 && (
                <Badge variant="warning" className="gap-1">
                  <TrendingUp className="size-3" />
                  {group.total_injuries} injuries
                </Badge>
              )}
              {group.total_fatalities > 0 && (
                <Badge variant="destructive" className="gap-1">
                  <AlertTriangle className="size-3" />
                  {group.total_fatalities} fatalities
                </Badge>
              )}
              <Badge variant="secondary" className="font-mono">
                {group.sample_report_ids.length} sample report(s): #
                {group.sample_report_ids.join(', #')}
              </Badge>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
