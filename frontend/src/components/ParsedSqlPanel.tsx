import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import type { ParsedSQL, ParsedError } from '@/lib/types'

interface Props {
  parsed: ParsedSQL
  error: ParsedError | null
}

export function ParsedSqlPanel({ parsed, error }: Props) {
  const missingCol = error?.column

  return (
    <Card>
      <CardHeader
        title="Parsed SQL Structure"
        subtitle="Entities extracted by sqlglot"
      />
      <CardBody className="space-y-5">
        {/* Stat row */}
        <div className="flex flex-wrap gap-2">
          <Stat label="Tables" value={parsed.tables.length} />
          <Stat label="Columns" value={parsed.columns.length} />
          <Stat label="Aggregations" value={parsed.aggregations.length} />
          <Stat label="dbt refs" value={parsed.dbt_refs.length} />
          <Stat label="CTEs" value={parsed.ctes.length} />
        </div>

        {/* Tables */}
        {parsed.tables.length > 0 && (
          <div>
            <h5 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              Tables / refs
            </h5>
            <div className="flex flex-wrap gap-1.5">
              {parsed.tables.map((t) => (
                <Badge key={t} variant="info">
                  {t}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Columns with missing highlighted */}
        {parsed.columns.length > 0 && (
          <div>
            <h5 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              Columns used
            </h5>
            <div className="flex flex-wrap gap-1.5">
              {parsed.columns.map((c) => (
                <Badge
                  key={c}
                  variant={c === missingCol ? 'danger' : 'default'}
                >
                  {c}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Aggregations */}
        {parsed.aggregations.length > 0 && (
          <div>
            <h5 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              Aggregations
            </h5>
            <div className="flex flex-wrap gap-1.5">
              {parsed.aggregations.map((a) => (
                <Badge key={a} variant="purple">
                  {a}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Aliases */}
        {Object.keys(parsed.aliases).length > 0 && (
          <div>
            <h5 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              Column aliases
            </h5>
            <div className="space-y-1">
              {Object.entries(parsed.aliases).map(([alias, expr]) => (
                <div key={alias} className="text-[12px] font-mono text-slate-600">
                  <span className="font-semibold text-slate-900">{alias}</span>
                  <span className="text-slate-400 mx-2">←</span>
                  <span>{expr}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-100 border border-slate-200">
      <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
        {label}
      </span>
      <span className="text-[13px] font-bold text-brand-600">{value}</span>
    </div>
  )
}
