import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './api'
import type { Product } from './types'

export type ProductFlow = 'purchase' | 'sale'

async function fetchProducts(flow?: ProductFlow): Promise<Product[]> {
  const response = await apiClient.get<Product[]>('/products', {
    params: flow ? { flow } : undefined,
  })
  return response.data
}

export function useProducts(flow?: ProductFlow) {
  return useQuery({
    queryKey: ['products', flow ?? 'all'],
    queryFn: () => fetchProducts(flow),
    staleTime: 5 * 60 * 1000, // 5 min — catalog changes rarely
    networkMode: 'offlineFirst',
  })
}

export interface CreateProductInput {
  name: string
  unit: string
  is_purchase?: boolean
  is_sale?: boolean
}

async function createProduct(input: CreateProductInput): Promise<Product> {
  const response = await apiClient.post<Product>('/products', input)
  return response.data
}

export function useCreateProduct() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createProduct,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
  })
}
