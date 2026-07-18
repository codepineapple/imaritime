import { useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2, Plus, RefreshCw, UploadCloud } from 'lucide-react'
import { toast } from 'sonner'

import { ApiError } from '@/api/client'
import { useIngestionJobs, useRetryIngestionJob, useUploadDocument, useUploadJsonl } from '@/api/queries'
import type { IngestionJobOut } from '@/api/types'
import { RUNNING_JOB_STATUSES } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { isRunningStatus, jobBadgeVariant, stageLabel } from '@/lib/job-status'

const SUPPORTED_FORMATS = 'PDF, TXT, MD, or pre-extracted JSON/JSONL'
const JSONL_EXTENSIONS = ['.jsonl', '.json']

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function JobRow({ job, onRetry }: { job: IngestionJobOut; onRetry: (id: number) => void }) {
  return (
    <TableRow>
      <TableCell className="align-top font-mono text-xs">{formatTime(job.created_at)}</TableCell>
      <TableCell className="max-w-56 truncate align-top font-medium">
        {job.filename ?? 'untitled'}
      </TableCell>
      <TableCell className="text-muted-foreground align-top text-xs">
        {job.content_type ?? '—'}
      </TableCell>
      <TableCell className="max-w-xs align-top whitespace-normal">
        {isRunningStatus(job.status) ? (
          <span className="text-muted-foreground flex items-center gap-2 text-sm">
            <Loader2 className="size-3.5 animate-spin" />
            {stageLabel(job.status, job.stage)}
          </span>
        ) : (
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge variant={jobBadgeVariant(job.status)} className="gap-1">
                {job.status === 'completed' ? (
                  <CheckCircle2 className="size-3" />
                ) : (
                  <AlertCircle className="size-3" />
                )}
                {job.status === 'completed' ? 'Completed' : 'Failed'}
              </Badge>
              {job.status === 'failed' && (
                <Button size="sm" variant="outline" onClick={() => onRetry(job.id)}>
                  <RefreshCw className="size-3" />
                  Retry
                </Button>
              )}
            </div>
            {job.status === 'failed' && job.error_message && (
              <p className="text-destructive text-xs break-words">{job.error_message}</p>
            )}
          </div>
        )}
      </TableCell>
    </TableRow>
  )
}

function JobsTable({
  jobs,
  emptyLabel,
  onRetry,
}: {
  jobs: IngestionJobOut[]
  emptyLabel: string
  onRetry: (id: number) => void
}) {
  if (jobs.length === 0) {
    return <p className="text-muted-foreground py-8 text-center text-sm">{emptyLabel}</p>
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Uploaded</TableHead>
          <TableHead>File</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <JobRow key={job.id} job={job} onRetry={onRetry} />
        ))}
      </TableBody>
    </Table>
  )
}

export function UploadModal({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isUploading, setIsUploading] = useState(false)
  const uploadDocument = useUploadDocument()
  const uploadJsonl = useUploadJsonl()
  const retryJob = useRetryIngestionJob()
  const { data: jobs } = useIngestionJobs()

  const runningJobs = (jobs ?? []).filter((j) => RUNNING_JOB_STATUSES.includes(j.status))
  const completedJobs = (jobs ?? []).filter((j) => !RUNNING_JOB_STATUSES.includes(j.status))

  async function uploadOne(file: File): Promise<{ file: File; ok: boolean; message: string }> {
    const isJsonl = JSONL_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext))
    try {
      if (isJsonl) {
        const result = await uploadJsonl.mutateAsync(file)
        return {
          file,
          ok: result.failed === 0,
          message: `${result.inserted} inserted, ${result.duplicates} duplicate(s), ${result.failed} failed`,
        }
      }
      await uploadDocument.mutateAsync(file)
      return { file, ok: true, message: 'queued for processing' }
    } catch (err) {
      const message = err instanceof ApiError ? String(err.detail) : 'upload failed'
      return { file, ok: false, message }
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (files.length === 0) return

    setIsUploading(true)
    try {
      // Fire every file's upload request concurrently -- this only
      // saves the file + creates its job row + enqueues the Celery
      // task, so it's fast regardless of how many files there are. The
      // actual parsing/extraction for each is then queued and
      // processed by the worker at its own concurrency, same as
      // before; this just lets you select a batch at once instead of
      // one at a time.
      const results = await Promise.all(files.map(uploadOne))

      if (files.length === 1) {
        const [result] = results
        result.ok ? toast.success(`${result.file.name}: ${result.message}`) : toast.error(`${result.file.name}: ${result.message}`)
      } else {
        const succeeded = results.filter((r) => r.ok).length
        const failed = results.length - succeeded
        if (failed === 0) {
          toast.success(`${succeeded} file(s) queued for processing.`)
        } else {
          toast.warning(`${succeeded} file(s) queued, ${failed} failed to upload.`)
          for (const r of results.filter((r) => !r.ok)) {
            toast.error(`${r.file.name}: ${r.message}`)
          }
        }
      }
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">Upload Reports</DialogTitle>
        </DialogHeader>

        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.md,.markdown,.json,.jsonl"
          multiple
          className="hidden"
          onChange={handleFileChange}
        />

        <button
          onClick={() => inputRef.current?.click()}
          disabled={isUploading}
          className="border-muted-foreground/30 hover:border-accent hover:bg-accent/5 flex shrink-0 flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed py-10 transition-colors disabled:opacity-60"
        >
          {isUploading ? (
            <Loader2 className="text-accent size-8 animate-spin" />
          ) : (
            <div className="bg-accent/10 flex size-14 items-center justify-center rounded-full">
              <Plus className="text-accent size-7" />
            </div>
          )}
          <div className="text-center">
            <p className="font-medium">
              {isUploading ? 'Uploading…' : 'Click to select one or more files'}
            </p>
            <p className="text-muted-foreground mt-1 flex items-center justify-center gap-1.5 text-xs">
              <UploadCloud className="size-3.5" />
              Supported formats: {SUPPORTED_FORMATS}
            </p>
          </div>
        </button>

        <Tabs defaultValue="running" className="mt-2 flex min-h-0 flex-1 flex-col">
          <TabsList className="shrink-0">
            <TabsTrigger value="running">
              Running
              {runningJobs.length > 0 && (
                <Badge variant="secondary" className="ml-1.5 rounded-full px-1.5">
                  {runningJobs.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="completed">Completed</TabsTrigger>
          </TabsList>
          <TabsContent value="running" className="min-h-0 flex-1 overflow-y-auto">
            <JobsTable
              jobs={runningJobs}
              emptyLabel="No uploads currently processing."
              onRetry={(id) => retryJob.mutate(id)}
            />
          </TabsContent>
          <TabsContent value="completed" className="min-h-0 flex-1 overflow-y-auto">
            <JobsTable
              jobs={completedJobs}
              emptyLabel="No completed uploads yet."
              onRetry={(id) => retryJob.mutate(id)}
            />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

export function UploadModalTrigger() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <UploadCloud className="size-4" />
        Upload Report
      </Button>
      <UploadModal open={open} onOpenChange={setOpen} />
    </>
  )
}
