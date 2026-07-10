import { useQuery } from '@tanstack/react-query'
import { apiClient } from './api'
import { useAuth } from './auth'
import type { DashboardSummary, TraceabilityEvent } from './types'

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function fetchDashboardSummary(
  from: string,
  to: string,
  signal?: AbortSignal,
): Promise<DashboardSummary> {
  const response = await apiClient.get<DashboardSummary>('/dashboard/summary', {
    params: { from, to },
    signal,
  })
  return response.data
}

async function fetchTraceability(
  productId: string,
  from: string,
  to: string,
  signal?: AbortSignal,
): Promise<TraceabilityEvent[]> {
  const response = await apiClient.get<TraceabilityEvent[]>(
    `/dashboard/traceability/${productId}`,
    { params: { from, to }, signal },
  )
  return response.data
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useDashboardSummary(userId: string | null, from: string, to: string) {
  return useQuery({
    queryKey: ['dashboard-summary', userId, from, to],
    queryFn: ({ signal }) => fetchDashboardSummary(from, to, signal),
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

export function useTraceability(
  userId: string | null,
  productId: string,
  from: string,
  to: string,
) {
  return useQuery({
    queryKey: ['dashboard-traceability', userId, productId, from, to],
    queryFn: ({ signal }) => fetchTraceability(productId, from, to, signal),
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class CsvAuthError extends Error {
  constructor() {
    super('CSV download failed: 401')
    this.name = 'CsvAuthError'
  }
}

// ---------------------------------------------------------------------------
// CSV download utility — uses fetch + blob because <a href> cannot send the
// Authorization header required by the backend.
// ---------------------------------------------------------------------------

export async function downloadCsv(
  from: string,
  to: string,
  type: 'all' | 'delivery' | 'order' | 'count' = 'all',
): Promise<void> {
  const token = useAuth.getState().token

  // Fail early if there is no token — avoids a 401 round-trip.
  if (!token) {
    throw new CsvAuthError()
  }

  // Same convention as src/lib/api.ts: VITE_API_URL wins if set; otherwise derive
  // from BASE_URL so the request goes to /interno/api/v1/... in production.
  const baseUrl = import.meta.env.VITE_API_URL || import.meta.env.BASE_URL.replace(/\/$/, '')
  const url = `${baseUrl}/api/v1/dashboard/export?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&type=${type}`

  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (response.status === 401) {
    throw new CsvAuthError()
  }

  if (!response.ok) {
    throw new Error(`CSV download failed: ${response.status}`)
  }

  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = `cocina-control_${from}_${to}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}
