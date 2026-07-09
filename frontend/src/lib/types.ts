export type DeliveryStatus = 'no_leida' | 'en_verificacion' | 'validada'

export interface DeliveryListItem {
  id: string
  supplier_name: string
  status: DeliveryStatus
  item_count: number
  created_at: string // ISO 8601 UTC
}
