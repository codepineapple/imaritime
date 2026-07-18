import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'

import { api } from '@/api/client'
import type {
  CreateBriefJobRequest,
  GroupByRequest,
  ReportFilterParams,
  ReportIdsRequest,
} from '@/api/types'
import { RUNNING_JOB_STATUSES } from '@/api/types'

/**
 * The brief-selection cap (`Settings.MAX_REPORTS_PER_BRIEF`) enforced by
 * the backend -- fetched once and treated as the single source of truth,
 * rather than duplicating the number in a frontend env var that could
 * silently drift from what the backend actually enforces.
 */
export function useConfig() {
  return useQuery({
    queryKey: ['config'],
    queryFn: () => api.config.get(),
    staleTime: Infinity, // this doesn't change at runtime; no need to ever refetch
  })
}

export function useReportsSearch(params: ReportFilterParams) {
  return useQuery({
    queryKey: ['reports', 'search', params],
    queryFn: () => api.reports.search(params),
    placeholderData: keepPreviousData,
  })
}

export function useReportStats(params: ReportFilterParams) {
  return useQuery({
    queryKey: ['reports', 'stats', params],
    queryFn: () => api.reports.stats(params),
    placeholderData: keepPreviousData,
  })
}

export function useReportDetail(id: number | null) {
  return useQuery({
    queryKey: ['reports', 'detail', id],
    queryFn: () => api.reports.detail(id as number),
    enabled: id !== null,
  })
}

export function useDeleteReport() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.reports.delete(id),
    onSuccess: () => {
      // Table/stats/groups/vocab can all reference the deleted report
      // (counts, sample_report_ids, vocab usage counts) -- invalidate
      // broadly rather than trying to patch each cache individually.
      queryClient.invalidateQueries({ queryKey: ['reports'] })
      queryClient.invalidateQueries({ queryKey: ['groups'] })
      queryClient.invalidateQueries({ queryKey: ['vocab'] })
    },
  })
}

export function useBulkDeleteReports() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: ReportIdsRequest) => api.reports.bulkDelete(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reports'] })
      queryClient.invalidateQueries({ queryKey: ['groups'] })
      queryClient.invalidateQueries({ queryKey: ['vocab'] })
    },
  })
}

/**
 * Exports reports as a `.jsonl` file and triggers a browser download.
 * Not cache-invalidating (export doesn't change any data), so this is a
 * plain mutation used only for its pending/error state on the Export button.
 */
export function useExportReports() {
  return useMutation({
    mutationFn: async (params: ReportIdsRequest) => {
      const blob = await api.reports.exportJsonl(params)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `reports_export_${new Date().toISOString().slice(0, 10)}.jsonl`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    },
  })
}

export function useSearchSuggestions(query: string) {
  return useQuery({
    queryKey: ['reports', 'suggestions', query],
    queryFn: () => api.reports.suggestions(query),
    enabled: query.trim().length >= 2,
  })
}

export function useDistinctValues(column: string) {
  return useQuery({
    queryKey: ['reports', 'distinct', column],
    queryFn: () => api.reports.distinct(column),
    staleTime: 5 * 60 * 1000,
  })
}

export function useGroups(params: GroupByRequest) {
  return useQuery({
    queryKey: ['groups', params],
    queryFn: () => api.groups.list(params),
    placeholderData: keepPreviousData,
  })
}

export function useVocab() {
  return useQuery({
    queryKey: ['vocab'],
    queryFn: () => api.vocab.all(),
    staleTime: 5 * 60 * 1000,
  })
}

export function useUploadDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => api.uploads.document(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

export function useUploadJsonl() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => api.uploads.jsonl(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reports'] })
      queryClient.invalidateQueries({ queryKey: ['groups'] })
      queryClient.invalidateQueries({ queryKey: ['vocab'] })
    },
  })
}

/**
 * Polls the full ingestion jobs list. Refetches frequently while any job
 * is still running, and stops (relatively) once everything has settled
 * into a terminal state -- powers the upload modal's Running/Completed tabs.
 */
export function useIngestionJobs() {
  return useQuery({
    queryKey: ['jobs', 'list'],
    queryFn: () => api.jobs.list(),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? []
      const anyRunning = jobs.some((j) => RUNNING_JOB_STATUSES.includes(j.status))
      return anyRunning ? 2000 : 8000
    },
  })
}

export function useRetryIngestionJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: number) => api.jobs.retry(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

/** Polls the full brief jobs list -- powers the Briefs page's Running/Completed tabs. */
export function useBriefJobs() {
  return useQuery({
    queryKey: ['briefs', 'list'],
    queryFn: () => api.briefs.list(),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? []
      const anyRunning = jobs.some((j) => RUNNING_JOB_STATUSES.includes(j.status))
      return anyRunning ? 2000 : 8000
    },
  })
}

export function useCreateBriefJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: CreateBriefJobRequest) => api.briefs.create(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['briefs'] })
    },
  })
}

export function useRetryBriefJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: number) => api.briefs.retry(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['briefs'] })
    },
  })
}
