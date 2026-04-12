import { CheckCircle2, Wrench, ArrowRight } from 'lucide-react'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { SqlDiff } from '@/components/SqlDiff'
import type { Job, AgenticDiagnosis } from '@/lib/types'
import { formatMs } from '@/lib/utils'

// Pretty labels for the 7 tools the agent can call.
// Keeps the timeline readable when Claude's raw tool names get shown.
const TOOL_LABELS: Record<string, { label: string; desc: string }> = {
  ingest_dbt_artifacts: {
    label: 'Ingest artifacts',
    desc: 'Loaded manifest.json and run_results.json',
  },
  analyze_sql: {
    label: 'Analyze SQL',
    desc: 'Parsed broken SQL with sqlglot',
  },
  analyze_error: {
    label: 'Analyze error',
    desc: 'Extracted error type and candidate columns',
  },
  get_lineage: {
    label: 'Build lineage',
    desc: 'Reconstructed model dependency DAG',
  },
  run_rule_engine: {
    label: 'Run rule engine',
    desc: 'Deterministic root-cause check',
  },
  get_model_sql: {
    label: 'Inspect upstream SQL',
    desc: 'Fetched upstream model source code',
  },
  fetch_dbt_cloud_artifacts: {
    label: 'Fetch from dbt Cloud',
    desc: 'Downloaded artifacts from dbt Cloud API',
  },
}

interface Props {
  job: Job
  rawSql?: string
}

/**
 * Find a balanced JSON object inside a blob of text.
 *
 * Claude's final ReAct message sometimes looks like:
 *   "Now I have all the evidence. The diagnosis is:\n\n{...}"
 *
 * A regex can fail on nested braces, so walk character-by-character.
 */
function findJsonBlock(text: string): string | null {
  let depth = 0
  let start: number | null = null
  let inString = false
  let escape = false

  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (escape) {
      escape = false
      continue
    }
    if (ch === '\\') {
      escape = true
      continue
    }
    if (ch === '"') {
      inString = !inString
      continue
    }
    if (inString) continue
    if (ch === '{') {
      if (depth === 0) start = i
      depth++
    } else if (ch === '}') {
      if (depth > 0) {
        depth--
        if (depth === 0 && start !== null) {
          return text.slice(start, i + 1)
        }
      }
    }
  }
  return null
}

/**
 * Coerce diagnosis from either an object or a messy string into a
 * typed AgenticDiagnosis. Returns null if nothing parseable is found.
 */
function coerceDiagnosis(raw: unknown): AgenticDiagnosis | null {
  if (typeof raw === 'object' && raw !== null) {
    return raw as AgenticDiagnosis
  }
  if (typeof raw === 'string') {
    // 1. Try parsing the whole string as JSON
    try {
      return JSON.parse(raw) as AgenticDiagnosis
    } catch {}
    // 2. Strip markdown fences and try again
    const stripped = raw
      .replace(/^```(?:json)?\s*/m, '')
      .replace(/\s*```\s*$/m, '')
      .trim()
    try {
      return JSON.parse(stripped) as AgenticDiagnosis
    } catch {}
    // 3. Find a balanced JSON block inside the text
    const block = findJsonBlock(raw)
    if (block) {
      try {
        return JSON.parse(block) as AgenticDiagnosis
      } catch {}
    }
  }
  return null
}

export function AgenticResultPanel({ job, rawSql }: Props) {
  // The job.result shape for agentic is:
  //   { mode: 'agentic', diagnosis: {...} | string, tools_used: string[], raw_sql: string }
  const result = job.result as
    | {
        diagnosis: AgenticDiagnosis | string
        tools_used?: string[]
        raw_sql?: string
      }
    | null

  if (!result) return null

  // Try to get a structured diagnosis, even if backend returned a string
  const diagnosis = coerceDiagnosis(result.diagnosis)

  // If we still couldn't parse, keep the raw text as a fallback display
  const rawTextDiagnosis =
    diagnosis === null && typeof result.diagnosis === 'string'
      ? result.diagnosis
      : null

  const toolsUsed = result.tools_used || []
  const confidence = diagnosis?.confidence_score ?? 0
  const confidencePct = Math.round(confidence * 100)

  // Prefer raw_sql from the result itself, fall back to prop
  const effectiveRawSql = result.raw_sql || rawSql || ''

  return (
    <>
      {/* ── Root Cause hero card ─────────────────────────────────────── */}
      {diagnosis?.root_cause && (
        <Card className="overflow-hidden">
          <CardHeader
            title="Agent Diagnosis"
            subtitle={`Completed in ${formatMs(job.duration_ms)} · ${toolsUsed.length} tool calls`}
            action={
              <Badge variant="info">{confidencePct}% confidence</Badge>
            }
          />
          <CardBody className="space-y-4">
            <div className="bg-gradient-brand rounded-xl p-5 shadow-brand relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
              <div className="relative">
                <div className="text-[10px] font-bold text-white/80 uppercase tracking-wider mb-2">
                  Root cause
                </div>
                <p className="text-[16px] font-semibold text-white leading-snug">
                  {diagnosis.root_cause}
                </p>
              </div>
            </div>
            {diagnosis.explanation && (
              <p className="text-[14px] text-slate-700 leading-relaxed">
                {diagnosis.explanation}
              </p>
            )}
          </CardBody>
        </Card>
      )}

      {/* ── Fallback: if diagnosis is a plain string ─────────────────── */}
      {!diagnosis && rawTextDiagnosis && (
        <Card>
          <CardHeader
            title="Agent Diagnosis"
            subtitle={`Completed in ${formatMs(job.duration_ms)} · ${toolsUsed.length} tool calls`}
          />
          <CardBody>
            <pre className="whitespace-pre-wrap !bg-slate-50 !border-slate-200 text-[13px] text-slate-700">
              {rawTextDiagnosis.slice(0, 2000)}
            </pre>
          </CardBody>
        </Card>
      )}

      {/* ── Tool call timeline ───────────────────────────────────────── */}
      {toolsUsed.length > 0 && (
        <Card>
          <CardHeader
            title="Agent reasoning trace"
            subtitle="Tools Claude chose to call, in order"
          />
          <CardBody>
            <ol className="space-y-2">
              {toolsUsed.map((tool, i) => {
                const info = TOOL_LABELS[tool] || { label: tool, desc: '' }
                const isLast = i === toolsUsed.length - 1
                return (
                  <li key={i} className="flex items-center gap-3">
                    <div className="flex flex-col items-center">
                      <div className="w-8 h-8 rounded-full bg-gradient-brand text-white flex items-center justify-center text-[11px] font-bold shadow-sm flex-shrink-0">
                        {i + 1}
                      </div>
                      {!isLast && (
                        <div className="w-px h-4 bg-slate-200 mt-1" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0 bg-slate-50 rounded-lg px-4 py-2.5 border border-slate-100 mb-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-semibold text-slate-900">
                          {info.label}
                        </span>
                        <ArrowRight className="w-3 h-3 text-slate-400" />
                        <span className="text-[11px] font-mono text-slate-500">
                          {tool}
                        </span>
                      </div>
                      {info.desc && (
                        <div className="text-[11px] text-slate-500 mt-0.5">
                          {info.desc}
                        </div>
                      )}
                    </div>
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                  </li>
                )
              })}
            </ol>
          </CardBody>
        </Card>
      )}

      {/* ── Validation checklist ─────────────────────────────────────── */}
      {diagnosis?.validation_steps && diagnosis.validation_steps.length > 0 && (
        <Card>
          <CardHeader
            title="Validation checklist"
            subtitle="Steps to verify the fix"
          />
          <CardBody>
            <ul className="space-y-2">
              {diagnosis.validation_steps.map((step, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2.5 text-[13px] text-slate-700"
                >
                  <CheckCircle2 className="w-4 h-4 text-brand-600 flex-shrink-0 mt-0.5" />
                  {step}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}

      {/* ── Corrected SQL diff ───────────────────────────────────────── */}
      {diagnosis?.corrected_sql && (
        <Card>
          <CardHeader
            title="Corrected SQL"
            subtitle="Agent's proposed fix"
            action={
              <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-brand-600">
                <Wrench className="w-3.5 h-3.5" />
                Agent fix
              </span>
            }
          />
          <CardBody>
            <SqlDiff
              original={effectiveRawSql || '(original SQL not available)'}
              corrected={diagnosis.corrected_sql}
            />
          </CardBody>
        </Card>
      )}
    </>
  )
}
