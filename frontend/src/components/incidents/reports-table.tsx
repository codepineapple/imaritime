import { ArrowDown, ArrowUp, ArrowUpDown, Sparkles } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { MatchType, ReportListItem } from '@/api/types'
import { confidenceKind, confidenceLabel } from '@/lib/confidence'
import { useReportSelectionStore } from '@/stores/report-selection-store'
import { cn } from '@/lib/utils'

const COLUMNS: { key: string; label: string; sortable?: boolean }[] = [
  { key: 'id', label: '#', sortable: true },
  { key: 'incident_date', label: 'Date', sortable: true },
  { key: 'incident_title', label: 'Incident Title', sortable: true },
  { key: 'incident_type', label: 'Type', sortable: true },
  { key: 'operation_type', label: 'Operation' },
  { key: 'vessel_type', label: 'Vessel' },
  { key: 'injuries', label: 'Inj.', sortable: true },
  { key: 'fatalities', label: 'Fat.', sortable: true },
  { key: 'overall_confidence', label: 'Confidence', sortable: true },
  { key: 'human_review_required', label: 'Review' },
]

function MatchBadge({ matchType }: { matchType: MatchType }) {
  if (!matchType) return null
  if (matchType === 'both') {
    return (
      <Badge variant="secondary" className="gap-1 font-mono text-[0.65rem]">
        <Sparkles className="size-2.5" />
        keyword + semantic
      </Badge>
    )
  }
  if (matchType === 'semantic') {
    return (
      <Badge variant="secondary" className="gap-1 font-mono text-[0.65rem]">
        <Sparkles className="size-2.5" />
        semantic match
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="font-mono text-[0.65rem]">
      keyword match
    </Badge>
  )
}

export function ReportsTable({
  reports,
  isLoading,
  sortBy,
  sortDir,
  onSortChange,
  onRowClick,
}: {
  reports: ReportListItem[]
  isLoading: boolean
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSortChange: (sortBy: string, sortDir: 'asc' | 'desc') => void
  onRowClick: (report: ReportListItem) => void
}) {
  const { selectedIds, toggle, isSelected, setSelected } = useReportSelectionStore()
  const hasMatchTypes = reports.some((r) => r.match_type)

  const visibleIds = reports.map((r) => r.id)
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id))
  const someVisibleSelected = visibleIds.some((id) => selectedIds.includes(id))

  function handleSelectAllChange() {
    if (allVisibleSelected) {
      // Deselect just this page's rows, leaving any selection from
      // other pages untouched.
      setSelected(selectedIds.filter((id) => !visibleIds.includes(id)))
    } else {
      // Select every row on this page, in addition to whatever's
      // already selected elsewhere.
      setSelected([...new Set([...selectedIds, ...visibleIds])])
    }
  }

  function handleHeaderClick(key: string) {
    if (key === sortBy) {
      onSortChange(key, sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      onSortChange(key, 'desc')
    }
  }

  return (
    <div className="bg-card overflow-hidden rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-10">
              {reports.length > 0 && (
                <Checkbox
                  checked={allVisibleSelected ? true : someVisibleSelected ? 'indeterminate' : false}
                  onCheckedChange={handleSelectAllChange}
                  aria-label="Select all reports on this page"
                />
              )}
            </TableHead>
            {COLUMNS.map((col) => (
              <TableHead
                key={col.key}
                className={cn(
                  'font-display text-xs font-semibold tracking-wide uppercase',
                  col.sortable && 'cursor-pointer select-none',
                )}
                onClick={() => col.sortable && handleHeaderClick(col.key)}
              >
                <span className="flex items-center gap-1">
                  {col.label}
                  {col.sortable &&
                    (sortBy === col.key ? (
                      sortDir === 'asc' ? (
                        <ArrowUp className="size-3" />
                      ) : (
                        <ArrowDown className="size-3" />
                      )
                    ) : (
                      <ArrowUpDown className="size-3 opacity-30" />
                    ))}
                </span>
              </TableHead>
            ))}
            {hasMatchTypes && (
              <TableHead className="font-display text-xs font-semibold tracking-wide uppercase">
                Match
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading &&
            Array.from({ length: 8 }).map((_, i) => (
              <TableRow key={`skeleton-${i}`}>
                <TableCell />
                {COLUMNS.map((col) => (
                  <TableCell key={col.key}>
                    <div className="bg-muted h-4 w-full max-w-24 animate-pulse rounded" />
                  </TableCell>
                ))}
              </TableRow>
            ))}

          {!isLoading && reports.length === 0 && (
            <TableRow>
              <TableCell
                colSpan={COLUMNS.length + 2}
                className="text-muted-foreground h-32 text-center"
              >
                No incidents match the current filters.
              </TableCell>
            </TableRow>
          )}

          {!isLoading &&
            reports.map((report) => {
              const selected = isSelected(report.id)
              return (
                <TableRow
                  key={report.id}
                  className="cursor-pointer"
                  data-state={selected ? 'selected' : undefined}
                  onClick={() => onRowClick(report)}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selected}
                      onCheckedChange={() => toggle(report.id)}
                      aria-label={`Select report ${report.id}`}
                    />
                  </TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs">
                    {report.id}
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums">
                    {report.incident_date ?? '—'}
                  </TableCell>
                  <TableCell className="max-w-80 truncate font-medium">
                    {report.incident_title ?? '(untitled)'}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {report.incident_type ?? '—'}
                  </TableCell>
                  <TableCell className="text-muted-foreground max-w-40 truncate">
                    {report.operation_type ?? '—'}
                  </TableCell>
                  <TableCell className="text-muted-foreground max-w-40 truncate">
                    {report.vessel_type ?? '—'}
                  </TableCell>
                  <TableCell
                    className={cn(
                      'font-mono text-xs tabular-nums',
                      report.injuries > 0 && 'text-warning font-semibold',
                    )}
                  >
                    {report.injuries}
                  </TableCell>
                  <TableCell
                    className={cn(
                      'font-mono text-xs tabular-nums',
                      report.fatalities > 0 && 'text-destructive font-semibold',
                    )}
                  >
                    {report.fatalities}
                  </TableCell>
                  <TableCell>
                    <Badge variant={confidenceKind(report.overall_confidence)} className="font-mono">
                      {report.overall_confidence !== null ? report.overall_confidence.toFixed(2) : '—'}{' '}
                      {confidenceLabel(report.overall_confidence)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {report.human_review_required ? (
                      <Badge variant="warning">Required</Badge>
                    ) : (
                      <Badge variant="success">Verified</Badge>
                    )}
                  </TableCell>
                  {hasMatchTypes && (
                    <TableCell>
                      <MatchBadge matchType={report.match_type} />
                    </TableCell>
                  )}
                </TableRow>
              )
            })}
        </TableBody>
      </Table>
    </div>
  )
}
