import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './api'
import type {
  DeliveryOrderListItem,
  DeliveryOrderDetail,
  CompleteOrderPayload,
} from './types'

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function fetchOrders(status?: 'pending' | 'completed'): Promise<DeliveryOrderListItem[]> {
  const params = status ? { status } : {}
  const response = await apiClient.get<DeliveryOrderListItem[]>('/delivery-orders', { params })
  return response.data
}

async function fetchOrder(id: string): Promise<DeliveryOrderDetail> {
  const response = await apiClient.get<DeliveryOrderDetail>(`/delivery-orders/${id}`)
  return response.data
}

// ---------------------------------------------------------------------------
// List query — returns pending + completed combined, sorted by caller
// ---------------------------------------------------------------------------

export function useOrders(userId?: string | null) {
  return useQuery({
    queryKey: ['orders', userId ?? null],
    queryFn: () => fetchOrders(),
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

export function useOrdersByStatus(
  status: 'pending' | 'completed',
  userId?: string | null,
) {
  return useQuery({
    queryKey: ['orders', status, userId ?? null],
    queryFn: () => fetchOrders(status),
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// Detail query
// ---------------------------------------------------------------------------

export function useOrder(id: string) {
  return useQuery({
    queryKey: ['order', id],
    queryFn: () => fetchOrder(id),
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// Complete order mutation
// ---------------------------------------------------------------------------

export function useCompleteOrder(orderId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CompleteOrderPayload) =>
      apiClient.post(`/delivery-orders/${orderId}/complete`, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['order', orderId] })
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// Cancel order mutation
// ---------------------------------------------------------------------------

export function useCancelOrder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      apiClient.post(`/delivery-orders/${id}/cancel`, reason ? { reason } : {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
    networkMode: 'offlineFirst',
  })
}
