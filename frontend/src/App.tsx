import { Routes, Route } from 'react-router-dom'
import { Sidebar } from '@/components/Sidebar'
import { DebugPage } from '@/pages/DebugPage'
import { JobsPage } from '@/pages/JobsPage'
import { ModelsPage } from '@/pages/ModelsPage'
import { UsagePage } from '@/pages/UsagePage'
import { SettingsPage } from '@/pages/SettingsPage'

export default function App() {
  return (
    <div className="flex h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">
        <Routes>
          <Route path="/" element={<DebugPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/usage" element={<UsagePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  )
}
