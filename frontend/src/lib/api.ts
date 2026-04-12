import axios, { AxiosError } from 'axios'
import type {
  DebugRequest,
  FastDebugResponse,
  AgenticAcceptedResponse,
  HealthResponse,
  Job,
  JobsListResponse,
  ModelsResponse,
  UsageStats,
} from './types'
import { useSettings } from './store'

// Build an axios instance per-call so it picks up settings mutations.
function client() {
  const { apiKey, apiBaseUrl } = useSettings.getState()
  const instance = axios.create({
    baseURL: apiBaseUrl || '', // empty = use the Vite proxy in dev
    timeout: 60_000,
    headers: {
      'Content-Type': 'application/json',
      ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
    },
  })

  // Normalize errors so UI code doesn't have to dig into axios internals.
  instance.interceptors.response.use(
    (r) => r,
    (err: AxiosError<{ detail?: string; error?: string }>) => {
      const detail =
        err.response?.data?.detail ||
        err.response?.data?.error ||
        err.message ||
        'Request failed'
      return Promise.reject(new ApiError(detail, err.response?.status ?? 0))
    },
  )
  return instance
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// Type guard: did POST /debug return a fast result or an agentic 202?
export function isAgenticAccepted(
  r: FastDebugResponse | AgenticAcceptedResponse,
): r is AgenticAcceptedResponse {
  return (r as AgenticAcceptedResponse).status === 'accepted'
}

// Response from the upload endpoint
export interface UploadResponse {
  upload_id: string
  manifest_path: string
  run_results_path: string
  bytes: {
    manifest: number
    run_results: number
  }
}

export const api = {
  health: async (): Promise<HealthResponse> => {
    const r = await client().get('/api/v1/health')
    return r.data
  },

  uploadArtifacts: async (
    manifest: File,
    runResults?: File,
  ): Promise<UploadResponse> => {
    // Multipart form upload — the backend saves to a temp dir and returns
    // the server-side paths we can use in subsequent /debug calls.
    const form = new FormData()
    form.append('manifest', manifest)
    if (runResults) {
      form.append('run_results', runResults)
    }
    // Use a bare axios instance so we can override the Content-Type
    // (axios sets multipart boundary automatically when we pass FormData)
    const { apiKey, apiBaseUrl } = useSettings.getState()
    const axiosInstance = (await import('axios')).default.create({
      baseURL: apiBaseUrl || '',
      timeout: 60_000,
      headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
    })
    try {
      const r = await axiosInstance.post('/api/v1/upload', form)
      return r.data
    } catch (err: any) {
      const detail =
        err.response?.data?.detail || err.response?.data?.error || err.message
      throw new ApiError(detail, err.response?.status ?? 0)
    }
  },

  debug: async (
    req: DebugRequest,
  ): Promise<FastDebugResponse | AgenticAcceptedResponse> => {
    const r = await client().post('/api/v1/debug', req)
    return r.data
  },

  getJob: async (jobId: string): Promise<Job> => {
    const r = await client().get(`/api/v1/jobs/${jobId}`)
    return r.data
  },

  listJobs: async (limit = 20): Promise<JobsListResponse> => {
    const r = await client().get('/api/v1/jobs', { params: { limit } })
    return r.data
  },

  usage: async (days = 7): Promise<UsageStats> => {
    const r = await client().get('/api/v1/usage', { params: { days } })
    return r.data
  },

  models: async (manifestPath?: string): Promise<ModelsResponse> => {
    const r = await client().get('/api/v1/models', {
      params: manifestPath ? { manifest_path: manifestPath } : undefined,
    })
    return r.data
  },
}
