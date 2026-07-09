import { useQuery } from '@tanstack/react-query'
import { apiClient } from './api'
import { useAuth } from './auth'
import type { DashboardSummary, TraceabilityEvent } from './types'

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function fetchDashboardSummary(from: string, to: string): Promise<DashboardSummary> {
  const response = await apiClient.get<DashboardSummary>('/dashboard/summary', {
    params: { from, to },
  })
  return response.data
}

async function fetchTraceability(
  productId: string,
  from: string,
  to: string,
): Promise<TraceabilityEvent[]> {
  const response = await apiClient.get<TraceabilityEvent[]>(
    `/dashboard/traceability/${productId}`,
    { params: { from, to } },
  )
  return response.data
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useDashboardSummary(from: string, to: string) {
  return useQuery({
    queryKey: ['dashboard-summary', from, to],
    queryFn: () => fetchDashboardSummary(from, to),
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

export function useTraceability(productId: string, from: string, to: string) {
  return useQuery({
    queryKey: ['dashboard-traceability', productId, from, to],
    queryFn: () => fetchTraceability(productId, from, to),
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
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
  const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
  const url = `${baseUrl}/api/v1/dashboard/export?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&type=${type}`

  const response = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })

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
