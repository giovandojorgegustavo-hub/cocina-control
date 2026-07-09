import { useQuery } from '@tanstack/react-query'
import { apiClient } from './api'
import type { DeliveryListItem } from './types'

async function fetchDeliveries(): Promise<DeliveryListItem[]> {
  const response = await apiClient.get<DeliveryListItem[]>('/deliveries')
  return response.data
}

export function useDeliveries(userId?: string | null) {
  return useQuery({
    // Include userId in the key so a new login never sees a different user's cache
    queryKey: ['deliveries', userId ?? null],
    queryFn: fetchDeliveries,
    // Always consider data stale so re-mounting the component always revalidates.
    // If the refetch fails, TanStack keeps the previous data in `data` and sets
    // isError=true — the bandeja shows the stale list + an error banner.
    staleTime: 0,
    // In offline mode, serve the in-memory cache without triggering a network error.
    networkMode: 'offlineFirst',
  })
}
