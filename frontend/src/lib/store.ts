import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { FastDebugResponse, Job } from './types'

// ── Settings store ───────────────────────────────────────────────────────────
// Persisted to localStorage so the API key survives page reloads.
// NEVER write secrets anywhere else (cookies, URL params, server logs).
interface Settings {
  apiKey: string
  apiBaseUrl: string
  manifestPath: string
  runResultsPath: string
  setApiKey: (v: string) => void
  setApiBaseUrl: (v: string) => void
  setManifestPath: (v: string) => void
  setRunResultsPath: (v: string) => void
}

export const useSettings = create<Settings>()(
  persist(
    (set) => ({
      apiKey: '',
      apiBaseUrl: '',
      manifestPath: 'dbt_demo/target/manifest.json',
      runResultsPath: 'dbt_demo/target/run_results.json',
      setApiKey: (apiKey) => set({ apiKey }),
      setApiBaseUrl: (apiBaseUrl) => set({ apiBaseUrl }),
      setManifestPath: (manifestPath) => set({ manifestPath }),
      setRunResultsPath: (runResultsPath) => set({ runResultsPath }),
    }),
    { name: 'datalineage-settings' },
  ),
)

// ── Debug result store ───────────────────────────────────────────────────────
// In-memory only (no persist middleware).
//
// Design:
//   - Lives outside React tree so it survives page navigation
//     (Debug → Jobs → Models → back to Debug keeps the result)
//   - NOT written to localStorage so a browser refresh clears everything
//   - This is intentional: showing a stale result after a refresh is
//     confusing, and the user probably wants a clean slate anyway.
//
// If you ever want to persist results across refreshes, wrap with persist
// and use partialize to filter out pollingJobId (a stale one would trigger
// ghost polls against a job that no longer exists).
interface DebugState {
  result: FastDebugResponse | null
  agenticJob: Job | null
  pollingJobId: string | null
  setResult: (r: FastDebugResponse | null) => void
  setAgenticJob: (j: Job | null) => void
  setPollingJobId: (id: string | null) => void
  clearResults: () => void
}

export const useDebugState = create<DebugState>()((set) => ({
  result: null,
  agenticJob: null,
  pollingJobId: null,
  setResult: (result) => set({ result }),
  setAgenticJob: (agenticJob) => set({ agenticJob }),
  setPollingJobId: (pollingJobId) => set({ pollingJobId }),
  clearResults: () =>
    set({ result: null, agenticJob: null, pollingJobId: null }),
}))
