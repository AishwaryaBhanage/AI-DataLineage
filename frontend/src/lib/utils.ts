import clsx, { type ClassValue } from 'clsx'

// Tiny className helper for conditional styles
export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

// ── dbt Cloud URL parsing ────────────────────────────────────────────────────
//
// dbt Cloud URLs follow a predictable shape:
//   https://cloud.getdbt.com/deploy/{account_id}/projects/{project_id}/jobs/{job_id}
//   https://cloud.getdbt.com/deploy/{account_id}/projects/{project_id}/runs/{run_id}
//   https://{subdomain}.cloud.getdbt.com/deploy/{account_id}/...
//
// This lets users paste a URL instead of manually entering account_id + job_id
// in separate fields.  Same pattern as Linear, GitHub, Vercel.

export interface ParsedDbtCloudUrl {
  accountId: string | null
  projectId: string | null
  jobId: string | null
  runId: string | null
  /** True if we could extract at least an account_id */
  isValid: boolean
  /** Best human-readable label: "Account X · Job Y" */
  summary: string
}

export function parseDbtCloudUrl(input: string): ParsedDbtCloudUrl {
  const result: ParsedDbtCloudUrl = {
    accountId: null,
    projectId: null,
    jobId: null,
    runId: null,
    isValid: false,
    summary: '',
  }

  if (!input || !input.trim()) return result

  const trimmed = input.trim()

  // Be lenient about what we accept — people paste with extra whitespace,
  // trailing slashes, query strings, and fragments.
  const accountMatch = trimmed.match(/\/deploy\/(\d+)/)
  if (accountMatch) result.accountId = accountMatch[1]

  const projectMatch = trimmed.match(/\/projects\/(\d+)/)
  if (projectMatch) result.projectId = projectMatch[1]

  const jobMatch = trimmed.match(/\/jobs\/(\d+)/)
  if (jobMatch) result.jobId = jobMatch[1]

  const runMatch = trimmed.match(/\/runs\/(\d+)/)
  if (runMatch) result.runId = runMatch[1]

  result.isValid = result.accountId !== null

  const parts: string[] = []
  if (result.accountId) parts.push(`Account ${result.accountId}`)
  if (result.projectId) parts.push(`Project ${result.projectId}`)
  if (result.jobId) parts.push(`Job ${result.jobId}`)
  if (result.runId) parts.push(`Run ${result.runId}`)
  result.summary = parts.join(' · ')

  return result
}

export function formatMs(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function confidenceColor(score: number): {
  bg: string
  text: string
  bar: string
  label: string
} {
  if (score >= 0.85)
    return {
      bg: 'bg-emerald-50',
      text: 'text-emerald-700',
      bar: 'bg-emerald-500',
      label: 'HIGH',
    }
  if (score >= 0.65)
    return {
      bg: 'bg-amber-50',
      text: 'text-amber-700',
      bar: 'bg-amber-500',
      label: 'MEDIUM',
    }
  return {
    bg: 'bg-rose-50',
    text: 'text-rose-700',
    bar: 'bg-rose-500',
    label: 'LOW',
  }
}

export function statusColor(status: string): string {
  switch (status) {
    case 'completed':
    case 'success':
    case 'ok':
      return 'bg-emerald-100 text-emerald-700'
    case 'running':
      return 'bg-blue-100 text-blue-700'
    case 'queued':
      return 'bg-slate-100 text-slate-700'
    case 'failed':
    case 'error':
      return 'bg-rose-100 text-rose-700'
    case 'cancelled':
      return 'bg-amber-100 text-amber-700'
    default:
      return 'bg-slate-100 text-slate-700'
  }
}
