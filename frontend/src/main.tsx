import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import 'reactflow/dist/style.css'
import './index.css'
import App from './App'

// One-time cleanup: remove the old persisted debug state that previous
// versions wrote to localStorage.  Now debug results are in-memory only,
// so we flush any stale blob left over from yesterday's build.
try {
  localStorage.removeItem('datalineage-debug-state')
} catch {
  /* ignore storage errors (private browsing, etc.) */
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <App />
        <Toaster position="top-right" richColors closeButton />
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
