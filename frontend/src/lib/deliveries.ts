import { useQuery } from '@tanstack/react-query'
import { apiClient } from './api'
import type { DeliveryListItem } from './types'

async function fetchDeliveries(): Promise<DeliveryListItem[]> {
  const response = await apiClient.get<DeliveryListItem[]>('/deliveries')
  return response.data
}

export function useDeliveries() {
  return useQuery({
    queryKey: ['deliveries'],
    queryFn: fetchDeliveries,
  })
}
