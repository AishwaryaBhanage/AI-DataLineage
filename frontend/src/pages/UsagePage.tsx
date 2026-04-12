import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  Zap,
  Bot,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Database,
  HardDrive,
} from 'lucide-react'
import { Header } from '@/components/Header'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { api } from '@/lib/api'
import { formatMs } from '@/lib/utils'

export function UsagePage() {
  const { data, isLoading } = useQuery({
    queryKey: ['usage'],
    queryFn: () => api.usage(7),
    refetchInterval: 10000,
  })

  return (
    <>
      <Header
        title="Usage"
        subtitle="Your debug activity over the last 7 days"
      />

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-5xl mx-auto space-y-6">
          {isLoading && (
            <Card>
              <CardBody className="py-12 text-center text-slate-400">
                Loading stats...
              </CardBody>
            </Card>
          )}

          {data && (
            <>
              {/* ── What the numbers actually mean ─────────────────────── */}
              <Card className="bg-gradient-brand-soft border-brand-200">
                <CardBody className="!py-4">
                  <div className="text-[12px] text-brand-700 leading-relaxed">
                    <span className="font-bold">What these numbers mean: </span>
                    A <b>debug run</b> is one actual analysis you kicked off (fast or
                    agentic). <b>HTTP requests</b> include polling and health checks, so
                    they're higher than debug runs — that's expected.
                  </div>
                </CardBody>
              </Card>

              {/* ── Primary metrics: debug runs ────────────────────────── */}
              <div>
                <h2 className="text-[12px] font-bold text-slate-500 uppercase tracking-wider mb-3">
                  Debug runs (actual analyses)
                </h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <StatCard
                    icon={Activity}
                    label="Total runs"
                    value={data.debug_runs.total.toString()}
                    accent="brand"
                  />
                  <StatCard
                    icon={Zap}
                    label="Fast mode"
                    value={data.debug_runs.fast.toString()}
                    subtext={
                      data.debug_runs.fast > 0
                        ? `avg ${formatMs(data.debug_runs.fast_avg_ms)}`
                        : undefined
                    }
                    accent="amber"
                  />
                  <StatCard
                    icon={Bot}
                    label="Agentic mode"
                    value={data.debug_runs.agentic.toString()}
                    subtext={
                      data.debug_runs.agentic > 0
                        ? `avg ${formatMs(data.debug_runs.agentic_avg_ms)}`
                        : undefined
                    }
                    accent="violet"
                  />
                  <StatCard
                    icon={Database}
                    label="Unique models"
                    value={data.debug_runs.unique_models.toString()}
                    subtext="distinct problems"
                    accent="blue"
                  />
                </div>
              </div>

              {/* ── Outcomes ─────────────────────────────────────────── */}
              <div>
                <h2 className="text-[12px] font-bold text-slate-500 uppercase tracking-wider mb-3">
                  Outcomes
                </h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <StatCard
                    icon={CheckCircle2}
                    label="Completed"
                    value={data.debug_runs.completed.toString()}
                    accent="emerald"
                  />
                  <StatCard
                    icon={AlertCircle}
                    label="Failed"
                    value={data.debug_runs.failed.toString()}
                    accent="rose"
                  />
                  <StatCard
                    icon={Sparkles}
                    label="Claude calls"
                    value={data.llm_calls_estimated.toString()}
                    subtext="~estimated"
                    accent="violet"
                  />
                  <StatCard
                    icon={HardDrive}
                    label="Cache hits"
                    value={data.cache_hits.toString()}
                    subtext="saved LLM cost"
                    accent="emerald"
                  />
                </div>
              </div>

              {/* ── Quota card (if set) ───────────────────────────────── */}
              {data.daily_quota && data.daily_quota > 0 && (
                <Card>
                  <CardHeader
                    title="Daily quota"
                    subtitle={`${data.requests_today || 0} of ${data.daily_quota} used today`}
                  />
                  <CardBody>
                    <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-brand transition-all"
                        style={{
                          width: `${Math.min(
                            100,
                            ((data.requests_today || 0) / data.daily_quota) * 100,
                          )}%`,
                        }}
                      />
                    </div>
                    <div className="mt-2 text-[11px] text-slate-500">
                      {data.quota_remaining ?? 0} requests remaining today
                    </div>
                  </CardBody>
                </Card>
              )}

              {/* ── Raw HTTP stats (secondary) ─────────────────────────── */}
              <Card>
                <CardHeader
                  title="Raw HTTP requests"
                  subtitle={`${data.http_requests.total} total · avg ${formatMs(data.http_requests.avg_duration_ms)} · includes polling + health checks`}
                />
                <CardBody className="space-y-5">
                  {/* By endpoint */}
                  <div>
                    <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                      By endpoint
                    </div>
                    {Object.keys(data.http_requests.by_endpoint).length === 0 ? (
                      <div className="text-center text-slate-400 py-4 text-sm">
                        No activity yet
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {Object.entries(data.http_requests.by_endpoint)
                          .sort(([, a], [, b]) => b - a)
                          .map(([endpoint, count]) => {
                            const pct =
                              data.http_requests.total > 0
                                ? (count / data.http_requests.total) * 100
                                : 0
                            return (
                              <div key={endpoint}>
                                <div className="flex items-center justify-between mb-1">
                                  <span className="text-[12px] font-mono text-slate-700">
                                    {endpoint}
                                  </span>
                                  <span className="text-[12px] font-semibold text-slate-900">
                                    {count}
                                  </span>
                                </div>
                                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                  <div
                                    className="h-full bg-gradient-brand rounded-full transition-all"
                                    style={{ width: `${pct}%` }}
                                  />
                                </div>
                              </div>
                            )
                          })}
                      </div>
                    )}
                  </div>

                  {/* Status codes */}
                  <div>
                    <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                      Status codes
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(data.http_requests.by_status_code).map(
                        ([code, count]) => {
                          const n = Number(code)
                          const styles =
                            n >= 500
                              ? 'bg-rose-50 border-rose-200 text-rose-700'
                              : n >= 400
                              ? 'bg-amber-50 border-amber-200 text-amber-700'
                              : n === 202
                              ? 'bg-brand-50 border-brand-200 text-brand-700'
                              : 'bg-emerald-50 border-emerald-200 text-emerald-700'
                          return (
                            <div
                              key={code}
                              className={`px-3 py-1.5 rounded-lg border ${styles}`}
                            >
                              <div className="text-[10px] font-bold uppercase tracking-wider">
                                HTTP {code}
                              </div>
                              <div className="text-[14px] font-bold">{count}</div>
                            </div>
                          )
                        },
                      )}
                    </div>
                  </div>
                </CardBody>
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  subtext,
  accent,
}: {
  icon: typeof Activity
  label: string
  value: string
  subtext?: string
  accent: 'brand' | 'amber' | 'emerald' | 'rose' | 'violet' | 'blue'
}) {
  const colors = {
    brand: 'bg-brand-50 text-brand-600',
    amber: 'bg-amber-50 text-amber-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    rose: 'bg-rose-50 text-rose-600',
    violet: 'bg-violet-50 text-violet-600',
    blue: 'bg-blue-50 text-blue-600',
  }
  return (
    <Card>
      <CardBody className="flex items-center gap-3 !p-4">
        <div
          className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${colors[accent]}`}
        >
          <Icon className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
            {label}
          </div>
          <div className="text-[20px] font-bold text-slate-900 leading-tight">
            {value}
          </div>
          {subtext && (
            <div className="text-[10px] text-slate-500 mt-0.5">{subtext}</div>
          )}
        </div>
      </CardBody>
    </Card>
  )
}
