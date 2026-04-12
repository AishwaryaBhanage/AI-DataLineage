import { useQuery } from '@tanstack/react-query'
import { Database, ArrowUpRight, ArrowDownRight, RefreshCw } from 'lucide-react'
import { Header } from '@/components/Header'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input, Label } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { useSettings } from '@/lib/store'
import { useState } from 'react'

export function ModelsPage() {
  const defaultPath = useSettings((s) => s.manifestPath)
  const [manifestPath, setManifestPath] = useState(defaultPath)

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['models', manifestPath],
    queryFn: () => api.models(manifestPath),
    enabled: !!manifestPath,
  })

  return (
    <>
      <Header
        title="Models"
        subtitle="Browse dbt project structure and dependencies"
      />

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-5xl mx-auto space-y-6">
          <Card>
            <CardBody>
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <Label>Manifest path</Label>
                  <Input
                    value={manifestPath}
                    onChange={(e) => setManifestPath(e.target.value)}
                    placeholder="dbt_demo/target/manifest.json"
                  />
                </div>
                <Button
                  variant="secondary"
                  onClick={() => refetch()}
                  disabled={isFetching}
                >
                  <RefreshCw
                    className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`}
                  />
                  Reload
                </Button>
              </div>
            </CardBody>
          </Card>

          {error && (
            <Card className="border-rose-200 bg-rose-50/30">
              <CardBody>
                <div className="text-rose-700 text-sm">{String(error)}</div>
              </CardBody>
            </Card>
          )}

          {isLoading && (
            <Card>
              <CardBody className="py-12 text-center text-slate-400">
                Loading manifest...
              </CardBody>
            </Card>
          )}

          {data && (
            <>
              {/* Project info */}
              <Card>
                <CardHeader
                  title={data.project}
                  subtitle={`${data.total_models} models · ${data.adapter} adapter`}
                  action={<Badge variant="info">{data.adapter}</Badge>}
                />
              </Card>

              {/* Models list */}
              <Card>
                <CardHeader title="All models" />
                <CardBody className="!p-0">
                  <div className="divide-y divide-slate-100">
                    {data.models.map((m) => (
                      <div
                        key={m.name}
                        className="px-5 py-4 hover:bg-slate-50/50 transition-colors"
                      >
                        <div className="flex items-start gap-3">
                          <div className="w-9 h-9 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <Database className="w-4 h-4" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <h3 className="text-[14px] font-semibold text-slate-900">
                                {m.name}
                              </h3>
                              <Badge variant="purple">{m.materialized}</Badge>
                            </div>
                            <div className="text-[11px] text-slate-500 font-mono mb-2">
                              {m.file_path}
                            </div>
                            <div className="flex flex-wrap gap-4 text-[11px]">
                              {m.upstream.length > 0 && (
                                <div className="flex items-center gap-1.5 text-slate-600">
                                  <ArrowUpRight className="w-3 h-3 text-violet-500" />
                                  <span className="font-semibold">Upstream:</span>
                                  {m.upstream.map((u) => (
                                    <code key={u} className="text-violet-700 bg-violet-50 px-1.5 py-0.5 rounded">
                                      {u}
                                    </code>
                                  ))}
                                </div>
                              )}
                              {m.downstream.length > 0 && (
                                <div className="flex items-center gap-1.5 text-slate-600">
                                  <ArrowDownRight className="w-3 h-3 text-blue-500" />
                                  <span className="font-semibold">Downstream:</span>
                                  {m.downstream.map((d) => (
                                    <code key={d} className="text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded">
                                      {d}
                                    </code>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
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
