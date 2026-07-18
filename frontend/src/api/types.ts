// Mirrors app/schemas/report_schemas.py, brief_schemas.py, job_schemas.py

export interface FieldMetadata {
  field_name: string
  value: unknown
  status: string | null
  human_revision_status: string | null
  confidence: number | null
  reasoning: string | null
  supporting_quotes: string[]
  source_page_numbers: number[]
}

export type MatchType = 'keyword' | 'semantic' | 'both' | null

export interface ReportListItem {
  id: number
  incident_date: string | null
  incident_title: string | null
  incident_type: string | null
  location: string | null
  operation_type: string | null
  vessel_type: string | null
  casual_signature: string | null
  vessel_information: unknown
  injuries: number
  fatalities: number
  overall_confidence: number | null
  human_review_required: boolean
  source_filename: string | null
  ingested_at: string | null
  match_type: MatchType
  semantic_score: number | null
}

export interface ReportDetail extends ReportListItem {
  weather_conditions: unknown
  environmental_factors: unknown
  pollution: unknown
  property_damage: unknown
  equipment_involved: string[]
  sequence_of_events: string[]
  immediate_causes: string[]
  root_causes: string[]
  contributing_factors: string[]
  human_factors: string[]
  technical_failures: string[]
  regulatory_issues: string[]
  lessons_learned: string[]
  corrective_actions: string[]
  safety_recommendations: string[]
  keywords: string[]
  fields_requiring_review: string[]
  full_text: string | null
  field_metadata: FieldMetadata[]
}

export interface PaginatedReports {
  items: ReportListItem[]
  total: number
  page: number
  page_size: number
}

export interface StatsOut {
  total_reports: number
  total_injuries: number
  total_fatalities: number
  human_review_required: number
  avg_confidence: number | null
}

export interface SearchToken {
  field: string
  text: string
}

export interface ReportFilterParams {
  field_search_tokens?: SearchToken[]
  date_from?: string | null
  date_to?: string | null
  min_injuries?: number | null
  min_fatalities?: number | null
  confidence_min?: number | null
  confidence_max?: number | null
  human_review_required?: boolean | null
  has_data_in?: string[]
  operation_types?: string[]
  vessel_types?: string[]
  casual_signatures?: string[]
  page?: number
  page_size?: number
  sort_by?: string
  sort_dir?: 'asc' | 'desc'
}

export interface SearchSuggestion {
  field: string
  text: string
}

export interface CausalGroup {
  group_by_field: string
  value: string
  count: number
  total_injuries: number
  total_fatalities: number
  avg_confidence: number | null
  earliest_date: string | null
  latest_date: string | null
  sample_report_ids: number[]
}

export type GroupableField = 'operation_type' | 'vessel_type' | 'casual_signature'

export interface GroupByRequest extends ReportFilterParams {
  group_by: GroupableField
  limit?: number
}

export interface BriefCitation {
  report_id: number
  field_name: string
  page_numbers: number[]
}

export interface RecurrenceStatement {
  statement: string
  citations: BriefCitation[]
}

export interface PatternThatKills {
  causal_signature: string
  description: string
  citations: BriefCitation[]
}

export interface ComplianceIllusionFinding {
  finding: string
  citations: BriefCitation[]
}

export interface ActionLine {
  action: string
  citations: BriefCitation[]
}

export interface IntelligenceBrief {
  recurrence_statement: RecurrenceStatement
  pattern_that_kills: PatternThatKills
  compliance_illusion_finding: ComplianceIllusionFinding
  action_lines: ActionLine[]
}

//: Shared job lifecycle status across both ingestion and brief jobs.
export type JobStatus =
  | 'pending'
  | 'parsing'
  | 'extracting'
  | 'persisting'
  | 'embedding'
  | 'analyzing'
  | 'generating'
  | 'completed'
  | 'failed'

export const RUNNING_JOB_STATUSES: JobStatus[] = [
  'pending',
  'parsing',
  'extracting',
  'persisting',
  'embedding',
  'analyzing',
  'generating',
]

export interface CreateBriefJobRequest {
  report_ids: number[]
}

export interface BriefJobOut {
  id: number
  report_ids: number[]
  status: JobStatus
  stage: string | null
  error_message: string | null
  top_causal_signature: string | null
  most_representative_report_id: number | null
  brief: IntelligenceBrief | null
  created_at: string
  updated_at: string
}

export interface IngestionJobOut {
  id: number
  filename: string | null
  content_type: string | null
  status: JobStatus
  stage: string | null
  error_message: string | null
  report_id: number | null
  created_at: string
  updated_at: string
}

export interface UploadAcceptedResponse {
  job_id: number
  celery_task_id: string | null
  status: string
  filename: string | null
}

export interface JsonlIngestResult {
  total_records: number
  inserted: number
  duplicates: number
  failed: number
  errors: string[]
  embedded: number
}

export interface FrontendConfig {
  max_reports_per_brief: number
}

export interface ReportIdsRequest {
  report_ids: number[]
}

export interface BulkDeleteResult {
  deleted: number[]
  not_found: number[]
}
