import { CheckCircle2, AlertCircle, Sparkles, Wrench } from 'lucide-react'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import type { AnalyzerResult } from '@/lib/types'

// Renders the primary diagnosis produced by llm_analyzer.py.
// This is the hero panel of a fast mode debug result.
interface Props {
  result: AnalyzerResult
}

export function AnalyzerResultPanel({ result }: Props) {
  const confidencePct = Math.round(result.confidence_score * 100)
  const tokens = result.tokens_used || {}
  const inputTokens = tokens.input_tokens ?? 0
  const outputTokens = tokens.output_tokens ?? 0
  const estimatedCost = (
    (inputTokens / 1_000_000) * 3 +
    (outputTokens / 1_000_000) * 15
  ).toFixed(4)

  return (
    <>
      {/* ── Hero card with gradient root cause ──────────────────────── */}
      <Card className="overflow-hidden">
        <CardHeader
          title="Root Cause Analysis"
          subtitle={`AI-powered diagnosis · ${inputTokens + outputTokens} tokens · ~$${estimatedCost}`}
          action={
            <Badge variant={confidencePct >= 85 ? 'success' : 'info'}>
              {confidencePct}% confidence
            </Badge>
          }
        />
        <CardBody className="space-y-4">
          {/* Root cause hero banner */}
          <div className="bg-gradient-brand rounded-xl p-5 shadow-brand relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
            <div className="relative">
              <div className="flex items-center gap-2 text-[10px] font-bold text-white/80 uppercase tracking-wider mb-2">
                <Sparkles className="w-3 h-3" />
                Root cause
              </div>
              <p className="text-[16px] font-semibold text-white leading-snug">
                {result.root_cause}
              </p>
            </div>
          </div>

          {/* Plain-English explanation */}
          {result.explanation && (
            <p className="text-[14px] text-slate-700 leading-relaxed">
              {result.explanation}
            </p>
          )}

          {/* Affected columns */}
          {result.affected_columns.length > 0 && (
            <div>
              <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                Affected columns
              </div>
              <div className="flex flex-wrap gap-1.5">
                {result.affected_columns.map((col) => (
                  <code
                    key={col}
                    className="px-2 py-1 rounded-md bg-slate-100 text-[12px] font-mono text-slate-800"
                  >
                    {col}
                  </code>
                ))}
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      {/* ── Validation checklist ─────────────────────────────────────── */}
      {result.validation_steps.length > 0 && (
        <Card>
          <CardHeader
            title="Validation checklist"
            subtitle="Steps to verify the fix before shipping"
          />
          <CardBody>
            <ul className="space-y-2">
              {result.validation_steps.map((step, i) => (
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

      {/* ── Alternative hypotheses ──────────────────────────────────── */}
      {result.hypotheses.length > 1 && (
        <Card>
          <CardHeader
            title="Alternative hypotheses"
            subtitle="Other possible causes ranked by likelihood"
          />
          <CardBody className="space-y-3">
            {result.hypotheses.map((h, i) => {
              const pct = Math.round(h.confidence * 100)
              const color =
                pct >= 85
                  ? 'bg-emerald-500'
                  : pct >= 65
                  ? 'bg-amber-500'
                  : 'bg-rose-500'
              return (
                <div
                  key={i}
                  className="bg-slate-50 rounded-lg p-3 border border-slate-100"
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      {i === 0 ? (
                        <Sparkles className="w-3.5 h-3.5 text-brand-600" />
                      ) : (
                        <AlertCircle className="w-3.5 h-3.5 text-slate-400" />
                      )}
                      <span className="text-[13px] font-semibold text-slate-900">
                        {h.cause}
                      </span>
                    </div>
                    <span className="text-[11px] font-bold text-slate-600">
                      {pct}%
                    </span>
                  </div>
                  <p className="text-[12px] text-slate-600 leading-relaxed mb-2">
                    {h.description}
                  </p>
                  <div className="h-1 bg-slate-200 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${color} rounded-full`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </CardBody>
        </Card>
      )}
    </>
  )
}
