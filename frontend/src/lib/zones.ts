import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './api'
import type { DeliveryZone } from './types'

// ---------------------------------------------------------------------------
// Distritos de reparto: GET /delivery-zones, POST, PATCH /delivery-zones/{id}
//
// No hay DELETE a proposito: un distrito que deja de tener cobertura se apaga
// (is_active = false) y conserva su tarifa para cuando vuelva a la lista.
// ---------------------------------------------------------------------------

async function fetchZones(all: boolean): Promise<DeliveryZone[]> {
  const response = await apiClient.get<DeliveryZone[]>('/delivery-zones', {
    // Solo owner/admin pueden pedir las apagadas; sin el parametro la API
    // devuelve las activas, que es lo mismo que ve el asistente.
    params: all ? { all: true } : undefined,
  })
  return response.data
}

export function useZones(all: boolean) {
  return useQuery({
    queryKey: ['delivery-zones', { all }],
    queryFn: () => fetchZones(all),
    staleTime: 5 * 60 * 1000,
    networkMode: 'offlineFirst',
  })
}

export interface DeliveryZoneCreateInput {
  district: string
  fee: string
}

async function createZone(input: DeliveryZoneCreateInput): Promise<DeliveryZone> {
  const response = await apiClient.post<DeliveryZone>('/delivery-zones', input)
  return response.data
}

export function useCreateZone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createZone,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['delivery-zones'] })
    },
  })
}

export interface DeliveryZoneUpdateInput {
  district?: string
  fee?: string
  is_active?: boolean
}

async function updateZone(id: string, input: DeliveryZoneUpdateInput): Promise<DeliveryZone> {
  const response = await apiClient.patch<DeliveryZone>(`/delivery-zones/${id}`, input)
  return response.data
}

export function useUpdateZone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: DeliveryZoneUpdateInput }) =>
      updateZone(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['delivery-zones'] })
    },
  })
}
