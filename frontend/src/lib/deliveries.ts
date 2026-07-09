import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './api'
import type { DeliveryListItem, DeliveryDetail } from './types'

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function fetchDeliveries(): Promise<DeliveryListItem[]> {
  const response = await apiClient.get<DeliveryListItem[]>('/deliveries')
  return response.data
}

async function fetchDelivery(id: string): Promise<DeliveryDetail> {
  const response = await apiClient.get<DeliveryDetail>(`/deliveries/${id}`)
  return response.data
}

// ---------------------------------------------------------------------------
// List query
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Detail query
// ---------------------------------------------------------------------------

export function useDelivery(id: string) {
  return useQuery({
    queryKey: ['delivery', id],
    queryFn: () => fetchDelivery(id),
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// Open delivery mutation: no_leida → en_verificacion
// ---------------------------------------------------------------------------

export function useOpenDelivery() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => apiClient.post(`/deliveries/${id}/open`),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: ['delivery', id] })
    },
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// Confirm item mutation — with optimistic update managed externally by the
// caller, because the caller owns the local item state.
// ---------------------------------------------------------------------------

interface ConfirmItemVars {
  deliveryId: string
  itemId: string
  receivedQty: number
}

export function useConfirmItem() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ deliveryId, itemId, receivedQty }: ConfirmItemVars) =>
      apiClient.post(`/deliveries/${deliveryId}/items/${itemId}/confirm`, {
        received_qty: receivedQty,
      }),
    onSuccess: (_data, { deliveryId }) => {
      void queryClient.invalidateQueries({ queryKey: ['delivery', deliveryId] })
    },
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// Validate delivery mutation
// ---------------------------------------------------------------------------

export function useValidateDelivery() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => apiClient.post(`/deliveries/${id}/validate`),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: ['delivery', id] })
      void queryClient.invalidateQueries({ queryKey: ['deliveries'] })
    },
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// Correct item mutation (post-validate; append-only)
// ---------------------------------------------------------------------------

interface CorrectItemVars {
  deliveryId: string
  itemId: string
  receivedQty: number
  reason?: string
}

export function useCorrectItem() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ deliveryId, itemId, receivedQty, reason }: CorrectItemVars) =>
      apiClient.post(`/deliveries/${deliveryId}/items/${itemId}/correct`, {
        received_qty: receivedQty,
        ...(reason !== undefined ? { reason } : {}),
      }),
    onSuccess: (_data, { deliveryId }) => {
      void queryClient.invalidateQueries({ queryKey: ['delivery', deliveryId] })
    },
    networkMode: 'offlineFirst',
  })
}
