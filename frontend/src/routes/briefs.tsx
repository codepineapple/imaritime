import { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  AlertCircle,
  AlertOctagon,
  CheckCircle2,
  FileWarning,
  Loader2,
  RefreshCw,
  ScrollText,
  ShieldAlert,
} from 'lucide-react'

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
import { useBriefJobs, useRetryBriefJob } from '@/api/queries'
import type { BriefCitation, BriefJobOut, IntelligenceBrief } from '@/api/types'
import { RUNNING_JOB_STATUSES } from '@/api/types'
import { isRunningStatus, jobBadgeVariant, stageLabel } from '@/lib/job-status'

export const Route = createFileRoute('/briefs')({
  component: BriefsPage,
})

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function CitationRow({ citations }: { citations: BriefCitation[] }) {
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

function BriefDocument({ job, brief }: { job: BriefJobOut; brief: IntelligenceBrief }) {
  return (
    <Card className="border-primary/15 gap-0 overflow-hidden border-2 p-0">
      <div className="bg-primary text-primary-foreground flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2.5">
          <ScrollText className="size-5" />
          <div>
            <p className="font-display text-lg leading-tight font-semibold">
              Brief #{job.id}
            </p>
            <p className="text-primary-foreground/70 text-xs">
              {job.report_ids.length} report(s) analyzed — #{job.report_ids.join(', #')}
            </p>
          </div>
        </div>
        <Badge variant="secondary" className="shrink-0">
          {formatTime(job.updated_at)}
        </Badge>
      </div>

      <div className="divide-y">
        <section className="space-y-1.5 px-6 py-5">
          <p className="text-muted-foreground text-[0.7rem] font-semibold tracking-wide uppercase">
            Recurrence
          </p>
          <p className="font-display text-lg leading-snug font-medium">
            {brief.recurrence_statement.statement}
          </p>
          <CitationRow citations={brief.recurrence_statement.citations} />
        </section>

        <section className="space-y-1.5 px-6 py-5">
          <div className="flex items-center gap-2">
            <AlertOctagon className="text-destructive size-4" />
            <p className="text-muted-foreground text-[0.7rem] font-semibold tracking-wide uppercase">
              The Pattern That Kills
            </p>
          </div>
          <Badge variant="destructive" className="mb-1">
            {brief.pattern_that_kills.causal_signature}
          </Badge>
          <p className="text-base leading-relaxed">{brief.pattern_that_kills.description}</p>
          <CitationRow citations={brief.pattern_that_kills.citations} />
        </section>

        <section className="space-y-1.5 px-6 py-5">
          <div className="flex items-center gap-2">
            <FileWarning className="text-warning size-4" />
            <p className="text-muted-foreground text-[0.7rem] font-semibold tracking-wide uppercase">
              The Compliance Illusion
            </p>
          </div>
          <p className="text-base leading-relaxed">{brief.compliance_illusion_finding.finding}</p>
          <CitationRow citations={brief.compliance_illusion_finding.citations} />
        </section>

        <section className="space-y-3 px-6 py-5">
          <div className="flex items-center gap-2">
            <ShieldAlert className="text-primary size-4" />
            <p className="text-muted-foreground text-[0.7rem] font-semibold tracking-wide uppercase">
              Act Now
            </p>
          </div>
          <ol className="space-y-3">
            {brief.action_lines.map((line, i) => (
              <li key={i} className="flex gap-3">
                <span className="bg-primary text-primary-foreground font-display flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold">
                  {i + 1}
                </span>
                <div>
                  <p className="font-medium">{line.action}</p>
                  <CitationRow citations={line.citations} />
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </Card>
  )
}

function BriefJobDialog({ job, onOpenChange }: { job: BriefJobOut | null; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={job !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="sr-only">Brief #{job?.id}</DialogTitle>
        </DialogHeader>
        {job && job.brief && <BriefDocument job={job} brief={job.brief} />}
        {job && !job.brief && (
          <p className="text-muted-foreground text-sm">This brief has no result yet.</p>
        )}
      </DialogContent>
    </Dialog>
  )
}

function JobRow({
  job,
  onOpenBrief,
  onRetry,
}: {
  job: BriefJobOut
  onOpenBrief: (job: BriefJobOut) => void
  onRetry: (id: number) => void
}) {
  const clickable = job.status === 'completed'
  return (
    <TableRow
      className={clickable ? 'cursor-pointer' : undefined}
      onClick={() => clickable && onOpenBrief(job)}
    >
      <TableCell className="align-top font-mono text-xs">{formatTime(job.created_at)}</TableCell>
      <TableCell className="align-top font-mono text-xs">
        #{job.report_ids.join(', #')}
      </TableCell>
      <TableCell className="max-w-56 truncate align-top">
        {job.top_causal_signature ?? '—'}
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
  onOpenBrief,
  onRetry,
}: {
  jobs: BriefJobOut[]
  emptyLabel: string
  onOpenBrief: (job: BriefJobOut) => void
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
          <TableHead>Reports</TableHead>
          <TableHead>Causal Signature</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <JobRow key={job.id} job={job} onOpenBrief={onOpenBrief} onRetry={onRetry} />
        ))}
      </TableBody>
    </Table>
  )
}

function BriefsPage() {
  const { data: jobs } = useBriefJobs()
  const retryJob = useRetryBriefJob()
  const [openJob, setOpenJob] = useState<BriefJobOut | null>(null)

  const runningJobs = (jobs ?? []).filter((j) => RUNNING_JOB_STATUSES.includes(j.status))
  const completedJobs = (jobs ?? []).filter((j) => !RUNNING_JOB_STATUSES.includes(j.status))

  return (
    <div className="mx-auto max-w-[900px] space-y-6 px-8 py-8">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Intelligence Briefs</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Select reports on the Incidents page and generate a brief — track its
          progress here, and revisit any completed brief below.
        </p>
      </div>

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
              emptyLabel="No briefs currently generating. Select reports on the Incidents page to start one."
              onOpenBrief={setOpenJob}
              onRetry={(id) => retryJob.mutate(id)}
            />
          </TabsContent>
          <TabsContent value="completed">
            <JobsTable
              jobs={completedJobs}
              emptyLabel="No completed briefs yet."
              onOpenBrief={setOpenJob}
              onRetry={(id) => retryJob.mutate(id)}
            />
          </TabsContent>
        </Tabs>
      </Card>

      <BriefJobDialog job={openJob} onOpenChange={(open) => !open && setOpenJob(null)} />
    </div>
  )
}
