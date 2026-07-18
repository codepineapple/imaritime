import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { AlertTriangle, Download, Loader2, ScrollText, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'

import { ApiError } from '@/api/client'
import { useBulkDeleteReports, useConfig, useCreateBriefJob, useExportReports } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useReportSelectionStore } from '@/stores/report-selection-store'

export function SelectionToolbar() {
  const { selectedIds, clear } = useReportSelectionStore()
  const { data: config } = useConfig()
  const createBriefJob = useCreateBriefJob()
  const bulkDelete = useBulkDeleteReports()
  const exportReports = useExportReports()
  const navigate = useNavigate()
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  if (selectedIds.length === 0) return null

  const maxReportsPerBrief = config?.max_reports_per_brief

  async function handleGenerateBrief() {
    if (maxReportsPerBrief !== undefined && selectedIds.length > maxReportsPerBrief) {
      toast.error(
        `You've selected ${selectedIds.length} reports, but a brief can only be generated from up to ${maxReportsPerBrief} at a time. Deselect some and try again.`,
      )
      return
    }
    try {
      await createBriefJob.mutateAsync({ report_ids: selectedIds })
      toast.success('Brief generation started — track it on the Intelligence Briefs page.')
      clear()
      navigate({ to: '/briefs' })
    } catch (err) {
      const message = err instanceof ApiError ? String(err.detail) : 'Could not start brief generation'
      toast.error(message)
    }
  }

  async function handleExport() {
    try {
      await exportReports.mutateAsync({ report_ids: selectedIds })
      toast.success(`Exported ${selectedIds.length} report(s).`)
    } catch (err) {
      const message = err instanceof ApiError ? String(err.detail) : 'Export failed'
      toast.error(message)
    }
  }

  async function handleDelete() {
    try {
      const result = await bulkDelete.mutateAsync({ report_ids: selectedIds })
      toast.success(`Deleted ${result.deleted.length} report(s).`)
      setConfirmingDelete(false)
      clear()
    } catch (err) {
      const message = err instanceof ApiError ? String(err.detail) : 'Delete failed'
      toast.error(message)
    }
  }

  return (
    <div className="bg-card flex flex-wrap items-center gap-3 rounded-lg border px-4 py-2.5">
      <Badge variant="secondary" className="font-mono">
        {selectedIds.length} selected
      </Badge>

      {!confirmingDelete ? (
        <>
          <Button size="sm" onClick={handleGenerateBrief} disabled={createBriefJob.isPending}>
            {createBriefJob.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <ScrollText className="size-3.5" />
            )}
            Generate Brief
          </Button>
          <Button size="sm" variant="outline" onClick={handleExport} disabled={exportReports.isPending}>
            {exportReports.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Download className="size-3.5" />
            )}
            Export
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="text-destructive hover:text-destructive"
            onClick={() => setConfirmingDelete(true)}
          >
            <Trash2 className="size-3.5" />
            Delete
          </Button>
          <button
            onClick={clear}
            className="text-muted-foreground hover:text-foreground ml-auto"
            aria-label="Clear selection"
          >
            <X className="size-4" />
          </button>
        </>
      ) : (
        <>
          <span className="text-muted-foreground text-sm">
            Delete {selectedIds.length} report(s)? This can't be undone.
          </span>
          <Button size="sm" variant="outline" onClick={() => setConfirmingDelete(false)}>
            Cancel
          </Button>
          <Button size="sm" variant="destructive" onClick={handleDelete} disabled={bulkDelete.isPending}>
            {bulkDelete.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <AlertTriangle className="size-3.5" />
            )}
            Confirm delete
          </Button>
        </>
      )}
    </div>
  )
}
