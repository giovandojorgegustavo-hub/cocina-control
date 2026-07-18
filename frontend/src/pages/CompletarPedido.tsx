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
import { useProducts, useCreateProduct } from '../lib/products'
import { useAuthWithGetters } from '../lib/auth'
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
// Alta inline de producto de venta (issues #139/#140): bowls, cubiertos,
// cremas... se crean desde el propio pedido. Solo owner/admin (el backend
// exige ese rol); el producto nace como venta pura (is_sale, sin compra).
// ---------------------------------------------------------------------------

function NuevaVentaCard({
  createProduct,
  onCreated,
}: {
  createProduct: ReturnType<typeof useCreateProduct>
  onCreated: (p: Product) => void
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [unit, setUnit] = useState('un')
  const [failed, setFailed] = useState(false)

  async function handleCrear() {
    if (!name.trim() || createProduct.isPending) return
    setFailed(false)
    try {
      const created = await createProduct.mutateAsync({
        name: name.trim(),
        unit,
        is_purchase: false,
        is_sale: true,
      })
      onCreated(created)
      setName('')
      setOpen(false)
    } catch {
      setFailed(true)
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="min-h-[96px] border-2 border-dashed border-gray-400 text-gray-600 flex flex-col items-center justify-center gap-1 active:bg-gray-100"
        aria-label="Crear producto de venta"
      >
        <span className="text-2xl font-black leading-none">+</span>
        <span className="text-sm font-semibold">nuevo</span>
      </button>
    )
  }

  return (
    <div className="col-span-3 border-2 border-gray-900 bg-gray-50 p-3 flex flex-col gap-2">
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="nombre del producto de venta"
        aria-label="Nombre del producto de venta"
        autoFocus
        className="min-h-[44px] px-2 border border-gray-300 text-sm w-full focus:outline-none focus:ring-2 focus:ring-gray-900"
      />
      <div className="flex gap-2">
        <select
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          aria-label="Unidad del producto de venta"
          className="min-h-[44px] px-2 border-2 border-gray-900 bg-white text-sm"
        >
          <option value="un">un</option>
          <option value="kg">kg</option>
          <option value="lt">lt</option>
        </select>
        <button
          type="button"
          onClick={handleCrear}
          disabled={!name.trim() || createProduct.isPending}
          className={[
            'flex-1 min-h-[44px] text-sm font-bold uppercase',
            name.trim() && !createProduct.isPending
              ? 'bg-gray-900 text-white active:opacity-80'
              : 'bg-gray-200 text-gray-400',
          ].join(' ')}
        >
          {createProduct.isPending ? 'creando...' : 'crear'}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="min-h-[44px] px-3 text-sm text-gray-600 border border-gray-300"
        >
          cancelar
        </button>
      </div>
      {failed && (
        <p className="text-xs text-red-600">no se pudo crear — proba de nuevo</p>
      )}
    </div>
  )
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
  } = useProducts('sale')

  const completeOrder = useCompleteOrder(id ?? '')
  const createProduct = useCreateProduct()
  const { role } = useAuthWithGetters()
  // el backend exige owner/admin para crear productos; el cocinero no ve el +
  const canCreateSale = role === 'owner' || role === 'admin'

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

          {!isLoading && products && (products.length > 0 || canCreateSale) && (
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
              {canCreateSale && (
                <NuevaVentaCard createProduct={createProduct} onCreated={handleTap} />
              )}
            </div>
          )}

          {!isLoading && products && products.length === 0 && !canCreateSale && (
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
