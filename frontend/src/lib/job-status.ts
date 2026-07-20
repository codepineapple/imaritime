import type { JobStatus } from '@/api/types'

const STAGE_LABELS: Record<string, string> = {
  pending: 'Queued',
  parsing: 'Parsing document',
  extracting: 'Extracting fields (LLM)',
  persisting: 'Saving to database',
  embedding: 'Generating embedding',
  analyzing: 'Analyzing selected reports',
  generating: 'Generating brief (LLM)',
  classifying: 'Classifying event (LLM)',
  mapping_trajectory: 'Mapping trajectory against historical reports',
  finding_barrier: 'Finding the barrier condition (LLM)',
  completed: 'Completed',
  failed: 'Failed',
}

export function stageLabel(status: JobStatus | string, stage: string | null): string {
  return STAGE_LABELS[stage ?? status] ?? stage ?? status
}

export function isRunningStatus(status: JobStatus | string): boolean {
  return status !== 'completed' && status !== 'failed'
}

export type JobBadgeVariant = 'secondary' | 'success' | 'destructive' | 'warning'

export function jobBadgeVariant(status: JobStatus | string): JobBadgeVariant {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'destructive'
  return 'secondary'
}
