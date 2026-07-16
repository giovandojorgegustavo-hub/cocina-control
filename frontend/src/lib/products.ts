import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './api'
import type { Product } from './types'

async function fetchProducts(): Promise<Product[]> {
  const response = await apiClient.get<Product[]>('/products')
  return response.data
}

export function useProducts() {
  return useQuery({
    queryKey: ['products'],
    queryFn: fetchProducts,
    staleTime: 5 * 60 * 1000, // 5 min — catalog changes rarely
    networkMode: 'offlineFirst',
  })
}

export interface CreateProductInput {
  name: string
  unit: string
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
