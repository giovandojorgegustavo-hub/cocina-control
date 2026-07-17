import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './api'

export interface Supplier {
  id: string
  name: string
  phone: string | null
}

async function fetchSuppliers(): Promise<Supplier[]> {
  const response = await apiClient.get<Supplier[]>('/suppliers')
  return response.data
}

export function useSuppliers() {
  return useQuery({
    queryKey: ['suppliers'],
    queryFn: fetchSuppliers,
    staleTime: 5 * 60 * 1000, // el registro de proveedores cambia poco
    networkMode: 'offlineFirst',
  })
}

export interface CreateSupplierInput {
  name: string
  phone?: string
}

async function createSupplier(input: CreateSupplierInput): Promise<Supplier> {
  const response = await apiClient.post<Supplier>('/suppliers', input)
  return response.data
}

export function useCreateSupplier() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createSupplier,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] })
    },
  })
}
