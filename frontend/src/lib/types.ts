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
  // Flags independientes (issue #140): compra = insumo, venta = item de pedido.
  is_purchase: boolean
  is_sale: boolean
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
// Purchase orders (v0.3)
// ---------------------------------------------------------------------------

export type PurchaseOrderStatus = 'open' | 'partially_received' | 'closed' | 'annulled'

/** EP-2 GET /purchase-orders — owner/admin list item */
export interface PurchaseOrderListItem {
  id: string
  supplier_name: string
  created_at: string // ISO 8601 UTC
  derived_status: PurchaseOrderStatus
  item_count: number
  total_ordered: string  // Decimal as string
  total_received: string
  pending_amount: string
  pending_summary: string | null
}

/** EP-1/EP-3 GET /purchase-orders/{id} — detail item */
export interface PurchaseOrderDetailItem {
  id: string
  product_id: string
  product_name: string
  unit: string
  expected_qty: string
  unit_cost: string
  received_qty: string
  pending_qty: string
  line_total: string
}

/** EP-3 GET /purchase-orders/{id} — full detail */
export interface PurchaseOrderDetailResponse {
  id: string
  supplier_name: string
  created_at: string
  created_by_name: string
  derived_status: PurchaseOrderStatus
  items: PurchaseOrderDetailItem[]
  total_ordered: string
  total_received: string
  pending_amount: string
  partida_count: number
}

/** EP-1 POST /purchase-orders — request */
export interface PurchaseOrderCreateItem {
  product_id: string
  expected_qty: number
  unit_cost: number
}

export interface PurchaseOrderCreate {
  supplier_name: string
  items: PurchaseOrderCreateItem[]
}

/** EP-4 GET /purchase-orders/pending — cocinero/admin, zero monetary fields */
export interface PurchaseOrderPendingItem {
  id: string
  supplier_name: string
  created_at: string
  derived_status: 'open' | 'partially_received'
  pending_items_summary: string
}

/** EP-5 GET /purchase-orders/{id}/partida-draft — cocinero/admin, zero monetary fields */
export interface PartidaDraftItem {
  purchase_order_item_id: string
  product_id: string
  product_name: string
  unit: string
  pending_qty: string   // Decimal as string
  already_received: string
}

export interface PartidaDraftResponse {
  order_id: string
  supplier_name: string
  partida_number: number
  items: PartidaDraftItem[]
}

/** EP-6 POST /purchase-orders/{id}/partidas — request */
export interface PartidaCreateItem {
  purchase_order_item_id: string
  received_qty: number
}

export interface PartidaCreate {
  items: PartidaCreateItem[]
}

/** EP-6 POST /purchase-orders/{id}/partidas — response, zero monetary fields */
export interface PartidaResponse {
  delivery_id: string
  partida_number: number
  order_id: string
  order_status: 'open' | 'partially_received' | 'closed'
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
