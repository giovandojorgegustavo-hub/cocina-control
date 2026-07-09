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

// ---------------------------------------------------------------------------
// Inventory counts
// ---------------------------------------------------------------------------

export type InventoryCountStatus = 'in_progress' | 'completed'

export interface InventoryCountItem {
  /** item_id from the server — used for corrections */
  id: string
  product_id: string
  quantity: number
}

export interface InventoryCount {
  id: string
  status: InventoryCountStatus
  started_at: string
  /** Leaf items per product: the effective (most recent) count for each product */
  items: InventoryCountItem[]
}

export interface StartInventoryCountResponse {
  id: string
  status: 'in_progress'
  started_at: string
}

export interface AddInventoryItemPayload {
  product_id: string
  quantity: number
}

export interface AddInventoryItemResponse {
  item_id: string
  product_id: string
  quantity: number
}

export interface CorrectInventoryItemPayload {
  quantity: number
  reason?: string
}

export interface CorrectInventoryItemResponse {
  new_item_id: string
  corrects_id: string
}

// ---------------------------------------------------------------------------
// Dashboard (owner-only)
// ---------------------------------------------------------------------------

export interface DashboardProduct {
  product_id: string
  name: string
  unit: string
  stock_now: number
  entries: number
  /** null when consumption_available is false */
  consumption: number | null
  consumption_available: boolean
  alert: boolean
  low_stock_threshold: number | null
}

export interface DashboardLowStockItem {
  product_id: string
  name: string
  unit: string
  stock_now: number
  low_stock_threshold: number
}

export interface DashboardOrdersSummary {
  completed_count: number
  photo_only_count: number
}

export interface DashboardSummary {
  products: DashboardProduct[]
  low_stock: DashboardLowStockItem[]
  orders_summary: DashboardOrdersSummary
  /** ISO 8601 UTC — most recent inventory count timestamp across all products */
  last_inventory_at: string | null
}

// ---------------------------------------------------------------------------
// Traceability event
// ---------------------------------------------------------------------------

export type TraceabilityEventType = 'ENTREGA' | 'PEDIDO' | 'INVENTARIO'

export interface TraceabilityEvent {
  id: string
  date: string // ISO 8601 UTC
  type: TraceabilityEventType
  qty: number
  unit: string
  operator: string
  note: string | null
  corrects_id: string | null
  /** Set on the corrected event: "corregido → X un." */
  corrected_by_note: string | null
}
