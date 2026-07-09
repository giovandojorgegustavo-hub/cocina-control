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

// ---------------------------------------------------------------------------
// Delivery orders (pedidos con foto)
// ---------------------------------------------------------------------------

export type DeliveryOrderStatus = 'pending' | 'completed'

export interface DeliveryOrderListItem {
  id: string
  status: DeliveryOrderStatus
  photo_at: string // ISO 8601 UTC
  photo_by: string // user id
  /** Present in response when status === 'completed' */
  completed_at?: string | null
  completed_by?: string | null
}

export interface DeliveryOrderItem {
  id: string
  product_id: string
  quantity: number
}

export interface DeliveryOrderDetail {
  id: string
  status: DeliveryOrderStatus
  photo_at: string
  photo_by: string
  completed_at: string | null
  completed_by: string | null
  items: DeliveryOrderItem[]
}

export interface CompleteOrderPayload {
  items: Array<{ product_id: string; quantity: number }>
}

// ---------------------------------------------------------------------------
// Photo queue (local-only, not from the API)
// ---------------------------------------------------------------------------

export type PhotoQueueStatus = 'queued' | 'uploading' | 'done' | 'failed' | 'orphaned'

export interface PhotoQueueEntry {
  /** Client-generated UUID. Used as local order id until server assigns one. */
  localId: string
  blob: Blob
  timestamp: string // ISO 8601 UTC, created at capture time
  status: PhotoQueueStatus
  /** User who captured this photo — used to prevent cross-user upload and visibility */
  userId: string
  /** Set after server returns the real id */
  serverId?: string
  retries: number
  nextRetryAt?: number // epoch ms
}

// ---------------------------------------------------------------------------
// Products
// ---------------------------------------------------------------------------

export interface Product {
  id: string
  name: string
  unit: string
  low_stock_threshold: number | null
}
