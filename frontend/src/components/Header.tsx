import { useQuery } from '@tanstack/react-query'
import { Activity, AlertCircle, CheckCircle2 } from 'lucide-react'
import { api } from '@/lib/api'
import { useSettings } from '@/lib/store'
import { cn } from '@/lib/utils'

/**
 * Top bar. Shows:
 *   - The current page title (passed via prop)
 *   - Backend health indicator (pings /health every 30s)
 *   - Current API key status
 */
interface HeaderProps {
  title: string
  subtitle?: string
}

export function Header({ title, subtitle }: HeaderProps) {
  const apiKey = useSettings((s) => s.apiKey)

  const { data: health, isError } = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: false,
  })

  let statusColor = 'bg-slate-400'
  let statusLabel = 'Checking'
  let StatusIcon = Activity

  if (isError) {
    statusColor = 'bg-rose-500'
    statusLabel = 'Offline'
    StatusIcon = AlertCircle
  } else if (health) {
    if (health.status === 'ok') {
      statusColor = 'bg-emerald-500'
      statusLabel = 'Online'
      StatusIcon = CheckCircle2
    } else {
      statusColor = 'bg-amber-500'
      statusLabel = 'Degraded'
      StatusIcon = AlertCircle
    }
  }

  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 flex-shrink-0">
      <div>
        <h1 className="text-[18px] font-bold text-slate-900 leading-none">
          {title}
        </h1>
        {subtitle && (
          <p className="text-[13px] text-slate-500 mt-1">{subtitle}</p>
        )}
      </div>

      <div className="flex items-center gap-3">
        {/* API key badge */}
        <div
          className={cn(
            'px-3 py-1.5 rounded-full text-[11px] font-semibold uppercase tracking-wide',
            apiKey
              ? 'bg-slate-100 text-slate-700'
              : 'bg-amber-50 text-amber-700 border border-amber-200',
          )}
        >
          {apiKey ? `Key: ${apiKey.slice(0, 10)}...` : 'No API key'}
        </div>

        {/* Health indicator */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-50 border border-slate-200">
          <div className="relative">
            <div className={cn('w-2 h-2 rounded-full', statusColor)} />
            {statusLabel === 'Online' && (
              <div
                className={cn(
                  'absolute inset-0 w-2 h-2 rounded-full animate-ping',
                  statusColor,
                  'opacity-60',
                )}
              />
            )}
          </div>
          <span className="text-[11px] font-semibold text-slate-600 uppercase tracking-wide">
            {statusLabel}
          </span>
          <StatusIcon className="w-3.5 h-3.5 text-slate-400" />
        </div>
      </div>
    </header>
  )
}
