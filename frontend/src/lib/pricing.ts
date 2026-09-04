import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './api'
import type { Product, Promotion } from './types'

// ---------------------------------------------------------------------------
// Precios de la carta: PATCH /products/{id}/pricing
// ---------------------------------------------------------------------------

export interface ProductPricingInput {
  sale_price?: string | null
  discount_percent?: string | null
}

async function updateProductPricing(
  productId: string,
  input: ProductPricingInput,
): Promise<Product> {
  const response = await apiClient.patch<Product>(`/products/${productId}/pricing`, input)
  return response.data
}

export function useUpdateProductPricing() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ productId, input }: { productId: string; input: ProductPricingInput }) =>
      updateProductPricing(productId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Promociones: GET /promotions, PATCH /promotions/{code}
// ---------------------------------------------------------------------------

async function fetchPromotions(): Promise<Promotion[]> {
  const response = await apiClient.get<Promotion[]>('/promotions')
  return response.data
}

export function usePromotions() {
  return useQuery({
    queryKey: ['promotions'],
    queryFn: fetchPromotions,
    staleTime: 5 * 60 * 1000,
    networkMode: 'offlineFirst',
  })
}

export interface PromotionInput {
  name?: string
  percent?: string
  first_order_only?: boolean
  is_active?: boolean
}

async function updatePromotion(code: string, input: PromotionInput): Promise<Promotion> {
  const response = await apiClient.patch<Promotion>(`/promotions/${code}`, input)
  return response.data
}

export function useUpdatePromotion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ code, input }: { code: string; input: PromotionInput }) =>
      updatePromotion(code, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotions'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Cuenta local: espejo de _final_price del servidor, solo para previsualizar.
// El servidor recalcula al crear el pedido; esto nunca viaja.
// ---------------------------------------------------------------------------

export function finalPrice(salePrice: string, discountPercent: string): number | null {
  const price = parseFloat(salePrice)
  const percent = discountPercent.trim() === '' ? 0 : parseFloat(discountPercent)
  if (!isFinite(price) || price < 0 || !isFinite(percent) || percent < 0 || percent >= 100) {
    return null
  }
  return Math.round(price * (1 - percent / 100) * 100) / 100
}
