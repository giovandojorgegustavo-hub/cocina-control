import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './api'
import type {
  PurchaseOrderReceivedPartida,
  PurchaseOrderListItem,
  PurchaseOrderDetailResponse,
  PurchaseOrderCreate,
  PurchaseOrderPendingItem,
  PartidaDraftResponse,
  PartidaCreate,
  PartidaResponse,
  PurchaseOrderStatus,
} from './types'

// ---------------------------------------------------------------------------
// EP-2 GET /purchase-orders — owner/admin
// ---------------------------------------------------------------------------

async function fetchPurchaseOrders(status?: string): Promise<PurchaseOrderListItem[]> {
  const params = status && status !== 'all' ? { status } : undefined
  const response = await apiClient.get<PurchaseOrderListItem[]>('/purchase-orders', { params })
  return response.data
}

export function usePurchaseOrders(status?: PurchaseOrderStatus | 'all', userId?: string | null) {
  return useQuery({
    queryKey: ['purchase-orders', status ?? 'all', userId ?? null],
    queryFn: () => fetchPurchaseOrders(status),
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// EP-3 GET /purchase-orders/{id} — owner/admin
// ---------------------------------------------------------------------------

async function fetchPurchaseOrder(id: string): Promise<PurchaseOrderDetailResponse> {
  const response = await apiClient.get<PurchaseOrderDetailResponse>(`/purchase-orders/${id}`)
  return response.data
}

export function usePurchaseOrder(id: string, userId?: string | null) {
  return useQuery({
    queryKey: ['purchase-order', id, userId ?? null],
    queryFn: () => fetchPurchaseOrder(id),
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// EP-1 POST /purchase-orders — owner/admin
// ---------------------------------------------------------------------------

export function useCreatePurchaseOrder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: PurchaseOrderCreate) =>
      apiClient.post<PurchaseOrderDetailResponse>('/purchase-orders', data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['purchase-orders'] })
    },
  })
}

// ---------------------------------------------------------------------------
// EP-4 GET /purchase-orders/pending — cocinero/admin (zero monetary fields)
// ---------------------------------------------------------------------------

async function fetchPendingPurchaseOrders(): Promise<PurchaseOrderPendingItem[]> {
  const response = await apiClient.get<PurchaseOrderPendingItem[]>('/purchase-orders/pending')
  return response.data
}

export function usePendingPurchaseOrders(userId?: string | null) {
  return useQuery({
    queryKey: ['purchase-orders-pending', userId ?? null],
    queryFn: fetchPendingPurchaseOrders,
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// GET /purchase-orders/received — historial de partidas (issue #146)
// ---------------------------------------------------------------------------

async function fetchReceivedPartidas(): Promise<PurchaseOrderReceivedPartida[]> {
  const response = await apiClient.get<PurchaseOrderReceivedPartida[]>(
    '/purchase-orders/received',
  )
  return response.data
}

export function useReceivedPartidas(userId?: string | null) {
  return useQuery({
    queryKey: ['purchase-orders-received', userId ?? null],
    queryFn: fetchReceivedPartidas,
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// EP-5 GET /purchase-orders/{id}/partida-draft — cocinero/admin (zero monetary)
// ---------------------------------------------------------------------------

async function fetchPartidaDraft(orderId: string): Promise<PartidaDraftResponse> {
  const response = await apiClient.get<PartidaDraftResponse>(
    `/purchase-orders/${orderId}/partida-draft`,
  )
  return response.data
}

export function usePartidaDraft(orderId: string, userId?: string | null) {
  return useQuery({
    queryKey: ['partida-draft', orderId, userId ?? null],
    queryFn: () => fetchPartidaDraft(orderId),
    staleTime: 0,
    networkMode: 'offlineFirst',
    retry: false, // 409 should not be retried
  })
}

// ---------------------------------------------------------------------------
// EP-6 POST /purchase-orders/{id}/partidas — cocinero/admin
// ---------------------------------------------------------------------------

interface ValidatePartidaVars {
  orderId: string
  body: PartidaCreate
}

export function useValidatePartida() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ orderId, body }: ValidatePartidaVars) =>
      apiClient.post<PartidaResponse>(`/purchase-orders/${orderId}/partidas`, body),
    onSuccess: (_data, { orderId }) => {
      void queryClient.invalidateQueries({ queryKey: ['purchase-orders'] })
      void queryClient.invalidateQueries({ queryKey: ['purchase-orders-pending'] })
      void queryClient.invalidateQueries({ queryKey: ['purchase-order', orderId] })
      void queryClient.invalidateQueries({ queryKey: ['partida-draft', orderId] })
    },
  })
}
