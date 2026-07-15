import { useState, useId, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProducts } from '../lib/products'
import { usePurchaseOrders, useCreatePurchaseOrder } from '../lib/purchaseOrders'
import { useAuthWithGetters } from '../lib/auth'
import { formatSoles } from '../lib/currency'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface OrderItem {
  localId: string
  product_id: string
  product_name: string
  unit: string
  qty: string
  cost: string
}

function emptyItem(localId: string): OrderItem {
  return { localId, product_id: '', product_name: '', unit: '', qty: '', cost: '' }
}

function lineTotal(item: OrderItem): number {
  const q = parseFloat(item.qty)
  const c = parseFloat(item.cost)
  if (!isFinite(q) || !isFinite(c) || q <= 0 || c <= 0) return 0
  return q * c
}

function orderTotal(items: OrderItem[]): number {
  return items.reduce((acc, i) => acc + lineTotal(i), 0)
}

function isItemValid(item: OrderItem): boolean {
  const q = parseFloat(item.qty)
  const c = parseFloat(item.cost)
  return item.product_id !== '' && isFinite(q) && q > 0 && isFinite(c) && c > 0
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

interface ToastState {
  visible: boolean
  message: string
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function OrdenNueva() {
  const navigate = useNavigate()
  const { userId } = useAuthWithGetters()
  const nextId = useId()
  const nextIdRef = useRef(1)

  const { data: products } = useProducts()
  const { data: existingOrders } = usePurchaseOrders('all', userId)
  const createMutation = useCreatePurchaseOrder()

  const [supplierName, setSupplierName] = useState('')
  const [items, setItems] = useState<OrderItem[]>([emptyItem(`item-${nextId}-0`)])
  const [toast, setToast] = useState<ToastState>({ visible: false, message: '' })

  // Datalist: distinct supplier names from previous orders
  const supplierDatalistId = `suppliers-${nextId}`
  const distinctSuppliers = existingOrders
    ? [...new Set(existingOrders.map((o) => o.supplier_name))]
    : []

  // Product IDs already chosen — to disable duplicates in other rows
  const chosenProductIds = new Set(items.map((i) => i.product_id).filter(Boolean))

  // Validate form
  const supplierValid = supplierName.trim() !== ''
  const allItemsValid = items.length > 0 && items.every(isItemValid)
  const canSubmit = supplierValid && allItemsValid && !createMutation.isPending

  // Handlers
  function addItem() {
    const localId = `item-${nextId}-${nextIdRef.current++}`
    setItems((prev) => [...prev, emptyItem(localId)])
  }

  function removeItem(localId: string) {
    setItems((prev) => prev.filter((i) => i.localId !== localId))
  }

  function updateItem(localId: string, patch: Partial<OrderItem>) {
    setItems((prev) =>
      prev.map((i) => (i.localId === localId ? { ...i, ...patch } : i)),
    )
  }

  function handleProductSelect(localId: string, productId: string) {
    const product = products?.find((p) => p.id === productId)
    if (!product) {
      updateItem(localId, { product_id: '', product_name: '', unit: '' })
      return
    }
    updateItem(localId, {
      product_id: product.id,
      product_name: product.name,
      unit: product.unit,
    })
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return

    createMutation.mutate(
      {
        supplier_name: supplierName.trim(),
        items: items.map((i) => ({
          product_id: i.product_id,
          expected_qty: parseFloat(i.qty),
          unit_cost: parseFloat(i.cost),
        })),
      },
      {
        onSuccess: () => {
          navigate('/ordenes')
        },
        onError: () => {
          setToast({
            visible: true,
            message:
              'No se pudo guardar la orden. Los datos no se perdieron — toca de nuevo para reintentar.',
          })
          setTimeout(() => setToast({ visible: false, message: '' }), 5000)
        },
      },
    )
  }

  const total = orderTotal(items)

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate('/ordenes')}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver a ordenes"
        >
          &lt;
        </button>
        <h1 className="text-lg font-bold uppercase tracking-wide">NUEVA ORDEN DE COMPRA</h1>
      </header>

      <form onSubmit={handleSubmit} className="flex-1 flex flex-col">
        <main className="flex-1 px-4 py-6 space-y-6 overflow-y-auto pb-40">
          {/* Supplier */}
          <div>
            <label
              htmlFor="supplier"
              className="block text-sm font-semibold text-gray-700 mb-1"
            >
              Proveedor
            </label>
            <input
              id="supplier"
              type="text"
              list={supplierDatalistId}
              value={supplierName}
              onChange={(e) => setSupplierName(e.target.value)}
              placeholder="Nombre del proveedor"
              className="w-full px-4 py-3 border border-gray-300 bg-white focus:outline-none focus:ring-2 focus:ring-gray-900 text-base"
              autoComplete="off"
              required
            />
            <datalist id={supplierDatalistId}>
              {distinctSuppliers.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </div>

          {/* Items table */}
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-2">Productos en esta orden</p>

            {/* Table header — desktop only */}
            <div className="hidden md:grid md:grid-cols-[1fr_80px_80px_120px_80px_40px] gap-2 text-xs text-gray-500 uppercase tracking-wide mb-1 px-1">
              <span>Producto</span>
              <span>Cant.</span>
              <span>Unidad</span>
              <span>Costo unit.</span>
              <span className="text-right">Total</span>
              <span />
            </div>

            <div className="flex flex-col gap-2">
              {items.map((item) => (
                <ItemRow
                  key={item.localId}
                  item={item}
                  products={products ?? []}
                  chosenProductIds={chosenProductIds}
                  onProductSelect={(pid) => handleProductSelect(item.localId, pid)}
                  onQtyChange={(v) => updateItem(item.localId, { qty: v })}
                  onCostChange={(v) => updateItem(item.localId, { cost: v })}
                  onRemove={() => removeItem(item.localId)}
                  canRemove={items.length > 1}
                />
              ))}
            </div>

            <button
              type="button"
              onClick={addItem}
              className="mt-3 min-h-[48px] w-full border-2 border-dashed border-gray-300 text-gray-600 text-sm font-medium hover:border-gray-400 active:opacity-70"
            >
              + agregar producto
            </button>
          </div>

          {/* Total */}
          <div className="border-t border-gray-300 pt-4 flex justify-between items-center">
            <span className="text-sm font-semibold text-gray-700">Total de la orden</span>
            <span className="text-base font-bold text-gray-900">{formatSoles(total)}</span>
          </div>
        </main>

        {/* Sticky footer */}
        <footer className="fixed bottom-0 left-0 right-0 border-t border-gray-200 bg-white px-4 py-3 flex gap-3">
          <button
            type="button"
            onClick={() => navigate('/ordenes')}
            className="flex-1 min-h-[56px] border border-gray-300 text-gray-700 font-semibold text-sm active:opacity-70"
          >
            cancelar
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className={[
              'flex-1 min-h-[56px] font-bold text-sm uppercase tracking-wide',
              canSubmit
                ? 'bg-gray-900 text-white active:opacity-70'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed',
            ].join(' ')}
          >
            {createMutation.isPending ? 'guardando...' : 'guardar orden — abierta'}
          </button>
        </footer>
      </form>

      {/* Toast */}
      {toast.visible && (
        <div
          role="alert"
          aria-live="assertive"
          className="fixed top-4 left-4 right-4 z-50 bg-red-600 text-white px-4 py-3 text-sm font-medium"
        >
          {toast.message}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Item row sub-component
// ---------------------------------------------------------------------------

interface ItemRowProps {
  item: OrderItem
  products: import('../lib/types').Product[]
  chosenProductIds: Set<string>
  onProductSelect: (productId: string) => void
  onQtyChange: (value: string) => void
  onCostChange: (value: string) => void
  onRemove: () => void
  canRemove: boolean
}

function ItemRow({
  item,
  products,
  chosenProductIds,
  onProductSelect,
  onQtyChange,
  onCostChange,
  onRemove,
  canRemove,
}: ItemRowProps) {
  const total = lineTotal(item)

  return (
    <div className="grid grid-cols-[1fr_80px_80px_110px_70px_40px] gap-2 items-center bg-white border border-gray-200 px-2 py-2">
      {/* Product select */}
      <select
        value={item.product_id}
        onChange={(e) => onProductSelect(e.target.value)}
        className="min-h-[44px] px-2 border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-gray-900 w-full"
        aria-label="Elegir producto"
        required
      >
        <option value="">elegir producto...</option>
        {products.map((p) => (
          <option
            key={p.id}
            value={p.id}
            disabled={chosenProductIds.has(p.id) && p.id !== item.product_id}
          >
            {p.name}
          </option>
        ))}
      </select>

      {/* Qty */}
      <input
        type="number"
        inputMode="decimal"
        min="0.001"
        step="any"
        value={item.qty}
        onChange={(e) => onQtyChange(e.target.value)}
        placeholder="0"
        className="min-h-[44px] px-2 border border-gray-300 text-sm text-center focus:outline-none focus:ring-2 focus:ring-gray-900 w-full"
        aria-label="Cantidad"
        required
      />

      {/* Unit — readonly */}
      <input
        type="text"
        readOnly
        value={item.unit}
        className="min-h-[44px] px-2 border border-gray-200 bg-gray-100 text-sm text-center text-gray-500 w-full"
        aria-label="Unidad"
        tabIndex={-1}
      />

      {/* Cost */}
      <input
        type="number"
        inputMode="decimal"
        min="0.01"
        step="0.01"
        value={item.cost}
        onChange={(e) => onCostChange(e.target.value)}
        placeholder="0.00"
        className="min-h-[44px] px-2 border border-gray-300 text-sm text-right focus:outline-none focus:ring-2 focus:ring-gray-900 w-full"
        aria-label="Costo unitario"
        required
      />

      {/* Line total */}
      <span className="text-sm text-gray-600 text-right tabular-nums">
        {total > 0 ? formatSoles(total) : '—'}
      </span>

      {/* Remove */}
      <button
        type="button"
        onClick={onRemove}
        disabled={!canRemove}
        className={[
          'min-h-[44px] min-w-[40px] flex items-center justify-center text-lg font-bold',
          canRemove ? 'text-gray-500 active:text-red-600' : 'text-gray-300 cursor-not-allowed',
        ].join(' ')}
        aria-label="Eliminar fila"
      >
        —
      </button>
    </div>
  )
}
