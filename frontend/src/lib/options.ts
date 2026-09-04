import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './api'
import type { OptionGroup, OptionItem, ProductOptionGroupLink } from './types'

// ---------------------------------------------------------------------------
// Extras y opciones de plato (migracion 0023).
//
// GET /option-groups, POST, PATCH /option-groups/{id}
// POST /option-groups/{id}/items, PATCH /option-items/{id}
// GET/PUT /products/{id}/option-groups
//
// No hay DELETE a proposito: un grupo o una opcion que deja de ofrecerse se
// apaga (is_active = false). Los pedidos viejos apuntan a la fila y el panel
// puede volver a encenderla.
// ---------------------------------------------------------------------------

const GROUPS_KEY = ['option-groups']

async function fetchOptionGroups(all: boolean): Promise<OptionGroup[]> {
  const response = await apiClient.get<OptionGroup[]>('/option-groups', {
    params: all ? { all: true } : undefined,
  })
  return response.data
}

export function useOptionGroups(all: boolean) {
  return useQuery({
    queryKey: [...GROUPS_KEY, { all }],
    queryFn: () => fetchOptionGroups(all),
    staleTime: 5 * 60 * 1000,
    networkMode: 'offlineFirst',
  })
}

export interface OptionGroupCreateInput {
  name: string
  selection: 'single' | 'multiple'
  required?: boolean
  min_choices?: number
  max_choices?: number | null
  sort_order?: number
}

async function createOptionGroup(input: OptionGroupCreateInput): Promise<OptionGroup> {
  const response = await apiClient.post<OptionGroup>('/option-groups', input)
  return response.data
}

export function useCreateOptionGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createOptionGroup,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: GROUPS_KEY })
    },
  })
}

export interface OptionGroupUpdateInput {
  name?: string
  selection?: 'single' | 'multiple'
  required?: boolean
  min_choices?: number
  max_choices?: number | null
  sort_order?: number
  is_active?: boolean
}

async function updateOptionGroup(id: string, input: OptionGroupUpdateInput): Promise<OptionGroup> {
  const response = await apiClient.patch<OptionGroup>(`/option-groups/${id}`, input)
  return response.data
}

export function useUpdateOptionGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: OptionGroupUpdateInput }) =>
      updateOptionGroup(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: GROUPS_KEY })
    },
  })
}

export interface OptionItemCreateInput {
  name: string
  price?: string
  product_id?: string | null
  sort_order?: number
}

async function createOptionItem(groupId: string, input: OptionItemCreateInput): Promise<OptionItem> {
  const response = await apiClient.post<OptionItem>(`/option-groups/${groupId}/items`, input)
  return response.data
}

export function useCreateOptionItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ groupId, input }: { groupId: string; input: OptionItemCreateInput }) =>
      createOptionItem(groupId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: GROUPS_KEY })
    },
  })
}

export interface OptionItemUpdateInput {
  name?: string
  price?: string
  product_id?: string | null
  sort_order?: number
  is_active?: boolean
}

async function updateOptionItem(id: string, input: OptionItemUpdateInput): Promise<OptionItem> {
  const response = await apiClient.patch<OptionItem>(`/option-items/${id}`, input)
  return response.data
}

export function useUpdateOptionItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: OptionItemUpdateInput }) =>
      updateOptionItem(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: GROUPS_KEY })
    },
  })
}

// ---------------------------------------------------------------------------
// Asignacion plato -> grupos
// ---------------------------------------------------------------------------

function productGroupsKey(productId: string) {
  return ['product-option-groups', productId]
}

async function fetchProductOptionGroups(productId: string): Promise<ProductOptionGroupLink[]> {
  const response = await apiClient.get<ProductOptionGroupLink[]>(
    `/products/${productId}/option-groups`,
  )
  return response.data
}

export function useProductOptionGroups(productId: string) {
  return useQuery({
    queryKey: productGroupsKey(productId),
    queryFn: () => fetchProductOptionGroups(productId),
    staleTime: 5 * 60 * 1000,
    networkMode: 'offlineFirst',
  })
}

// La pantalla por plato necesita las asignaciones de toda la carta a la vez
// (resumen en cada tarjeta y "este grupo se usa en N platos"). Misma clave
// por producto que useProductOptionGroups, asi el PUT invalida las dos.
export function useProductsOptionGroups(productIds: string[]) {
  return useQueries({
    queries: productIds.map((productId) => ({
      queryKey: productGroupsKey(productId),
      queryFn: () => fetchProductOptionGroups(productId),
      staleTime: 5 * 60 * 1000,
      networkMode: 'offlineFirst' as const,
    })),
  })
}

async function replaceProductOptionGroups(
  productId: string,
  groupIds: string[],
): Promise<ProductOptionGroupLink[]> {
  const response = await apiClient.put<ProductOptionGroupLink[]>(
    `/products/${productId}/option-groups`,
    { group_ids: groupIds },
  )
  return response.data
}

export function useReplaceProductOptionGroups() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ productId, groupIds }: { productId: string; groupIds: string[] }) =>
      replaceProductOptionGroups(productId, groupIds),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: productGroupsKey(variables.productId) })
    },
  })
}
