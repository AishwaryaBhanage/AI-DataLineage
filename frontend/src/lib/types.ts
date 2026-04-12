// Mirror of app/api/schemas.py and the DB models.
// Keep this in sync when you change the backend response shapes.

export type DebugMode = 'fast' | 'agentic'
export type ArtifactSource = 'local' | 'cloud'

// ── Request ────────────────────────────────────────────────────────────────

export interface DebugRequest {
  source: ArtifactSource
  manifest_path?: string | null
  run_results_path?: string | null
  dbt_cloud_token?: string | null
  dbt_cloud_account_id?: string | null
  dbt_cloud_run_id?: string | null
  dbt_cloud_job_id?: string | null
  model_name?: string | null
  mode: DebugMode
  use_llm?: boolean
  sql?: string | null
  error_message?: string | null
}

// ── Health ─────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string
  version: string
  environment: string
  modes: string[]
  checks: Record<string, boolean>
}

// ── Domain types ───────────────────────────────────────────────────────────

export interface AnalyzerHypothesis {
  cause: string
  description: string
  confidence: number
}

export interface AnalyzerResult {
  root_cause: string
  explanation: string
  confidence_score: number
  corrected_sql: string
  validation_steps: string[]
  affected_columns: string[]
  query_is_valid: boolean
  hypotheses: AnalyzerHypothesis[]
  tokens_used: Record<string, number>
}

export interface ParsedSQL {
  tables: string[]
  columns: string[]
  joins: unknown[]
  filters: string[]
  ctes: string[]
  aggregations: string[]
  dbt_refs: string[]
  aliases: Record<string, string>
  group_by: string[]
}

export interface ParsedError {
  raw_text: string
  error_type: string
  column?: string | null
  relation?: string | null
  model?: string | null
  line_number?: number | null
  hint?: string | null
  candidates: string[]
}

export interface Lineage {
  nodes: string[]
  edges: { from: string; to: string }[]
  upstream: string[]
  downstream: string[]
  impacted: string[]
  paths_to_root: string[][]
}

// ── Fast mode response ─────────────────────────────────────────────────────

export interface FastDebugResponse {
  mode: 'fast'
  broken_model: string
  file_path: string
  raw_sql: string
  compiled_sql: string | null
  parsed_sql: ParsedSQL | null
  parsed_error: ParsedError | null
  lineage: Lineage
  lineage_ascii: string
  upstream_columns: Record<string, string[]>
  query_is_valid: boolean
  corrected_sql: string | null
  analyzer_result: AnalyzerResult | null
  errors: string[]
  job_id?: string
  cached?: boolean
}

// ── Agentic mode response (initial 202) ────────────────────────────────────

export interface AgenticAcceptedResponse {
  status: 'accepted'
  job_id: string
  mode: 'agentic'
  poll_url: string
  message: string
}

// ── Jobs ───────────────────────────────────────────────────────────────────

export type JobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface Job {
  id: string
  status: JobStatus
  mode: DebugMode
  broken_model: string | null
  result: unknown
  error: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
}

export interface JobsListResponse {
  count: number
  jobs: Job[]
}

// ── Usage ──────────────────────────────────────────────────────────────────

export interface DebugRunStats {
  total: number
  fast: number
  agentic: number
  completed: number
  failed: number
  unique_models: number
  fast_avg_ms: number
  agentic_avg_ms: number
}

export interface HttpRequestStats {
  total: number
  avg_duration_ms: number
  by_endpoint: Record<string, number>
  by_status_code: Record<string, number>
}

export interface UsageStats {
  api_key_prefix: string
  period_days: number
  debug_runs: DebugRunStats
  llm_calls_estimated: number
  cache_hits: number
  http_requests: HttpRequestStats
  // Legacy fields (still returned for backward compat)
  total_requests: number
  avg_duration_ms: number
  by_endpoint: Record<string, number>
  by_status_code: Record<string, number>
  daily_quota?: number
  requests_today?: number
  quota_remaining?: number
}

// ── Models ─────────────────────────────────────────────────────────────────

export interface ModelInfo {
  name: string
  file_path: string
  materialized: string
  upstream: string[]
  downstream: string[]
}

export interface ModelsResponse {
  project: string
  adapter: string
  total_models: number
  models: ModelInfo[]
}

// ── Agentic job result shape (inside Job.result) ───────────────────────────

export interface AgenticResult {
  mode: 'agentic'
  diagnosis: AgenticDiagnosis | string
  tools_used: string[]
  errors: string[]
}

export interface AgenticDiagnosis {
  root_cause?: string
  explanation?: string
  corrected_sql?: string | null
  confidence_score?: number
  validation_steps?: string[]
  tools_used?: string[]
}
