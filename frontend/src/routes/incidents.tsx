import { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useReportsSearch, useReportStats } from '@/api/queries'
import type { ReportFilterParams, ReportListItem, SearchToken } from '@/api/types'
import { FiltersPanel, DEFAULT_SECONDARY_FILTERS, type SecondaryFilters } from '@/components/incidents/filters-panel'
import { ReportDetailDialog } from '@/components/incidents/report-detail-dialog'
import { ReportsTable } from '@/components/incidents/reports-table'
import { SearchBar } from '@/components/incidents/search-bar'
import { SelectionToolbar } from '@/components/incidents/selection-toolbar'
import { StatCardsRow } from '@/components/incidents/stat-cards-row'
import { UploadModalTrigger } from '@/components/incidents/upload-modal'

export const Route = createFileRoute('/incidents')({
  component: IncidentsPage,
})

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100]

function toFilterParams(
  tokens: SearchToken[],
  secondary: SecondaryFilters,
  page: number,
  pageSize: number,
  sortBy: string,
  sortDir: 'asc' | 'desc',
): ReportFilterParams {
  return {
    field_search_tokens: tokens,
    date_from: secondary.dateFrom || null,
    date_to: secondary.dateTo || null,
    min_injuries: secondary.minInjuries ? Number(secondary.minInjuries) : null,
    min_fatalities: secondary.minFatalities ? Number(secondary.minFatalities) : null,
    confidence_min: secondary.confidenceRange[0],
    confidence_max: secondary.confidenceRange[1],
    human_review_required:
      secondary.humanReview === 'any' ? null : secondary.humanReview === 'required',
    has_data_in: secondary.hasDataIn,
    operation_types: secondary.operationTypes,
    vessel_types: secondary.vesselTypes,
    casual_signatures: secondary.casualSignatures,
    page,
    page_size: pageSize,
    sort_by: sortBy,
    sort_dir: sortDir,
  }
}

function IncidentsPage() {
  const [tokens, setTokens] = useState<SearchToken[]>([])
  const [draftFilters, setDraftFilters] = useState<SecondaryFilters>(DEFAULT_SECONDARY_FILTERS)
  const [appliedFilters, setAppliedFilters] = useState<SecondaryFilters>(DEFAULT_SECONDARY_FILTERS)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [sortBy, setSortBy] = useState('ingested_at')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null)

  const params = toFilterParams(tokens, appliedFilters, page, pageSize, sortBy, sortDir)
  const statsParams = toFilterParams(tokens, appliedFilters, 1, 1, sortBy, sortDir)

  const { data, isLoading, isFetching } = useReportsSearch(params)
  const { data: stats, isLoading: statsLoading } = useReportStats(statsParams)

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1

  function handleTokensChange(next: SearchToken[]) {
    setTokens(next)
    setPage(1)
  }

  function handleApply() {
    setAppliedFilters(draftFilters)
    setPage(1)
  }

  function handleReset() {
    setDraftFilters(DEFAULT_SECONDARY_FILTERS)
    setAppliedFilters(DEFAULT_SECONDARY_FILTERS)
    setTokens([])
    setPage(1)
  }

  function handleSortChange(newSortBy: string, newSortDir: 'asc' | 'desc') {
    setSortBy(newSortBy)
    setSortDir(newSortDir)
    setPage(1)
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 px-8 py-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Incidents</h1>
        </div>
        <UploadModalTrigger />
      </div>

      <StatCardsRow stats={stats} isLoading={statsLoading} />

      <SearchBar tokens={tokens} onTokensChange={handleTokensChange} />

      <FiltersPanel
        filters={draftFilters}
        onChange={setDraftFilters}
        onApply={handleApply}
        onReset={handleReset}
      />

      <SelectionToolbar />

      <div className="flex items-center justify-between">
        <p className="text-muted-foreground text-sm">
          {isLoading ? 'Loading…' : `${data?.total.toLocaleString() ?? 0} incident(s) found`}
        </p>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground text-xs">Rows per page</span>
          <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1) }}>
            <SelectTrigger size="sm" className="w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PAGE_SIZE_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="relative">
        <div className={isFetching ? 'pointer-events-none opacity-40 transition-opacity' : 'transition-opacity'}>
          <ReportsTable
            reports={data?.items ?? []}
            isLoading={isLoading}
            sortBy={sortBy}
            sortDir={sortDir}
            onSortChange={handleSortChange}
            onRowClick={(report: ReportListItem) => setSelectedReportId(report.id)}
          />
        </div>
        {isFetching && !isLoading && (
          <div className="bg-background/60 absolute inset-0 flex items-center justify-center rounded-lg backdrop-blur-[1px]">
            <div className="bg-card flex items-center gap-2.5 rounded-full border px-4 py-2 shadow-md">
              <Loader2 className="text-accent size-4 animate-spin" />
              <span className="text-sm font-medium">Fetching reports…</span>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-center gap-3">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          Previous
        </Button>
        <span className="text-muted-foreground text-xs">
          Page {page} of {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= totalPages}
          onClick={() => setPage((p) => p + 1)}
        >
          Next
        </Button>
      </div>

      <ReportDetailDialog
        reportId={selectedReportId}
        onOpenChange={(open) => !open && setSelectedReportId(null)}
      />
    </div>
  )
}
