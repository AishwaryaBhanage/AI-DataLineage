import { useQuery } from '@tanstack/react-query'
import { Clock, Zap, Bot, ChevronRight } from 'lucide-react'
import { Header } from '@/components/Header'
import { Card, CardBody } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { api } from '@/lib/api'
import { formatMs, formatTime, statusColor, cn } from '@/lib/utils'
import type { Job } from '@/lib/types'

export function JobsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => api.listJobs(50),
    refetchInterval: 5000, // auto-refresh every 5s
  })

  return (
    <>
      <Header title="Jobs" subtitle="Debug run history" />

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-5xl mx-auto">
          {isLoading && <LoadingState />}
          {error && <ErrorState message={String(error)} />}
          {data && data.jobs.length === 0 && <EmptyState />}
          {data && data.jobs.length > 0 && (
            <Card>
              <CardBody className="!p-0">
                <div className="divide-y divide-slate-100">
                  {data.jobs.map((job) => (
                    <JobRow key={job.id} job={job} />
                  ))}
                </div>
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}

function JobRow({ job }: { job: Job }) {
  const Icon = job.mode === 'fast' ? Zap : Bot
  return (
    <div className="flex items-center gap-4 px-5 py-4 hover:bg-slate-50/50 transition-colors">
      <div
        className={cn(
          'w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0',
          job.mode === 'fast'
            ? 'bg-amber-50 text-amber-600'
            : 'bg-violet-50 text-violet-600',
        )}
      >
        <Icon className="w-5 h-5" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-mono text-[12px] font-semibold text-slate-700">
            {job.id}
          </span>
          <span
            className={cn(
              'px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider',
              statusColor(job.status),
            )}
          >
            {job.status}
          </span>
          {job.mode === 'agentic' && (
            <Badge variant="purple">agentic</Badge>
          )}
        </div>
        <div className="flex items-center gap-4 text-[11.5px] text-slate-500">
          <span>
            Model:{' '}
            <span className="font-semibold text-slate-700">
              {job.broken_model || '—'}
            </span>
          </span>
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatTime(job.created_at)}
          </span>
          <span>Duration: {formatMs(job.duration_ms)}</span>
        </div>
      </div>

      <ChevronRight className="w-4 h-4 text-slate-300 flex-shrink-0" />
    </div>
  )
}

function LoadingState() {
  return (
    <Card>
      <CardBody>
        <div className="flex items-center justify-center py-16 text-slate-400">
          Loading jobs...
        </div>
      </CardBody>
    </Card>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <Card className="border-rose-200 bg-rose-50/30">
      <CardBody>
        <div className="text-rose-700 text-sm">{message}</div>
      </CardBody>
    </Card>
  )
}

function EmptyState() {
  return (
    <Card>
      <CardBody className="py-16">
        <div className="text-center text-slate-400">
          <Clock className="w-10 h-10 mx-auto mb-3 opacity-50" />
          <p className="text-sm font-medium">No jobs yet</p>
          <p className="text-xs mt-1">
            Run a debug analysis to see history here
          </p>
        </div>
      </CardBody>
    </Card>
  )
}
