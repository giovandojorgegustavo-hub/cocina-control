/**
 * /inventario/contar/:productId — Pantalla 2: Contar un producto
 *
 * Two modes driven by an optional ?item_id=X query param:
 *   - No item_id → new count: POST /inventory-counts/{id}/items
 *   - item_id present → correction: POST /inventory-counts/{id}/items/{itemId}/correct
 *
 * Principio #1: NEVER show expected values, previous stock, averages, or
 * differences. The only exception: when correcting, a banner shows the
 * previous value — that is the fact being corrected, not an analysis.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useProducts } from '../lib/products'
import {
  getSavedCountId,
  useInventoryCount,
  useAddInventoryItem,
  useCorrectInventoryItem,
} from '../lib/inventory'
import { useAuthWithGetters } from '../lib/auth'
import type { InventoryCountItem } from '../lib/types'

// ---------------------------------------------------------------------------
// Quantity validation — mirrors the guard in Verificacion.tsx
// ---------------------------------------------------------------------------

function parseQty(raw: string): number | null {
  const parsed = parseFloat(raw.replace(',', '.'))
  if (!isFinite(parsed) || parsed < 0) return null
  return parsed
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function ContarProducto() {
  const { productId } = useParams<{ productId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { userId } = useAuthWithGetters()

  const itemId = searchParams.get('item_id') // present when correcting
  const isCorrection = itemId !== null

  const countId = userId ? getSavedCountId(userId) : null

  const { data: products } = useProducts()
  const { data: count } = useInventoryCount(countId)

  const addItem = useAddInventoryItem()
  const correctItem = useCorrectInventoryItem()

  const product = products?.find((p) => p.id === productId)

  // The item being corrected (to show previous value in banner)
  const previousItem: InventoryCountItem | undefined = count?.items.find(
    (i) => i.id === itemId,
  )

  // Input state
  const [value, setValue] = useState<string>('')
  const inputRef = useRef<HTMLInputElement>(null)

  // Pre-load input with current value when correcting
  useEffect(() => {
    if (isCorrection && previousItem !== undefined) {
      setValue(String(previousItem.quantity))
    }
  }, [isCorrection, previousItem])

  // Auto-focus on mount
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus()
    }
  }, [])

  // Toast for save errors (quantity is NOT cleared on error)
  const [toast, setToast] = useState<{ visible: boolean; message: string }>({
    visible: false,
    message: '',
  })

  useEffect(() => {
    if (!toast.visible) return
    const t = setTimeout(() => setToast({ visible: false, message: '' }), 3000)
    return () => clearTimeout(t)
  }, [toast.visible])

  // ---------------------------------------------------------------------------
  // Derived: next pending product for SIGUIENTE navigation
  // ---------------------------------------------------------------------------

  const nextPendingProductId = useCallback((): string | null => {
    if (!products || !count) return null

    const countedIds = new Set(count.items.map((i) => i.product_id))
    const pending = products
      .filter((p) => !countedIds.has(p.id))
      .sort((a, b) => a.name.localeCompare(b.name))

    // If correcting, the current product is already counted — find first pending that is not it
    // If counting new, the current product is not yet counted — skip it in SIGUIENTE
    const nextList = pending.filter((p) => p.id !== productId)

    // After saving a new count the current product moves to counted, so the raw
    // pending list (before save) still includes it. We filter it out here so
    // SIGUIENTE always goes to a different product.
    return nextList[0]?.id ?? null
  }, [products, count, productId])

  // ---------------------------------------------------------------------------
  // Save handler
  // ---------------------------------------------------------------------------

  const handleSave = useCallback(
    (
      qty: number,
      afterSave: (savedProductId: string) => void,
    ) => {
      if (!countId || !productId) return

      const onError = () => {
        setToast({ visible: true, message: 'No se pudo guardar. Intentá de nuevo.' })
        // Value is kept in input — principio de no perder lo tipeado
      }

      if (isCorrection && itemId) {
        correctItem.mutate(
          { countId, itemId, payload: { quantity: qty } },
          {
            onSuccess: () => afterSave(productId),
            onError,
          },
        )
      } else {
        addItem.mutate(
          { countId, payload: { product_id: productId, quantity: qty } },
          {
            onSuccess: () => afterSave(productId),
            onError,
          },
        )
      }
    },
    [countId, productId, isCorrection, itemId, correctItem, addItem],
  )

  const isPending = addItem.isPending || correctItem.isPending

  const handleSiguiente = useCallback(() => {
    const qty = parseQty(value)
    if (qty === null || isPending) return

    const nextId = nextPendingProductId()

    handleSave(qty, () => {
      if (nextId) {
        navigate(`/inventario/contar/${nextId}`)
      } else {
        navigate('/inventario')
      }
    })
  }, [value, isPending, nextPendingProductId, handleSave, navigate])

  const handleOkYVolver = useCallback(() => {
    const qty = parseQty(value)
    if (qty === null || isPending) return

    handleSave(qty, () => {
      navigate('/inventario')
    })
  }, [value, isPending, handleSave, navigate])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') handleSiguiente()
    },
    [handleSiguiente],
  )

  const parsedQty = parseQty(value)
  const isValid = parsedQty !== null

  // ---------------------------------------------------------------------------
  // Guards
  // ---------------------------------------------------------------------------

  if (!productId || !countId) {
    return null
  }

  // ---------------------------------------------------------------------------
  // Product not found in catalogue
  // ---------------------------------------------------------------------------

  if (products && !product) {
    return (
      <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
        <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
          <button
            onClick={() => navigate('/inventario')}
            className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
            aria-label="Volver"
          >
            &lt;
          </button>
          <h1 className="text-base font-bold uppercase tracking-wide">INVENTARIO</h1>
        </header>
        <main className="flex-1 flex items-center justify-center px-8 text-center">
          <p className="text-gray-700">Producto no encontrado.</p>
        </main>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate('/inventario')}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver a la lista"
        >
          &lt;
        </button>
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-400">INVENTARIO</p>
          <h1 className="text-base font-bold uppercase tracking-wide">
            {product?.name ?? '...'}
          </h1>
        </div>
      </header>

      {/* Correction banner — the only place where a previous value is shown */}
      {isCorrection && previousItem !== undefined && (
        <div
          data-testid="correction-banner"
          className="bg-yellow-50 border-b border-yellow-300 px-4 py-3"
          role="status"
        >
          <p className="text-sm font-semibold text-yellow-900 uppercase tracking-wide">
            CAMBIANDO — {product?.name ?? ''}{' '}
            <span className="font-normal normal-case">
              (antes: {previousItem.quantity} {product?.unit ?? ''})
            </span>
          </p>
        </div>
      )}

      {/* Input area */}
      <main className="flex-1 flex flex-col items-center justify-center px-8 gap-6">
        <p className="text-sm text-gray-600 uppercase tracking-wide">Cantidad que queda</p>

        <div className="flex items-center gap-3">
          <input
            ref={inputRef}
            data-testid="qty-input"
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder=""
            className="border-2 border-gray-900 text-4xl font-bold text-center w-40 py-4 focus:outline-none focus:border-blue-600"
            aria-label="Cantidad que queda"
          />
          <span className="text-lg text-gray-600">{product?.unit ?? ''}</span>
        </div>
      </main>

      {/* Action buttons */}
      <footer className="px-4 py-6 bg-white border-t border-gray-200 flex gap-3">
        {/* SIGUIENTE is the primary / larger button */}
        <button
          data-testid="btn-siguiente"
          onClick={handleSiguiente}
          disabled={!isValid || isPending}
          className={[
            'flex-[2] min-h-[56px] font-bold text-base uppercase tracking-wide',
            isValid && !isPending
              ? 'bg-gray-900 text-white active:opacity-70'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed',
          ].join(' ')}
        >
          {isPending ? 'guardando...' : 'SIGUIENTE →'}
        </button>

        <button
          data-testid="btn-ok-volver"
          onClick={handleOkYVolver}
          disabled={!isValid || isPending}
          className={[
            'flex-1 min-h-[56px] font-semibold text-sm border uppercase tracking-wide',
            isValid && !isPending
              ? 'border-gray-400 text-gray-700 bg-white active:opacity-70'
              : 'border-gray-200 text-gray-400 bg-gray-50 cursor-not-allowed',
          ].join(' ')}
        >
          OK y volver
        </button>
      </footer>

      {/* Toast for save errors */}
      {toast.visible && (
        <div
          role="alert"
          aria-live="assertive"
          className="fixed bottom-28 left-4 right-4 z-50 bg-red-600 text-white px-4 py-3 text-sm font-medium"
        >
          {toast.message}
        </div>
      )}
    </div>
  )
}
