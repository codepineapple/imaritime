import type {
  BriefJobOut,
  BulkDeleteResult,
  CausalGroup,
  CreateBriefJobRequest,
  FrontendConfig,
  GroupByRequest,
  IngestionJobOut,
  JsonlIngestResult,
  PaginatedReports,
  ReportDetail,
  ReportFilterParams,
  ReportIdsRequest,
  SearchSuggestion,
  StatsOut,
  UploadAcceptedResponse,
} from '@/api/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body && !(init.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...init?.headers,
    },
  })

  if (!res.ok) {
    let detail: unknown
    try {
      const body = await res.json()
      detail = body?.detail ?? body
    } catch {
      detail = res.statusText
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' })
}

function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' })
}

async function postForBlob(path: string, body: unknown): Promise<Blob> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail: unknown
    try {
      detail = (await res.json())?.detail
    } catch {
      detail = res.statusText
    }
    throw new ApiError(res.status, detail)
  }
  return res.blob()
}

export const api = {
  health: () => get<{ status: string; app: string; environment: string }>('/health'),

  config: {
    get: () => get<FrontendConfig>('/config'),
  },

  reports: {
    // Hybrid keyword + semantic search lives behind this one endpoint --
    // when a free-text ("all fields") token is present, the backend also
    // runs a semantic similarity search and labels each result's match_type.
    search: (params: ReportFilterParams) => post<PaginatedReports>('/reports/search', params),
    stats: (params: ReportFilterParams) => post<StatsOut>('/reports/stats', params),
    detail: (id: number) => get<ReportDetail>(`/reports/${id}`),
    suggestions: (q: string) =>
      get<SearchSuggestion[]>(`/reports/suggestions?q=${encodeURIComponent(q)}`),
    distinct: (column: string) => get<string[]>(`/reports/distinct/${column}`),
    delete: (id: number) => del<void>(`/reports/${id}`),
    bulkDelete: (params: ReportIdsRequest) => post<BulkDeleteResult>('/reports/bulk-delete', params),
    exportJsonl: (params: ReportIdsRequest) => postForBlob('/reports/export', params),
  },

  groups: {
    list: (params: GroupByRequest) => post<CausalGroup[]>('/groups', params),
  },

  briefs: {
    create: (params: CreateBriefJobRequest) => post<BriefJobOut>('/briefs', params),
    list: () => get<BriefJobOut[]>('/briefs'),
    get: (id: number) => get<BriefJobOut>(`/briefs/${id}`),
    retry: (id: number) => post<BriefJobOut>(`/briefs/${id}/retry`, {}),
  },

  vocab: {
    all: () => get<Record<string, string[]>>('/vocab'),
    field: (fieldName: string) => get<string[]>(`/vocab/${fieldName}`),
  },

  uploads: {
    document: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return request<UploadAcceptedResponse>('/uploads/documents', {
        method: 'POST',
        body: formData,
      })
    },
    jsonl: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return request<JsonlIngestResult>('/uploads/jsonl', { method: 'POST', body: formData })
    },
  },

  jobs: {
    list: () => get<IngestionJobOut[]>('/jobs'),
    get: (id: number) => get<IngestionJobOut>(`/jobs/${id}`),
    retry: (id: number) => post<IngestionJobOut>(`/jobs/${id}/retry`, {}),
  },
}
