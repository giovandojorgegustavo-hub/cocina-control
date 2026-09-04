import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { isAxiosError } from 'axios'
import { useProducts } from '../lib/products'
import {
  finalPrice,
  usePromotions,
  useUpdateProductPricing,
  useUpdatePromotion,
} from '../lib/pricing'
import { useAuthWithGetters } from '../lib/auth'
import { formatSoles } from '../lib/currency'
import { ErrorBanner } from '../components/ErrorBanner'
import type { Product, Promotion } from '../lib/types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function errorMessage(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  return fallback
}

const inputClass =
  'w-full px-3 py-2 border border-gray-300 bg-white text-right text-base focus:outline-none focus:ring-2 focus:ring-gray-900 min-h-[44px]'

const saveButtonClass = (enabled: boolean) =>
  [
    'min-h-[44px] px-4 text-sm font-bold uppercase tracking-wide',
    enabled ? 'bg-gray-900 text-white active:opacity-70' : 'bg-gray-200 text-gray-400 cursor-not-allowed',
  ].join(' ')

// ---------------------------------------------------------------------------
// Fila de producto
// ---------------------------------------------------------------------------

interface ProductRowProps {
  product: Product
  onError: (message: string) => void
}

function ProductRow({ product, onError }: ProductRowProps) {
  const [price, setPrice] = useState(product.sale_price ?? '')
  const [discount, setDiscount] = useState(product.discount_percent ?? '')
  const [saved, setSaved] = useState(false)
  const mutation = useUpdateProductPricing()

  // Cuando llega una version nueva del catalogo (otro usuario guardo), la fila
  // se vuelve a alinear con el servidor salvo que se este editando.
  useEffect(() => {
    setPrice(product.sale_price ?? '')
    setDiscount(product.discount_percent ?? '')
  }, [product.sale_price, product.discount_percent])

  const dirty =
    price.trim() !== (product.sale_price ?? '') ||
    discount.trim() !== (product.discount_percent ?? '')
  const computed = price.trim() === '' ? null : finalPrice(price, discount)
  const valid = price.trim() === '' || computed !== null
  const canSave = dirty && valid && !mutation.isPending

  function handleSave() {
    if (!canSave) return
    setSaved(false)
    mutation.mutate(
      {
        productId: product.id,
        input: {
          sale_price: price.trim() === '' ? null : price.trim(),
          discount_percent: discount.trim() === '' ? null : discount.trim(),
        },
      },
      {
        onSuccess: () => {
          setSaved(true)
          setTimeout(() => setSaved(false), 3000)
        },
        onError: (err) => {
          onError(errorMessage(err, `No se pudo guardar el precio de ${product.name}.`))
        },
      },
    )
  }

  return (
    <tr className="border-b border-gray-100">
      <td className="px-3 py-2 font-semibold text-gray-900">{product.name}</td>
      <td className="px-3 py-2 w-32">
        <input
          type="number"
          inputMode="decimal"
          step="0.10"
          min="0"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          aria-label={`Precio de ${product.name}`}
          className={inputClass}
        />
      </td>
      <td className="px-3 py-2 w-28">
        <input
          type="number"
          inputMode="numeric"
          step="1"
          min="0"
          max="99.99"
          value={discount}
          onChange={(e) => setDiscount(e.target.value)}
          aria-label={`Descuento de ${product.name}`}
          className={inputClass}
        />
      </td>
      <td className="px-3 py-2 text-right font-bold text-gray-900 whitespace-nowrap">
        {computed === null ? <span className="text-gray-400">—</span> : formatSoles(computed)}
      </td>
      <td className="px-3 py-2 text-right whitespace-nowrap">
        <div className="flex items-center justify-end gap-2">
          {saved && (
            <span role="status" className="text-xs text-green-700 font-semibold">
              Guardado
            </span>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            className={saveButtonClass(canSave)}
          >
            {mutation.isPending ? 'guardando...' : 'Guardar'}
          </button>
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Fila de promocion
// ---------------------------------------------------------------------------

interface PromotionRowProps {
  promotion: Promotion
  onError: (message: string) => void
}

function PromotionRow({ promotion, onError }: PromotionRowProps) {
  const [percent, setPercent] = useState(promotion.percent)
  const [firstOnly, setFirstOnly] = useState(promotion.first_order_only)
  const [active, setActive] = useState(promotion.is_active)
  const [saved, setSaved] = useState(false)
  const mutation = useUpdatePromotion()

  useEffect(() => {
    setPercent(promotion.percent)
    setFirstOnly(promotion.first_order_only)
    setActive(promotion.is_active)
  }, [promotion.percent, promotion.first_order_only, promotion.is_active])

  const percentNumber = parseFloat(percent)
  const percentValid = isFinite(percentNumber) && percentNumber > 0 && percentNumber < 100
  const dirty =
    percent.trim() !== promotion.percent ||
    firstOnly !== promotion.first_order_only ||
    active !== promotion.is_active
  const canSave = dirty && percentValid && !mutation.isPending

  function handleSave() {
    if (!canSave) return
    setSaved(false)
    mutation.mutate(
      {
        code: promotion.code,
        input: { percent: percent.trim(), first_order_only: firstOnly, is_active: active },
      },
      {
        onSuccess: () => {
          setSaved(true)
          setTimeout(() => setSaved(false), 3000)
        },
        onError: (err) => {
          onError(errorMessage(err, `No se pudo guardar la promoción ${promotion.name}.`))
        },
      },
    )
  }

  return (
    <tr className="border-b border-gray-100">
      <td className="px-3 py-2">
        <div className="font-semibold text-gray-900">{promotion.name}</div>
        <div className="text-xs text-gray-500 font-mono">{promotion.code}</div>
      </td>
      <td className="px-3 py-2 w-28">
        <input
          type="number"
          inputMode="numeric"
          step="1"
          min="0"
          max="99.99"
          value={percent}
          onChange={(e) => setPercent(e.target.value)}
          aria-label={`Porcentaje de ${promotion.name}`}
          className={inputClass}
        />
      </td>
      <td className="px-3 py-2 text-center">
        <input
          type="checkbox"
          checked={firstOnly}
          onChange={(e) => setFirstOnly(e.target.checked)}
          aria-label={`Solo primera compra — ${promotion.name}`}
          className="h-6 w-6 accent-gray-900"
        />
      </td>
      <td className="px-3 py-2 text-center">
        <input
          type="checkbox"
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
          aria-label={`Activa — ${promotion.name}`}
          className="h-6 w-6 accent-gray-900"
        />
      </td>
      <td className="px-3 py-2 text-right whitespace-nowrap">
        <div className="flex items-center justify-end gap-2">
          {saved && (
            <span role="status" className="text-xs text-green-700 font-semibold">
              Guardado
            </span>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            className={saveButtonClass(canSave)}
          >
            {mutation.isPending ? 'guardando...' : 'Guardar'}
          </button>
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const thClass = 'px-3 py-2 font-semibold text-gray-600 uppercase text-xs'

export function Precios() {
  const navigate = useNavigate()
  const { role } = useAuthWithGetters()
  const backTo = role === 'owner' ? '/tablero' : '/'

  const {
    data: products,
    isLoading: productsLoading,
    isError: productsError,
    refetch: refetchProducts,
  } = useProducts('sale')
  const {
    data: promotions,
    isLoading: promotionsLoading,
    isError: promotionsError,
    refetch: refetchPromotions,
  } = usePromotions()

  const [error, setError] = useState<string | null>(null)

  const loadError = productsError || promotionsError

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate(backTo)}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver"
        >
          &lt;
        </button>
        <h1 className="text-lg font-bold uppercase tracking-wide">PRECIOS Y DESCUENTOS</h1>
      </header>

      <main className="flex-1 px-4 py-6 space-y-8 overflow-y-auto pb-24">
        {/* Carta */}
        <section aria-label="Precios de la carta">
          <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-1">
            Precios de la carta
          </h2>
          <p className="text-sm text-gray-500 mb-3">
            El precio final es el que cobra el asistente de WhatsApp. Un descuento vacío o 0
            significa sin descuento.
          </p>
          {productsLoading && (
            <p role="status" className="text-sm text-gray-400">
              Cargando carta...
            </p>
          )}
          {products && products.length === 0 && (
            <p className="text-sm text-gray-400">No hay productos de venta en el catálogo.</p>
          )}
          {products && products.length > 0 && (
            <div className="overflow-x-auto bg-white border border-gray-200 rounded-lg">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className={`${thClass} text-left`}>Plato</th>
                    <th className={`${thClass} text-right`}>Precio (S/)</th>
                    <th className={`${thClass} text-right`}>Descuento (%)</th>
                    <th className={`${thClass} text-right`}>Precio final</th>
                    <th className={thClass}>
                      <span className="sr-only">Acciones</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((product) => (
                    <ProductRow key={product.id} product={product} onError={setError} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Promociones */}
        <section aria-label="Promociones">
          <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-1">
            Promociones
          </h2>
          <p className="text-sm text-gray-500 mb-3">
            El asistente de WhatsApp aplica <span className="font-mono">primera_compra</span>{' '}
            automáticamente cuando el cliente menciona el descuento y es su primer pedido.
          </p>
          {promotionsLoading && (
            <p role="status" className="text-sm text-gray-400">
              Cargando promociones...
            </p>
          )}
          {promotions && promotions.length === 0 && (
            <p className="text-sm text-gray-400">No hay promociones cargadas.</p>
          )}
          {promotions && promotions.length > 0 && (
            <div className="overflow-x-auto bg-white border border-gray-200 rounded-lg">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className={`${thClass} text-left`}>Nombre</th>
                    <th className={`${thClass} text-right`}>Porcentaje</th>
                    <th className={`${thClass} text-center`}>Solo primera compra</th>
                    <th className={`${thClass} text-center`}>Activa</th>
                    <th className={thClass}>
                      <span className="sr-only">Acciones</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {promotions.map((promotion) => (
                    <PromotionRow key={promotion.code} promotion={promotion} onError={setError} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>

      {loadError && (
        <ErrorBanner
          message="No se pudieron cargar los precios."
          onRetry={() => {
            void refetchProducts()
            void refetchPromotions()
          }}
        />
      )}
      {!loadError && error && (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      )}
    </div>
  )
}
