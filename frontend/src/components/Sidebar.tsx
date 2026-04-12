import { NavLink } from 'react-router-dom'
import {
  Bug,
  Boxes,
  BarChart3,
  ListOrdered,
  Settings as SettingsIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const items = [
  { to: '/', label: 'Debug', icon: Bug },
  { to: '/jobs', label: 'Jobs', icon: ListOrdered },
  { to: '/models', label: 'Models', icon: Boxes },
  { to: '/usage', label: 'Usage', icon: BarChart3 },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]

export function Sidebar() {
  return (
    <aside className="w-60 flex-shrink-0 bg-white border-r border-slate-200 flex flex-col">
      {/* Logo */}
      <div className="h-16 flex items-center px-5 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-brand flex items-center justify-center shadow-brand">
            <svg viewBox="0 0 24 24" className="w-4 h-4 text-white" fill="currentColor">
              <path d="M5 7h3v10H5zm5-4h3v14h-3zm5 8h3v6h-3z" />
            </svg>
          </div>
          <div>
            <div className="text-[15px] font-bold text-slate-900 leading-none">
              DataLineage
            </div>
            <div className="text-[10px] font-semibold text-brand-600 uppercase tracking-wider leading-none mt-0.5">
              AI
            </div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-[13.5px] font-medium transition-colors',
                isActive
                  ? 'bg-brand-50 text-brand-700'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900',
              )
            }
          >
            <Icon className="w-[18px] h-[18px]" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-slate-100">
        <div className="text-[11px] text-slate-500 leading-relaxed">
          <div className="font-semibold text-slate-600 mb-1">
            v1.0 · Beta
          </div>
          sqlglot · networkx · LangGraph
          <br />
          FastAPI · Claude
        </div>
      </div>
    </aside>
  )
}
