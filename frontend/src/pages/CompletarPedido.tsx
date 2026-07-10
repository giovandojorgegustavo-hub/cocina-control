/**
 * Pantalla 4 — Completar pedido
 * Pantalla 5 — Terminado (confirmatorio)
 *
 * La foto queda visible mientras el operario selecciona productos.
 * Cada tarjeta de producto:
 *  - Tap 1: selecciona con ×1
 *  - Tap 2+: suma cantidad (×2, ×3...)
 *  - Tap en el badge de cantidad: resta (o deselecciona si llega a 0)
 *
 * "terminar pedido" exige mínimo 1 producto seleccionado.
 * "dejar solo foto por ahora" vuelve a la bandeja sin llamar al backend.
 */
import { useState, useCallback, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useOrder, useCompleteOrder } from '../lib/orders'
import { useProducts } from '../lib/products'
import { AuthImg } from '../components/AuthImg'
import { ErrorBanner } from '../components/ErrorBanner'
import { formatRelativeDate } from '../lib/date'
import type { Product } from '../lib/types'

// Same convention as src/lib/api.ts: VITE_API_URL wins if set; otherwise derive
// from BASE_URL so photo requests go to /interno/api/v1/... in production.
const BASE_URL = import.meta.env.VITE_API_URL || import.meta.env.BASE_URL.replace(/\/$/, '')

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ProductSelection {
  product: Product
  quantity: number
}

// ---------------------------------------------------------------------------
// Confirmed screen (Pantalla 5)
// ---------------------------------------------------------------------------

function TerminadoView({
  time,
  productCount,
}: {
  time: string
  productCount: number
}) {
  return (
    <div
      className="h-screen flex flex-col items-center justify-center bg-gray-900 text-white gap-6"
      role="status"
      aria-live="assertive"
      aria-label="Pedido terminado"
      data-testid="terminado-view"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 64 64"
        className="w-24 h-24"
        aria-hidden="true"
      >
        <circle cx="32" cy="32" r="30" fill="#16a34a" />
        <path
          d="M18 33 L28 43 L46 22"
          stroke="white"
          strokeWidth="5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>

      <div className="text-center">
        <p className="text-3xl font-black tracking-widest uppercase">PEDIDO TERMINADO</p>
        <p className="mt-3 text-gray-300 text-base">
          pedido de {time} — {productCount}{' '}
          {productCount === 1 ? 'producto' : 'productos'}
        </p>
      </div>

      <p className="text-gray-500 text-sm mt-4">volviendo a la bandeja...</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Product card
// ---------------------------------------------------------------------------

interface ProductCardProps {
  product: Product
  quantity: number
  onTap: (productId: string) => void
  onDecrease: (productId: string) => void
}

function ProductCard({ product, quantity, onTap, onDecrease }: ProductCardProps) {
  const isSelected = quantity > 0

  return (
    <button
      onClick={() => onTap(product.id)}
      aria-label={`${product.name}${isSelected ? `, cantidad ${quantity}` : ', sin seleccionar'}`}
      aria-pressed={isSelected}
      className={[
        'relative flex flex-col items-center justify-center',
        'min-h-[90px] px-2 py-4',
        'border-2',
        'active:scale-95 transition-transform duration-75',
        isSelected
          ? 'bg-gray-900 border-gray-900 text-white'
          : 'bg-white border-gray-200 text-gray-900',
      ].join(' ')}
    >
      <span className="text-sm font-black uppercase tracking-wide text-center leading-tight">
        {product.name}
      </span>

      {isSelected && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            onDecrease(product.id)
          }}
          aria-label={`Quitar una unidad de ${product.name}`}
          className={[
            'absolute top-1 right-1',
            'bg-gray-700 text-white text-xs font-bold',
            'px-2 py-1 rounded',
            'min-h-[32px] min-w-[32px]',
            'flex items-center justify-center',
            'active:bg-gray-500',
          ].join(' ')}
        >
          &times;{quantity}
        </button>
      )}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Product grid skeleton
// ---------------------------------------------------------------------------

function ProductSkeleton() {
  return (
    <div
      role="status"
      aria-label="Cargando productos"
      className="grid grid-cols-3 gap-2 p-4 animate-pulse"
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-20 bg-gray-200 rounded" />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function CompletarPedido() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const {
    data: order,
    isLoading: orderLoading,
    isError: orderError,
  } = useOrder(id ?? '')

  const {
    data: products,
    isLoading: productsLoading,
    isError: productsError,
  } = useProducts()

  const completeOrder = useCompleteOrder(id ?? '')

  const [selections, setSelections] = useState<Map<string, ProductSelection>>(new Map())
  const [screen, setScreen] = useState<'form' | 'confirmed'>('form')
  const [showError, setShowError] = useState(true)

  // Navigate back to bandeja 1.5 s after confirmation screen (H-09: with cleanup)
  useEffect(() => {
    if (screen !== 'confirmed') return
    const t = setTimeout(() => {
      navigate('/pedidos', { replace: true })
    }, 1500)
    return () => clearTimeout(t)
  }, [screen, navigate])

  const totalSelected = Array.from(selections.values()).reduce(
    (acc, s) => acc + s.quantity,
    0,
  )

  const handleTap = useCallback((product: Product) => {
    setSelections((prev) => {
      const next = new Map(prev)
      const existing = next.get(product.id)
      if (existing) {
        next.set(product.id, { product, quantity: existing.quantity + 1 })
      } else {
        next.set(product.id, { product, quantity: 1 })
      }
      return next
    })
  }, [])

  const handleDecrease = useCallback((productId: string) => {
    setSelections((prev) => {
      const next = new Map(prev)
      const existing = next.get(productId)
      if (!existing) return prev
      if (existing.quantity <= 1) {
        next.delete(productId)
      } else {
        next.set(productId, { ...existing, quantity: existing.quantity - 1 })
      }
      return next
    })
  }, [])

  async function handleTerminar() {
    if (totalSelected === 0 || !id) return

    const items = Array.from(selections.values()).map((s) => ({
      product_id: s.product.id,
      quantity: s.quantity,
    }))

    try {
      await completeOrder.mutateAsync({ items })
      setScreen('confirmed')
      // Navigation is handled by the useEffect above (H-09: cleanup on unmount)
    } catch {
      setShowError(true)
    }
  }

  function handleDejarSoloFoto() {
    navigate('/pedidos', { replace: true })
  }

  // Pantalla 5
  if (screen === 'confirmed' && order) {
    return (
      <TerminadoView
        time={formatRelativeDate(order.photo_at)}
        productCount={totalSelected}
      />
    )
  }

  const isLoading = orderLoading || productsLoading
  const isError = orderError || productsError || completeOrder.isError

  const photoSrc = id
    ? `${BASE_URL}/api/v1/delivery-orders/${id}/photo`
    : ''

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate('/pedidos')}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver a la bandeja"
        >
          &lt;
        </button>
        <h1 className="text-lg font-bold tracking-wide uppercase">
          COMPLETAR —{' '}
          {order ? `pedido de ${formatRelativeDate(order.photo_at)}` : 'cargando...'}
        </h1>
      </header>

      {/* Body — side by side on tablet, stacked on mobile */}
      <main className="flex-1 overflow-y-auto flex flex-col md:flex-row gap-px bg-gray-300">
        {/* Photo column */}
        <div className="bg-white md:w-48 flex-shrink-0 flex items-center justify-center p-2">
          {id && (
            <AuthImg
              src={photoSrc}
              alt="Foto del paquete"
              className="w-full h-40 md:h-full object-cover"
              data-testid="order-photo-completar"
            />
          )}
        </div>

        {/* Product grid column */}
        <div className="flex-1 bg-white">
          <p className="px-4 pt-4 pb-2 text-sm font-semibold text-gray-700">
            ¿que salio en este pedido? (minimo 1)
          </p>

          {isLoading && <ProductSkeleton />}

          {!isLoading && products && products.length > 0 && (
            <div className="grid grid-cols-3 gap-2 px-4 pb-4">
              {products.map((product) => {
                const sel = selections.get(product.id)
                return (
                  <ProductCard
                    key={product.id}
                    product={product}
                    quantity={sel?.quantity ?? 0}
                    onTap={() => handleTap(product)}
                    onDecrease={handleDecrease}
                  />
                )
              })}
            </div>
          )}

          {!isLoading && products && products.length === 0 && (
            <div className="px-4 py-8 text-center">
              <p className="text-gray-500 text-sm">
                No hay productos en el catalogo. Pedile al dueno que los cargue.
              </p>
            </div>
          )}
        </div>
      </main>

      {/* Footer actions */}
      <footer className="flex-shrink-0 bg-white border-t border-gray-200 px-4 py-4 flex items-center justify-between gap-4">
        <button
          onClick={handleDejarSoloFoto}
          className="text-gray-500 text-sm underline min-h-[48px] px-2"
          aria-label="Dejar solo foto y volver a la bandeja"
          data-testid="dejar-solo-foto"
        >
          dejar solo foto por ahora
        </button>

        <button
          onClick={() => { void handleTerminar() }}
          disabled={totalSelected === 0 || completeOrder.isPending}
          aria-label={`Terminar pedido con ${totalSelected} productos`}
          aria-disabled={totalSelected === 0}
          data-testid="terminar-pedido"
          className={[
            'bg-gray-900 text-white font-bold text-sm uppercase tracking-wide',
            'px-5 py-4 min-h-[56px]',
            'active:opacity-70',
            totalSelected === 0 || completeOrder.isPending
              ? 'opacity-40 cursor-not-allowed'
              : '',
          ].join(' ')}
        >
          {completeOrder.isPending
            ? 'guardando...'
            : `terminar pedido${totalSelected > 0 ? ` (${totalSelected} producto${totalSelected !== 1 ? 's' : ''})` : ''}`}
        </button>
      </footer>

      {isError && showError && (
        <ErrorBanner
          message="Error al completar el pedido. Intenta de nuevo."
          onDismiss={() => setShowError(false)}
          onRetry={() => {
            setShowError(false)
            void handleTerminar() // eslint-disable-line @typescript-eslint/no-floating-promises
          }}
        />
      )}
    </div>
  )
}
