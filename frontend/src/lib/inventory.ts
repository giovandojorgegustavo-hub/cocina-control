import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './api'
import type {
  InventoryCount,
  StartInventoryCountResponse,
  AddInventoryItemPayload,
  AddInventoryItemResponse,
  CorrectInventoryItemPayload,
  CorrectInventoryItemResponse,
} from './types'

// ---------------------------------------------------------------------------
// localStorage helpers
// Key is scoped per user so a different login never resumes another user's count.
// ---------------------------------------------------------------------------

export function inventoryCountKey(userId: string): string {
  return `cocina-inventory-count-${userId}`
}

export function getSavedCountId(userId: string): string | null {
  return localStorage.getItem(inventoryCountKey(userId))
}

export function saveCountId(userId: string, countId: string): void {
  localStorage.setItem(inventoryCountKey(userId), countId)
}

export function clearSavedCountId(userId: string): void {
  localStorage.removeItem(inventoryCountKey(userId))
}

// ---------------------------------------------------------------------------
// Start a new inventory count
// ---------------------------------------------------------------------------

export async function startInventoryCount(): Promise<StartInventoryCountResponse> {
  const response = await apiClient.post<StartInventoryCountResponse>('/inventory-counts')
  return response.data
}

// ---------------------------------------------------------------------------
// Fetch an existing inventory count
// ---------------------------------------------------------------------------

async function fetchInventoryCount(id: string): Promise<InventoryCount> {
  const response = await apiClient.get<InventoryCount>(`/inventory-counts/${id}`)
  return response.data
}

export function useInventoryCount(id: string | null) {
  return useQuery({
    queryKey: ['inventory-count', id],
    queryFn: () => fetchInventoryCount(id!),
    enabled: id !== null,
    staleTime: 0,
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// Add an item (POST /inventory-counts/{id}/items)
// ---------------------------------------------------------------------------

interface AddItemVars {
  countId: string
  payload: AddInventoryItemPayload
}

export function useAddInventoryItem() {
  const queryClient = useQueryClient()

  return useMutation<AddInventoryItemResponse, Error, AddItemVars>({
    mutationFn: ({ countId, payload }) =>
      apiClient
        .post<AddInventoryItemResponse>(`/inventory-counts/${countId}/items`, payload)
        .then((r) => r.data),
    onSuccess: (_data, { countId }) => {
      void queryClient.invalidateQueries({ queryKey: ['inventory-count', countId] })
    },
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// Correct an existing item (POST /inventory-counts/{id}/items/{itemId}/correct)
// ---------------------------------------------------------------------------

interface CorrectItemVars {
  countId: string
  itemId: string
  payload: CorrectInventoryItemPayload
}

export function useCorrectInventoryItem() {
  const queryClient = useQueryClient()

  return useMutation<CorrectInventoryItemResponse, Error, CorrectItemVars>({
    mutationFn: ({ countId, itemId, payload }) =>
      apiClient
        .post<CorrectInventoryItemResponse>(
          `/inventory-counts/${countId}/items/${itemId}/correct`,
          payload,
        )
        .then((r) => r.data),
    onSuccess: (_data, { countId }) => {
      void queryClient.invalidateQueries({ queryKey: ['inventory-count', countId] })
    },
    networkMode: 'offlineFirst',
  })
}

// ---------------------------------------------------------------------------
// Complete the inventory count (POST /inventory-counts/{id}/complete)
// ---------------------------------------------------------------------------

interface CompleteCountResponse {
  id: string
  status: 'completed'
  completed_at: string
}

export function useCompleteInventoryCount() {
  const queryClient = useQueryClient()

  return useMutation<CompleteCountResponse, Error, string>({
    mutationFn: (countId) =>
      apiClient
        .post<CompleteCountResponse>(`/inventory-counts/${countId}/complete`)
        .then((r) => r.data),
    onSuccess: (_data, countId) => {
      void queryClient.invalidateQueries({ queryKey: ['inventory-count', countId] })
    },
    networkMode: 'offlineFirst',
  })
}
