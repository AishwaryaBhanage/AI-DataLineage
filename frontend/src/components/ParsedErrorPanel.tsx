import { AlertCircle, Hash, Tag, FileWarning } from 'lucide-react'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import type { ParsedError } from '@/lib/types'

interface Props {
  error: ParsedError
}

export function ParsedErrorPanel({ error }: Props) {
  if (!error.raw_text) {
    return null
  }

  return (
    <Card>
      <CardHeader
        title="Error Analysis"
        subtitle="Parsed from warehouse error message"
      />
      <CardBody className="space-y-4">
        {/* Error type badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-50 border border-rose-200">
          <AlertCircle className="w-4 h-4 text-rose-600" />
          <span className="text-[11px] font-bold text-rose-700 uppercase tracking-wider">
            {error.error_type.replace(/_/g, ' ')}
          </span>
        </div>

        {/* Raw error text */}
        <div className="bg-rose-50/50 border border-rose-100 rounded-lg p-3">
          <pre className="text-[12px] text-rose-900 whitespace-pre-wrap font-mono !bg-transparent !border-0 !p-0">
            {error.raw_text.slice(0, 400)}
          </pre>
        </div>

        {/* Metadata row */}
        <div className="grid grid-cols-3 gap-3">
          <Meta icon={Tag} label="Column" value={error.column} />
          <Meta icon={FileWarning} label="Model" value={error.model} />
          <Meta icon={Hash} label="Line" value={error.line_number?.toString()} />
        </div>

        {/* Candidates from warehouse */}
        {error.candidates && error.candidates.length > 0 && (
          <div>
            <h5 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              Warehouse suggestions
            </h5>
            <div className="flex flex-wrap gap-1.5">
              {error.candidates.map((c) => (
                <Badge key={c} variant="success">
                  {c}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function Meta({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof AlertCircle
  label: string
  value?: string | null
}) {
  return (
    <div className="bg-slate-50 rounded-lg p-2.5">
      <div className="flex items-center gap-1.5 text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
        <Icon className="w-3 h-3" />
        {label}
      </div>
      <div className="text-[13px] font-semibold text-slate-900 font-mono truncate">
        {value || '—'}
      </div>
    </div>
  )
}
