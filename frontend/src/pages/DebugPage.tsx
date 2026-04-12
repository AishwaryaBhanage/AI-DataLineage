import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Zap,
  Bot,
  FolderOpen,
  Cloud,
  Play,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Loader2,
  Database,
  Network,
  Link as LinkIcon,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'

import { Header } from '@/components/Header'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input, Label } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { LineageGraph } from '@/components/LineageGraph'
import { SqlDiff } from '@/components/SqlDiff'
import { ParsedSqlPanel } from '@/components/ParsedSqlPanel'
import { ParsedErrorPanel } from '@/components/ParsedErrorPanel'
import { AgenticResultPanel } from '@/components/AgenticResultPanel'
import { AnalyzerResultPanel } from '@/components/AnalyzerResultPanel'
import { FileDropZone } from '@/components/FileDropZone'

import { api, isAgenticAccepted, ApiError } from '@/lib/api'
import { useSettings, useDebugState } from '@/lib/store'
import type {
  ArtifactSource,
  DebugMode,
  DebugRequest,
  FastDebugResponse,
  Job,
} from '@/lib/types'
import { cn, formatMs, parseDbtCloudUrl } from '@/lib/utils'

export function DebugPage() {
  const { apiKey, manifestPath, runResultsPath } = useSettings()

  const [mode, setMode] = useState<DebugMode>('fast')
  const [source, setSource] = useState<ArtifactSource>('local')
  const [modelName, setModelName] = useState('')
  const [showAdvancedLocal, setShowAdvancedLocal] = useState(false)
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false)

  // Local file upload state
  const [manifestFile, setManifestFile] = useState<File | null>(null)
  const [runResultsFile, setRunResultsFile] = useState<File | null>(null)
  // After upload, these hold the temp paths the backend saved files to
  const [uploadedManifestPath, setUploadedManifestPath] = useState<string | null>(null)
  const [uploadedRunResultsPath, setUploadedRunResultsPath] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)

  // dbt Cloud fields
  const [cloudToken, setCloudToken] = useState('')
  const [cloudUrl, setCloudUrl] = useState('')
  const [cloudAccountId, setCloudAccountId] = useState('')
  const [cloudRunId, setCloudRunId] = useState('')
  const [cloudJobId, setCloudJobId] = useState('')
  const [showAdvancedCloud, setShowAdvancedCloud] = useState(false)

  // Parse the URL whenever it changes and auto-populate the ID fields.
  // Power users who toggle Advanced can still override these manually.
  const parsedCloudUrl = parseDbtCloudUrl(cloudUrl)
  // Use parsed values unless the user has manually overridden them
  const effectiveAccountId = cloudAccountId || parsedCloudUrl.accountId || ''
  const effectiveJobId = cloudJobId || parsedCloudUrl.jobId || ''
  const effectiveRunId = cloudRunId || parsedCloudUrl.runId || ''

  // State lives in Zustand (not local useState) so results survive
  // page navigation and browser refreshes.
  const result = useDebugState((s) => s.result)
  const agenticJob = useDebugState((s) => s.agenticJob)
  const pollingJobId = useDebugState((s) => s.pollingJobId)
  const setResult = useDebugState((s) => s.setResult)
  const setAgenticJob = useDebugState((s) => s.setAgenticJob)
  const setPollingJobId = useDebugState((s) => s.setPollingJobId)

  // Poll the job endpoint every 2s when an agentic job is running
  const { data: polledJob } = useQuery({
    queryKey: ['job', pollingJobId],
    queryFn: () => api.getJob(pollingJobId!),
    enabled: !!pollingJobId,
    refetchInterval: (query) => {
      const job = query.state.data as Job | undefined
      if (!job) return 2000
      if (job.status === 'completed' || job.status === 'failed') return false
      return 2000
    },
  })

  // Handle polled job completion — store the Job; AgenticResultPanel renders it
  if (polledJob && pollingJobId) {
    if (polledJob.status === 'completed') {
      if (agenticJob?.id !== polledJob.id) {
        setAgenticJob(polledJob)
        setResult(null)
        setPollingJobId(null)
        toast.success('Agent analysis complete')
      }
    } else if (polledJob.status === 'failed') {
      toast.error(`Job failed: ${polledJob.error || 'Unknown error'}`)
      setPollingJobId(null)
    }
  }

  const mutation = useMutation({
    mutationFn: async (req: DebugRequest) => api.debug(req),
    onSuccess: (data) => {
      if (isAgenticAccepted(data)) {
        setPollingJobId(data.job_id)
        setResult(null)
        setAgenticJob(null)
        toast.info(`Deep analysis queued: ${data.job_id.slice(0, 14)}...`, {
          description: 'Agent is investigating...',
        })
      } else {
        setResult(data)
        setAgenticJob(null)
        if (data.cached) {
          toast.success('Result from cache', { description: 'Same input within 1h' })
        } else {
          toast.success('Analysis complete')
        }
      }
    },
    onError: (err: ApiError) => {
      toast.error('Request failed', { description: err.message })
    },
  })

  const onSubmit = async () => {
    if (!apiKey) {
      toast.error('No API key set', {
        description: 'Go to Settings to configure',
      })
      return
    }

    const req: DebugRequest = {
      source,
      mode,
      model_name: modelName || undefined,
      use_llm: true,
    }

    if (source === 'local') {
      // Priority 1: if user picked a file, upload it first
      if (manifestFile) {
        setIsUploading(true)
        try {
          const resp = await api.uploadArtifacts(
            manifestFile,
            runResultsFile || undefined,
          )
          setUploadedManifestPath(resp.manifest_path)
          setUploadedRunResultsPath(resp.run_results_path || null)
          req.manifest_path = resp.manifest_path
          req.run_results_path = resp.run_results_path || ''
          toast.success('Files uploaded', {
            description: `${(resp.bytes.manifest / 1024).toFixed(1)} KB manifest`,
          })
        } catch (err: any) {
          toast.error('Upload failed', { description: err.message })
          setIsUploading(false)
          return
        }
        setIsUploading(false)
      }
      // Priority 2: if files were uploaded in a previous session, reuse them
      else if (uploadedManifestPath) {
        req.manifest_path = uploadedManifestPath
        req.run_results_path = uploadedRunResultsPath || ''
      }
      // Priority 3: fall back to paths (dev workflow)
      else {
        req.manifest_path = manifestPath
        req.run_results_path = runResultsPath
      }
    } else {
      // dbt Cloud: use effective values (parsed from URL, overridable via Advanced)
      if (!cloudToken) {
        toast.error('dbt Cloud API token is required')
        return
      }
      if (!effectiveAccountId) {
        toast.error('Could not detect account ID from URL', {
          description: 'Paste a dbt Cloud URL or fill in Advanced fields',
        })
        return
      }
      if (!effectiveJobId && !effectiveRunId) {
        toast.error('Paste a job or run URL', {
          description: 'URL must contain /jobs/{id} or /runs/{id}',
        })
        return
      }
      req.dbt_cloud_token = cloudToken
      req.dbt_cloud_account_id = effectiveAccountId
      if (effectiveRunId) req.dbt_cloud_run_id = effectiveRunId
      if (effectiveJobId) req.dbt_cloud_job_id = effectiveJobId
    }

    setResult(null)
    setAgenticJob(null)
    setPollingJobId(null)
    mutation.mutate(req)
  }

  const isLoading = mutation.isPending || isUploading || !!pollingJobId

  return (
    <>
      <Header
        title="Debug"
        subtitle="Analyze broken dbt models with AI-powered root cause detection"
      />

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* ── Input section ──────────────────────────────────────── */}
          <Card>
            <CardBody className="space-y-5">
              {/* Mode selector */}
              <div>
                <Label>Analysis mode</Label>
                <div className="grid grid-cols-2 gap-3">
                  <ModeCard
                    active={mode === 'fast'}
                    icon={Zap}
                    title="Analyze"
                    description="Single LLM call with structured evidence, ~4s"
                    onClick={() => setMode('fast')}
                  />
                  <ModeCard
                    active={mode === 'agentic'}
                    icon={Bot}
                    title="Deep analysis"
                    description="Multi-step ReAct agent, ~20-30s, use for complex cases"
                    onClick={() => setMode('agentic')}
                  />
                </div>
              </div>

              {/* Source selector */}
              <div>
                <Label>Artifact source</Label>
                <div className="grid grid-cols-2 gap-3">
                  <ModeCard
                    active={source === 'local'}
                    icon={FolderOpen}
                    title="Upload files"
                    description="Drag & drop manifest.json"
                    onClick={() => setSource('local')}
                  />
                  <ModeCard
                    active={source === 'cloud'}
                    icon={Cloud}
                    title="dbt Cloud"
                    description="Fetch from dbt Cloud API"
                    onClick={() => setSource('cloud')}
                  />
                </div>
              </div>

              {/* Source-specific inputs */}
              {source === 'local' ? (
                <div className="space-y-4">
                  {/* Primary: drag-drop file upload */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <FileDropZone
                      label="Manifest.json"
                      hint="target/manifest.json from your dbt project"
                      file={manifestFile}
                      onFileSelect={(f) => {
                        setManifestFile(f)
                        // Clear any previous upload when user picks new file
                        setUploadedManifestPath(null)
                        setUploadedRunResultsPath(null)
                      }}
                      uploaded={!!uploadedManifestPath && !!manifestFile}
                    />
                    <FileDropZone
                      label="Run_results.json (optional)"
                      hint="target/run_results.json — needed to auto-detect failures"
                      file={runResultsFile}
                      onFileSelect={(f) => {
                        setRunResultsFile(f)
                        setUploadedRunResultsPath(null)
                      }}
                      uploaded={!!uploadedRunResultsPath && !!runResultsFile}
                    />
                  </div>

                  {/* Advanced: server paths (for dev mode) */}
                  <div>
                    <button
                      type="button"
                      onClick={() => setShowAdvancedLocal(!showAdvancedLocal)}
                      className="flex items-center gap-1.5 text-[12px] font-semibold text-slate-600 hover:text-slate-900"
                    >
                      {showAdvancedLocal ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                      Advanced — use server paths instead of uploading
                    </button>
                    {showAdvancedLocal && (
                      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 pl-5 border-l-2 border-slate-100">
                        <div>
                          <Label>Manifest path</Label>
                          <Input
                            value={manifestPath}
                            onChange={(e) =>
                              useSettings.setState({ manifestPath: e.target.value })
                            }
                            placeholder="dbt_demo/target/manifest.json"
                          />
                          <p className="mt-1 text-[11px] text-slate-500">
                            Path on the backend machine — only works in local dev
                          </p>
                        </div>
                        <div>
                          <Label>Run results path (optional)</Label>
                          <Input
                            value={runResultsPath}
                            onChange={(e) =>
                              useSettings.setState({ runResultsPath: e.target.value })
                            }
                            placeholder="dbt_demo/target/run_results.json"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Primary: paste a dbt Cloud URL */}
                  <div>
                    <Label>dbt Cloud URL</Label>
                    <div className="relative">
                      <LinkIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                      <Input
                        className="pl-9 font-mono text-[13px]"
                        value={cloudUrl}
                        onChange={(e) => setCloudUrl(e.target.value)}
                        placeholder="https://cloud.getdbt.com/deploy/12345/projects/.../jobs/67890"
                      />
                    </div>
                    <p className="mt-1.5 text-[11px] text-slate-500">
                      Paste any job or run URL from your dbt Cloud browser tab.
                      We'll extract the IDs automatically.
                    </p>

                    {/* Extracted values preview */}
                    {cloudUrl && (
                      <div className="mt-2.5">
                        {parsedCloudUrl.isValid ? (
                          <div className="flex items-center gap-2 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                            <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                            <span className="font-semibold">Detected:</span>
                            <span className="font-mono">{parsedCloudUrl.summary}</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                            <span>That doesn't look like a dbt Cloud URL. Paste a full URL or fill in Advanced fields below.</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* API token */}
                  <div>
                    <Label>dbt Cloud API Token</Label>
                    <Input
                      type="password"
                      value={cloudToken}
                      onChange={(e) => setCloudToken(e.target.value)}
                      placeholder="dbt_..."
                    />
                    <p className="mt-1.5 text-[11px] text-slate-500">
                      Get this from{' '}
                      <span className="font-mono text-slate-600">
                        Profile → API Tokens → Create Token
                      </span>
                    </p>
                  </div>

                  {/* Advanced: manual ID override */}
                  <div className="pt-2">
                    <button
                      type="button"
                      onClick={() => setShowAdvancedCloud(!showAdvancedCloud)}
                      className="flex items-center gap-1.5 text-[12px] font-semibold text-slate-600 hover:text-slate-900"
                    >
                      {showAdvancedCloud ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                      Advanced — enter IDs manually
                    </button>
                    {showAdvancedCloud && (
                      <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3 pl-5 border-l-2 border-slate-100">
                        <div>
                          <Label>Account ID</Label>
                          <Input
                            value={cloudAccountId}
                            onChange={(e) => setCloudAccountId(e.target.value)}
                            placeholder={parsedCloudUrl.accountId || '12345'}
                          />
                        </div>
                        <div>
                          <Label>Job ID</Label>
                          <Input
                            value={cloudJobId}
                            onChange={(e) => setCloudJobId(e.target.value)}
                            placeholder={parsedCloudUrl.jobId || '789'}
                          />
                        </div>
                        <div>
                          <Label>Run ID</Label>
                          <Input
                            value={cloudRunId}
                            onChange={(e) => setCloudRunId(e.target.value)}
                            placeholder={parsedCloudUrl.runId || '67890'}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Advanced options (collapsed by default) */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowAdvancedOptions(!showAdvancedOptions)}
                  className="flex items-center gap-1.5 text-[12px] font-semibold text-slate-600 hover:text-slate-900"
                >
                  {showAdvancedOptions ? (
                    <ChevronDown className="w-4 h-4" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                  Advanced options
                </button>
                {showAdvancedOptions && (
                  <div className="mt-3 pl-5 border-l-2 border-slate-100">
                    <Label>Model to debug (override auto-detect)</Label>
                    <Input
                      value={modelName}
                      onChange={(e) => setModelName(e.target.value)}
                      placeholder="e.g. customer_revenue"
                    />
                    <p className="mt-1 text-[11px] text-slate-500">
                      Leave empty to auto-detect the first failed model from run_results.json.
                      Set this to analyze a specific model (useful when you have multiple failures).
                    </p>
                  </div>
                )}
              </div>

              {/* Submit */}
              <Button
                onClick={onSubmit}
                disabled={isLoading}
                size="lg"
                className="w-full"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {isUploading
                      ? 'Uploading...'
                      : pollingJobId
                      ? 'Agent thinking...'
                      : 'Analyzing...'}
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" />
                    {mode === 'fast' ? 'Run analysis' : 'Start agent'}
                  </>
                )}
              </Button>
            </CardBody>
          </Card>

          {/* ── Agentic polling UI ─────────────────────────────────── */}
          {pollingJobId && polledJob && polledJob.status !== 'completed' && (
            <Card className="border-brand-200 bg-brand-50/40">
              <CardBody>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-brand-100 flex items-center justify-center flex-shrink-0">
                    <Sparkles className="w-5 h-5 text-brand-600 animate-pulse" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[14px] font-semibold text-slate-900">
                      Agent is investigating
                    </div>
                    <div className="text-[12px] text-slate-600 mt-0.5">
                      Claude is autonomously calling tools to debug this failure. Status:{' '}
                      <span className="font-semibold text-brand-700">
                        {polledJob.status}
                      </span>
                    </div>
                  </div>
                  <Badge variant="info">Job {pollingJobId.slice(0, 14)}</Badge>
                </div>
              </CardBody>
            </Card>
          )}

          {/* ── Results ────────────────────────────────────────────── */}
          {result && (
            <>
              <StatusBanner result={result} />
              <StatsRow result={result} />

              {/* Parsed SQL + Error side by side */}
              {(result.parsed_sql || result.parsed_error) && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {result.parsed_sql && (
                    <ParsedSqlPanel
                      parsed={result.parsed_sql}
                      error={result.parsed_error}
                    />
                  )}
                  {result.parsed_error && result.parsed_error.raw_text && (
                    <ParsedErrorPanel error={result.parsed_error} />
                  )}
                </div>
              )}

              {/* Lineage */}
              {result.lineage.nodes.length > 0 && (
                <Card>
                  <CardHeader
                    title="Lineage graph"
                    subtitle={`${result.lineage.nodes.length} models · ${result.lineage.edges.length} edges`}
                    action={
                      <div className="flex items-center gap-2 text-[11px] font-semibold">
                        <LegendDot color="bg-violet-400" label="Upstream" />
                        <LegendDot
                          color={result.query_is_valid ? 'bg-emerald-400' : 'bg-rose-400'}
                          label={result.query_is_valid ? 'Fixed' : 'Broken'}
                        />
                      </div>
                    }
                  />
                  <CardBody>
                    <LineageGraph
                      lineage={result.lineage}
                      brokenModel={result.broken_model}
                      queryIsValid={result.query_is_valid}
                    />
                  </CardBody>
                </Card>
              )}

              {/* LLM analyzer result (the hero of the fast mode flow) */}
              {result.analyzer_result && (
                <AnalyzerResultPanel result={result.analyzer_result} />
              )}

              {/* SQL diff — show original vs corrected */}
              {result.raw_sql &&
                (result.analyzer_result?.corrected_sql || result.corrected_sql) && (
                  <Card>
                    <CardHeader
                      title="Corrected SQL"
                      subtitle={`Side-by-side comparison${
                        result.file_path ? ` · ${result.file_path}` : ''
                      }`}
                    />
                    <CardBody>
                      <SqlDiff
                        original={result.raw_sql}
                        corrected={
                          result.analyzer_result?.corrected_sql ||
                          result.corrected_sql ||
                          ''
                        }
                      />
                    </CardBody>
                  </Card>
                )}
            </>
          )}

          {/* ── Agentic job result ─────────────────────────────────── */}
          {agenticJob && (
            <AgenticResultPanel
              job={agenticJob}
              rawSql={(agenticJob.result as any)?.raw_sql || ''}
            />
          )}
        </div>
      </div>
    </>
  )
}

// ── Subcomponents ────────────────────────────────────────────────────────────

interface ModeCardProps {
  active: boolean
  icon: typeof Zap
  title: string
  description: string
  onClick: () => void
}

function ModeCard({ active, icon: Icon, title, description, onClick }: ModeCardProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'text-left px-4 py-3 rounded-xl border-2 transition-all',
        active
          ? 'border-brand-500 bg-brand-50 shadow-sm'
          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50',
      )}
    >
      <div className="flex items-center gap-2.5">
        <div
          className={cn(
            'w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0',
            active ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-600',
          )}
        >
          <Icon className="w-4 h-4" />
        </div>
        <div className="min-w-0">
          <div
            className={cn(
              'text-[13px] font-semibold',
              active ? 'text-brand-700' : 'text-slate-900',
            )}
          >
            {title}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">{description}</div>
        </div>
      </div>
    </button>
  )
}

function StatusBanner({ result }: { result: FastDebugResponse }) {
  if (result.query_is_valid) {
    return (
      <Card className="border-emerald-200 bg-gradient-to-br from-emerald-50 to-emerald-50/30">
        <CardBody>
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-emerald-100 flex items-center justify-center">
              <CheckCircle2 className="w-6 h-6 text-emerald-600" />
            </div>
            <div>
              <div className="text-[11px] font-bold text-emerald-700 uppercase tracking-wider">
                Query is valid
              </div>
              <div className="text-[16px] font-bold text-slate-900 mt-0.5">
                No issues found — SQL looks correct
              </div>
              <div className="text-[12px] text-emerald-700 mt-1">
                All columns exist upstream. The error may be from a previous run.
              </div>
            </div>
          </div>
        </CardBody>
      </Card>
    )
  }
  return (
    <Card className="border-rose-200 bg-gradient-to-br from-rose-50 to-rose-50/30">
      <CardBody>
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-rose-100 flex items-center justify-center">
            <AlertCircle className="w-6 h-6 text-rose-600" />
          </div>
          <div>
            <div className="text-[11px] font-bold text-rose-700 uppercase tracking-wider">
              Pipeline failure detected
            </div>
            <div className="text-[16px] font-bold text-slate-900 mt-0.5">
              {result.broken_model}
            </div>
            <div className="text-[12px] text-rose-700 mt-1">
              Issues found — see analysis below
            </div>
          </div>
        </div>
      </CardBody>
    </Card>
  )
}

function StatsRow({ result }: { result: FastDebugResponse }) {
  const confidence = result.analyzer_result?.confidence_score ?? 0
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <StatCard
        icon={Database}
        label="Broken model"
        value={result.broken_model}
      />
      <StatCard
        icon={AlertCircle}
        label="Error type"
        value={result.parsed_error?.error_type.replace(/_/g, ' ') || 'N/A'}
      />
      <StatCard
        icon={Sparkles}
        label="Confidence"
        value={`${Math.round(confidence * 100)}%`}
      />
      <StatCard
        icon={Network}
        label="Lineage depth"
        value={result.lineage.nodes.length.toString()}
      />
    </div>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Database
  label: string
  value: string
}) {
  return (
    <Card className="hover:shadow-pop transition-shadow">
      <CardBody className="flex items-center gap-3 !p-4">
        <div className="w-10 h-10 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center flex-shrink-0">
          <Icon className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
            {label}
          </div>
          <div className="text-[14px] font-semibold text-slate-900 truncate">
            {value}
          </div>
        </div>
      </CardBody>
    </Card>
  )
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-slate-500">
      <span className={cn('w-2.5 h-2.5 rounded-full', color)} />
      {label}
    </span>
  )
}
