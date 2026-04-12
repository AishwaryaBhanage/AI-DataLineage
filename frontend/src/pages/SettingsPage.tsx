import { useState } from 'react'
import { toast } from 'sonner'
import { Key, Globe, FolderOpen, Save, Eye, EyeOff } from 'lucide-react'
import { Header } from '@/components/Header'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Input, Label } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { useSettings } from '@/lib/store'

export function SettingsPage() {
  const settings = useSettings()
  const [showKey, setShowKey] = useState(false)

  return (
    <>
      <Header title="Settings" subtitle="Configure API connection and defaults" />

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-2xl mx-auto space-y-6">
          {/* API connection */}
          <Card>
            <CardHeader
              title="API connection"
              subtitle="Credentials and endpoint for the DataLineage API"
            />
            <CardBody className="space-y-5">
              <div>
                <Label>API base URL</Label>
                <div className="relative">
                  <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <Input
                    className="pl-9"
                    placeholder="http://localhost:8000 (leave empty in dev)"
                    value={settings.apiBaseUrl}
                    onChange={(e) => settings.setApiBaseUrl(e.target.value)}
                  />
                </div>
                <p className="mt-1.5 text-[11px] text-slate-500">
                  In dev, leave empty to use the Vite proxy that forwards{' '}
                  <code className="bg-slate-100 px-1 rounded">/api</code> to
                  localhost:8000.
                  <br />
                  In production, set to your deployed API URL.
                </p>
              </div>

              <div>
                <Label>API key (Bearer token)</Label>
                <div className="relative">
                  <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <Input
                    className="pl-9 pr-9 font-mono"
                    type={showKey ? 'text' : 'password'}
                    placeholder="dl_test_..."
                    value={settings.apiKey}
                    onChange={(e) => settings.setApiKey(e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    {showKey ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </button>
                </div>
                <p className="mt-1.5 text-[11px] text-slate-500">
                  Sent as{' '}
                  <code className="bg-slate-100 px-1 rounded">
                    Authorization: Bearer &lt;key&gt;
                  </code>
                  . Stored in your browser's localStorage only.
                </p>
              </div>
            </CardBody>
          </Card>

          {/* Defaults */}
          <Card>
            <CardHeader
              title="Default dbt artifact paths"
              subtitle="Used as defaults on the Debug page"
            />
            <CardBody className="space-y-5">
              <div>
                <Label>Default manifest.json path</Label>
                <div className="relative">
                  <FolderOpen className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <Input
                    className="pl-9"
                    value={settings.manifestPath}
                    onChange={(e) => settings.setManifestPath(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <Label>Default run_results.json path</Label>
                <div className="relative">
                  <FolderOpen className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <Input
                    className="pl-9"
                    value={settings.runResultsPath}
                    onChange={(e) => settings.setRunResultsPath(e.target.value)}
                  />
                </div>
              </div>
            </CardBody>
          </Card>

          <div className="flex justify-end">
            <Button onClick={() => toast.success('Settings saved')}>
              <Save className="w-4 h-4" />
              Save changes
            </Button>
          </div>
        </div>
      </div>
    </>
  )
}
