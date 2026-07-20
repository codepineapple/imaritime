import { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  AlertCircle,
  AlertOctagon,
  CheckCircle2,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import { toast } from 'sonner'

import { ApiError } from '@/api/client'
import { useCreateEventAnalysisJob, useEventAnalysisJobs, useRetryEventAnalysisJob } from '@/api/queries'
import type { BarrierCitation, EventAnalysisJobOut } from '@/api/types'
import { RUNNING_JOB_STATUSES } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
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
import { Textarea } from '@/components/ui/textarea'
import { SeveritySequence, severityBadgeVariant, SEVERITY_LABELS } from '@/components/event-analysis/severity-sequence'
import { isRunningStatus, jobBadgeVariant, stageLabel } from '@/lib/job-status'

export const Route = createFileRoute('/event-analysis')({
  component: EventAnalysisPage,
})

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function CitationRow({ citations }: { citations: BarrierCitation[] }) {
  if (citations.length === 0) return null
  return (
    <p className="text-muted-foreground mt-2 font-mono text-[0.7rem]">
      Sources:{' '}
      {citations.map((c, i) => (
        <span key={i}>
          #{c.report_id} ({c.field_name}
          {c.page_numbers.length > 0 ? `, p.${c.page_numbers.join(',')}` : ''}){i < citations.length - 1 ? '; ' : ''}
        </span>
      ))}
    </p>
  )
}

function CreateEventAnalysisForm() {
  const [description, setDescription] = useState('')
  const createJob = useCreateEventAnalysisJob()

  async function handleSubmit() {
    if (!description.trim()) return
    try {
      await createJob.mutateAsync({ description: description.trim() })
      toast.success('Analysis started — track its progress below.')
      setDescription('')
    } catch (err) {
      const message = err instanceof ApiError ? String(err.detail) : 'Could not start analysis'
      toast.error(message)
    }
  }

  return (
    <Card className="gap-3 p-5">
      <label className="text-muted-foreground text-xs tracking-wide uppercase">
        Describe what happened
      </label>
      <Textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder='e.g. "Crew member entered cargo hold on log carrier, felt dizzy, climbed back out. No injury."'
        rows={3}
      />
      <div className="flex justify-end">
        <Button onClick={handleSubmit} disabled={!description.trim() || createJob.isPending}>
          {createJob.isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Sparkles className="size-3.5" />
          )}
          Analyze
        </Button>
      </div>
    </Card>
  )
}

function AnalysisDocument({ job }: { job: EventAnalysisJobOut }) {
  if (!job.findings || !job.severity_stage) return null
  const { barrier_finding, recommended_action } = job.findings

  return (
    <Card className="border-primary/15 gap-0 overflow-hidden border-2 p-0">
      <div className="bg-primary text-primary-foreground flex items-center justify-between px-6 py-4">
        <div>
          <p className="font-display text-lg leading-tight font-semibold">Event Analysis #{job.id}</p>
          <p className="text-primary-foreground/70 text-xs">
            {job.operation_type} — {job.vessel_type}
          </p>
        </div>
        <Badge variant="secondary" className="shrink-0">
          {formatTime(job.updated_at)}
        </Badge>
      </div>

      <div className="space-y-1.5 px-6 py-5">
        <p className="text-muted-foreground text-[0.7rem] font-semibold tracking-wide uppercase">
          What was described
        </p>
        <p className="text-base leading-relaxed">{job.event_summary}</p>
      </div>

      <div className="border-t px-6 py-2">
        <SeveritySequence
          currentStage={job.severity_stage}
          nearMissCount={job.near_miss_count ?? 0}
          seriousCount={job.serious_count ?? 0}
          fatalCount={job.fatal_count ?? 0}
        />
      </div>

      <div className="divide-y border-t">
        <section className="space-y-1.5 px-6 py-5">
          <div className="flex items-center gap-2">
            <AlertOctagon className="text-destructive size-4" />
            <p className="text-muted-foreground text-[0.7rem] font-semibold tracking-wide uppercase">
              The Barrier Finding
            </p>
          </div>
          <p className="text-base leading-relaxed">{barrier_finding.condition}</p>
          <CitationRow citations={barrier_finding.citations} />
        </section>

        <section className="space-y-1.5 px-6 py-5">
          <div className="flex items-center gap-2">
            <ShieldAlert className="text-primary size-4" />
            <p className="text-muted-foreground text-[0.7rem] font-semibold tracking-wide uppercase">
              The One Check
            </p>
          </div>
          <p className="text-base font-medium leading-relaxed">{recommended_action.action}</p>
          <CitationRow citations={recommended_action.citations} />
        </section>
      </div>

      <div className="bg-muted/40 text-muted-foreground px-6 py-2.5 text-[0.7rem]">
        Based on {job.near_miss_report_ids.length + job.serious_report_ids.length + job.fatal_report_ids.length}{' '}
        historical report(s): #
        {[...job.near_miss_report_ids, ...job.serious_report_ids, ...job.fatal_report_ids].join(', #')}
      </div>
    </Card>
  )
}

function EventAnalysisDialog({
  job,
  onOpenChange,
}: {
  job: EventAnalysisJobOut | null
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={job !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="sr-only">Event Analysis #{job?.id}</DialogTitle>
        </DialogHeader>
        {job && <AnalysisDocument job={job} />}
        {job && !job.findings && (
          <p className="text-muted-foreground text-sm">This analysis has no result yet.</p>
        )}
      </DialogContent>
    </Dialog>
  )
}

function JobRow({
  job,
  onOpenJob,
  onRetry,
}: {
  job: EventAnalysisJobOut
  onOpenJob: (job: EventAnalysisJobOut) => void
  onRetry: (id: number) => void
}) {
  const clickable = job.status === 'completed'
  return (
    <TableRow className={clickable ? 'cursor-pointer' : undefined} onClick={() => clickable && onOpenJob(job)}>
      <TableCell className="align-top font-mono text-xs">{formatTime(job.created_at)}</TableCell>
      <TableCell className="max-w-72 truncate align-top">{job.description}</TableCell>
      <TableCell className="align-top">
        {job.severity_stage ? (
          <Badge variant={severityBadgeVariant(job.severity_stage)}>
            {SEVERITY_LABELS[job.severity_stage]}
          </Badge>
        ) : (
          '—'
        )}
      </TableCell>
      <TableCell className="max-w-xs align-top whitespace-normal">
        {isRunningStatus(job.status) ? (
          <span className="text-muted-foreground flex items-center gap-2 text-sm">
            <Loader2 className="size-3.5 animate-spin" />
            {stageLabel(job.status, job.stage)}
          </span>
        ) : (
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
              <Button
                size="sm"
                variant="outline"
                onClick={(e) => {
                  e.stopPropagation()
                  onRetry(job.id)
                }}
              >
                <RefreshCw className="size-3" />
                Retry
              </Button>
            )}
          </div>
        )}
        {job.status === 'failed' && job.error_message && (
          <p className="text-destructive mt-1 text-xs break-words">{job.error_message}</p>
        )}
      </TableCell>
    </TableRow>
  )
}

function JobsTable({
  jobs,
  emptyLabel,
  onOpenJob,
  onRetry,
}: {
  jobs: EventAnalysisJobOut[]
  emptyLabel: string
  onOpenJob: (job: EventAnalysisJobOut) => void
  onRetry: (id: number) => void
}) {
  if (jobs.length === 0) {
    return <p className="text-muted-foreground py-10 text-center text-sm">{emptyLabel}</p>
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Started</TableHead>
          <TableHead>Description</TableHead>
          <TableHead>Severity</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <JobRow key={job.id} job={job} onOpenJob={onOpenJob} onRetry={onRetry} />
        ))}
      </TableBody>
    </Table>
  )
}

function EventAnalysisPage() {
  const { data: jobs } = useEventAnalysisJobs()
  const retryJob = useRetryEventAnalysisJob()
  const [openJob, setOpenJob] = useState<EventAnalysisJobOut | null>(null)

  const runningJobs = (jobs ?? []).filter((j) => RUNNING_JOB_STATUSES.includes(j.status))
  const completedJobs = (jobs ?? []).filter((j) => !RUNNING_JOB_STATUSES.includes(j.status))

  return (
    <div className="mx-auto max-w-[900px] space-y-6 px-8 py-8">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Event Analysis</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Describe an event in plain language — see where it sits against every historical
          report for the same operation and vessel type, and what separates a near miss from
          a fatality in that pattern.
        </p>
      </div>

      <CreateEventAnalysisForm />

      <Card className="p-0">
        <Tabs defaultValue="running" className="p-5">
          <TabsList>
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
          <TabsContent value="running">
            <JobsTable
              jobs={runningJobs}
              emptyLabel="No analyses currently running. Describe an event above to start one."
              onOpenJob={setOpenJob}
              onRetry={(id) => retryJob.mutate(id)}
            />
          </TabsContent>
          <TabsContent value="completed">
            <JobsTable
              jobs={completedJobs}
              emptyLabel="No completed analyses yet."
              onOpenJob={setOpenJob}
              onRetry={(id) => retryJob.mutate(id)}
            />
          </TabsContent>
        </Tabs>
      </Card>

      <EventAnalysisDialog job={openJob} onOpenChange={(open) => !open && setOpenJob(null)} />
    </div>
  )
}
