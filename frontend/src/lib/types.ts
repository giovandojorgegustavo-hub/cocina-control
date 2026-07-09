export type DeliveryStatus = 'no_leida' | 'en_verificacion' | 'validada'

export interface DeliveryListItem {
  id: string
  supplier_name: string
  status: DeliveryStatus
  item_count: number
  created_at: string // ISO 8601 UTC
}

export interface DeliveryItem {
  id: string
  product_id: string
  product_name: string
  unit: string
  announced_qty: number
  received_qty: number | null
}

export interface DeliveryDetail {
  id: string
  supplier_name: string
  status: DeliveryStatus
  item_count: number
  created_at: string
  validated_at: string | null
  items: DeliveryItem[]
}
