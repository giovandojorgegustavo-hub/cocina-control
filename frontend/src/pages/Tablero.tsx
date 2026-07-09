import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthWithGetters } from '../lib/auth'
import { apiClient } from '../lib/api'
import { useDashboardSummary, downloadCsv, CsvAuthError } from '../lib/dashboard'
import { usePeriod } from '../lib/usePeriod'
import { PeriodSelector } from '../components/PeriodSelector'
import { Semaforo, stockLevel } from '../components/Semaforo'
import { ErrorBanner } from '../components/ErrorBanner'
import type { DashboardProduct, DashboardLowStockItem } from '../lib/types'

// ---------------------------------------------------------------------------
// Skeletons
// ---------------------------------------------------------------------------

function SkeletonWidget({ height = 140 }: { height?: number }) {
  return (
    <div
      role="status"
      aria-label="Cargando widget"
      className="bg-white border border-gray-200 rounded-lg p-4 animate-pulse"
      style={{ minHeight: height }}
    >
      <div className="h-4 bg-gray-200 rounded w-1/3 mb-3" />
      <div className="h-3 bg-gray-100 rounded w-2/3 mb-2" />
      <div className="h-3 bg-gray-100 rounded w-1/2 mb-2" />
      <div className="h-3 bg-gray-100 rounded w-3/4" />
    </div>
  )
}

function SkeletonTable() {
  return (
    <div
      role="status"
      aria-label="Cargando tabla"
      className="bg-white border border-gray-200 rounded-lg p-4 animate-pulse"
    >
      <div className="h-4 bg-gray-200 rounded w-1/4 mb-4" />
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="flex gap-4 mb-3">
          <div className="h-3 bg-gray-100 rounded flex-1" />
          <div className="h-3 bg-gray-100 rounded w-16" />
          <div className="h-3 bg-gray-100 rounded w-16" />
          <div className="h-3 bg-gray-100 rounded w-16" />
          <div className="h-3 bg-gray-100 rounded w-12" />
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Low stock widget
// ---------------------------------------------------------------------------

interface LowStockWidgetProps {
  items: DashboardLowStockItem[]
  onVerTodos: () => void
}

function LowStockWidget({ items, onVerTodos }: LowStockWidgetProps) {
  const top5 = items.slice(0, 5)

  return (
    <section
      aria-label="Productos por acabarse"
      className="bg-white border border-gray-200 rounded-lg p-4 flex flex-col gap-2"
    >
      <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-1">
        Por acabarse
      </h2>
      {top5.length === 0 ? (
        <p className="text-sm text-gray-400">Sin productos bajo umbral.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {top5.map((item) => {
            const level = stockLevel(item.stock_now, item.low_stock_threshold)
            return (
              <li key={item.product_id} className="flex items-center gap-2">
                <Semaforo level={level} />
                <span className="font-bold text-sm text-gray-900 flex-1">{item.name}</span>
                <span className="text-sm text-gray-500">
                  {item.stock_now} {item.unit}
                </span>
              </li>
            )
          })}
        </ul>
      )}
      {items.length > 5 && (
        <button
          onClick={onVerTodos}
          className="mt-1 text-xs text-gray-500 underline text-left min-h-[44px] flex items-center"
        >
          ver todos
        </button>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Orders summary widget
// ---------------------------------------------------------------------------

interface OrdersWidgetProps {
  completed: number
  photoOnly: number
}

function OrdersWidget({ completed, photoOnly }: OrdersWidgetProps) {
  return (
    <section
      aria-label="Pedidos en el periodo"
      className="bg-white border border-gray-200 rounded-lg p-4 flex flex-col gap-2"
    >
      <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-1">
        Pedidos en el periodo
      </h2>
      <div className="flex flex-col gap-1">
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-700">Terminados (con detalle)</span>
          <span className="text-xl font-bold text-gray-900" aria-label={`${completed} pedidos terminados`}>
            {completed}
          </span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-700">Solo foto</span>
          <span className="text-xl font-bold text-gray-900" aria-label={`${photoOnly} pedidos solo foto`}>
            {photoOnly}
          </span>
        </div>
        <div className="border-t border-gray-200 mt-1 pt-1 flex justify-between items-center">
          <span className="text-sm font-semibold text-gray-700">Total</span>
          <span className="text-xl font-bold text-gray-900">
            {completed + photoOnly}
          </span>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Product table — desktop
// ---------------------------------------------------------------------------

interface ProductTableProps {
  products: DashboardProduct[]
  onRowClick: (productId: string) => void
  filterLowStock: boolean
}

function sortProducts(products: DashboardProduct[]): DashboardProduct[] {
  return [...products].sort((a, b) => {
    // Alerts first descending
    const alertDiff = Number(b.alert) - Number(a.alert)
    if (alertDiff !== 0) return alertDiff
    // Then by consumption descending (null consumption goes last)
    const aC = a.consumption ?? -Infinity
    const bC = b.consumption ?? -Infinity
    return bC - aC
  })
}

function AlertCell({ product }: { product: DashboardProduct }) {
  const hasThreshold = product.low_stock_threshold !== null
  const isBelowThreshold = hasThreshold && product.stock_now < product.low_stock_threshold!

  if (product.alert) {
    return (
      <span className="flex items-center gap-1">
        <span aria-label="advertencia" className="text-orange-500 font-bold">!</span>
        {isBelowThreshold && (
          <>
            <Semaforo level={stockLevel(product.stock_now, product.low_stock_threshold!)} size={8} />
            <span className="text-xs text-gray-600">por acabar</span>
          </>
        )}
      </span>
    )
  }

  if (isBelowThreshold) {
    return (
      <span className="flex items-center gap-1">
        <Semaforo level={stockLevel(product.stock_now, product.low_stock_threshold!)} size={8} />
        <span className="text-xs text-gray-600">por acabar</span>
      </span>
    )
  }

  return null
}

function ProductTable({ products, onRowClick, filterLowStock }: ProductTableProps) {
  const sorted = sortProducts(products)
  const visible = filterLowStock
    ? sorted.filter(
        (p) => p.low_stock_threshold !== null && p.stock_now < p.low_stock_threshold,
      )
    : sorted

  return (
    <section aria-label="Consumo y stock por producto">
      <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-2">
        Consumo y stock por producto
        {filterLowStock && (
          <span className="ml-2 text-orange-500">(filtrando bajo umbral)</span>
        )}
      </h2>

      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-3 py-2 font-semibold text-gray-600 uppercase text-xs">
                Producto
              </th>
              <th className="text-right px-3 py-2 font-semibold text-gray-600 uppercase text-xs">
                Stock ahora
              </th>
              <th className="text-right px-3 py-2 font-semibold text-gray-600 uppercase text-xs">
                Entradas
              </th>
              <th className="text-right px-3 py-2 font-semibold text-gray-600 uppercase text-xs">
                Consumo (diff)
              </th>
              <th className="text-left px-3 py-2 font-semibold text-gray-600 uppercase text-xs">
                Alerta
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((product) => (
              <tr
                key={product.product_id}
                onClick={() => onRowClick(product.product_id)}
                className="border-b border-gray-100 cursor-pointer hover:bg-gray-50 active:bg-gray-100"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') onRowClick(product.product_id)
                }}
                role="button"
                aria-label={`Ver trazabilidad de ${product.name}`}
              >
                <td className="px-3 py-3 font-semibold text-gray-900">{product.name}</td>
                <td className="px-3 py-3 text-right text-gray-700">
                  {product.stock_now} {product.unit}
                </td>
                <td className="px-3 py-3 text-right text-gray-700">
                  {product.entries} {product.unit}
                </td>
                <td className="px-3 py-3 text-right text-gray-700">
                  {product.consumption_available ? (
                    <>
                      {product.consumption} {product.unit}
                    </>
                  ) : (
                    <span className="text-gray-400 text-xs">sin dato de inicio</span>
                  )}
                </td>
                <td className="px-3 py-3">
                  <AlertCell product={product} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden flex flex-col gap-2">
        {visible.map((product) => (
          <button
            key={product.product_id}
            onClick={() => onRowClick(product.product_id)}
            className="w-full text-left bg-white border border-gray-200 rounded-lg p-4 active:bg-gray-50"
            aria-label={`Ver trazabilidad de ${product.name}`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="font-bold text-gray-900">{product.name}</span>
              <AlertCell product={product} />
            </div>
            <div className="text-sm text-gray-600 flex flex-wrap gap-x-4 gap-y-1">
              <span>
                stock <strong>{product.stock_now} {product.unit}</strong>
              </span>
              <span>
                entradas <strong>{product.entries} {product.unit}</strong>
              </span>
              <span>
                consumo{' '}
                {product.consumption_available ? (
                  <strong>
                    {product.consumption} {product.unit}
                  </strong>
                ) : (
                  <span className="text-gray-400">sin dato de inicio</span>
                )}
              </span>
            </div>
          </button>
        ))}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState({ onPreset }: { onPreset: (p: 'today' | '7d' | '30d') => void }) {
  return (
    <div
      className="flex flex-col items-center justify-center py-16 px-4 text-center"
      aria-label="Sin registros en el periodo"
    >
      <p className="text-gray-700 text-lg font-medium mb-1">
        Todavia no hay registros en este periodo.
      </p>
      <p className="text-gray-500 text-sm mb-6">
        Cambia el rango o espera a que el operario registre algo.
      </p>
      <div className="flex gap-3 flex-wrap justify-center">
        <button
          onClick={() => onPreset('7d')}
          className="px-5 py-2 bg-gray-900 text-white text-sm font-semibold rounded min-h-[44px]"
        >
          ver 7 dias
        </button>
        <button
          onClick={() => onPreset('30d')}
          className="px-5 py-2 border border-gray-900 text-gray-900 text-sm font-semibold rounded min-h-[44px]"
        >
          ver 30 dias
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Offline banner with stale data timestamp
// ---------------------------------------------------------------------------

interface OfflineStaleBannerProps {
  dataUpdatedAt: number
}

function OfflineStaleBanner({ dataUpdatedAt }: OfflineStaleBannerProps) {
  const minutesAgo = Math.round((Date.now() - dataUpdatedAt) / 60_000)
  const label =
    minutesAgo < 1
      ? 'hace menos de un minuto'
      : minutesAgo === 1
        ? 'hace 1 min'
        : `hace ${minutesAgo} min`

  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-orange-500 text-white text-sm font-medium px-4 py-3 text-center"
    >
      Sin conexion — mostrando datos guardados (ultima sync: {label})
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Tablero() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { userId, clearToken } = useAuthWithGetters()

  // usePeriod needs last_inventory_at to compute the "HOY" range correctly.
  // We seed it from the summary response once it arrives.
  const [lastInventoryAt, setLastInventoryAt] = useState<string | null>(null)
  const period = usePeriod('7d', lastInventoryAt)

  const {
    data,
    isLoading,
    isError,
    refetch: summaryRefetch,
    dataUpdatedAt,
  } = useDashboardSummary(userId, period.from, period.to)

  // Sync last_inventory_at from summary so "HOY" re-computes after first load.
  if (data?.last_inventory_at && data.last_inventory_at !== lastInventoryAt) {
    setLastInventoryAt(data.last_inventory_at)
  }

  const [showError, setShowError] = useState(true)
  const [csvError, setCsvError] = useState<string | null>(null)
  const [filterLowStock, setFilterLowStock] = useState(false)
  const [csvLoading, setCsvLoading] = useState(false)

  const isOfflineWithData = !navigator.onLine && data !== undefined && dataUpdatedAt > 0

  // Reset error banner each time a new error arrives.
  // Retry both summary (traceability is not on this page).
  function handleRetry() {
    setShowError(true)
    void summaryRefetch()
  }

  async function handleDownloadCsv() {
    setCsvLoading(true)
    setCsvError(null)
    try {
      await downloadCsv(period.from, period.to, 'all')
    } catch (err) {
      if (err instanceof CsvAuthError) {
        // Token expired or missing — clear session and redirect to login.
        clearToken()
        queryClient.clear()
        navigate('/login', { replace: true })
        return
      }
      setCsvError('No se pudo descargar el CSV. Proba de nuevo.')
    } finally {
      setCsvLoading(false)
    }
  }

  async function handleLogout() {
    try {
      await apiClient.post('/auth/logout')
    } catch {
      // best-effort
    }
    queryClient.clear()
    navigate('/login', { replace: true })
  }

  const isEmpty =
    !isLoading &&
    !isError &&
    data !== undefined &&
    data.products.length === 0 &&
    data.orders_summary.completed_count === 0 &&
    data.orders_summary.photo_only_count === 0

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Offline banner — shown at the top when offline and stale data is cached */}
      {isOfflineWithData && <OfflineStaleBanner dataUpdatedAt={dataUpdatedAt} />}

      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center justify-between flex-shrink-0">
        <h1 className="text-lg font-bold tracking-wide">Cocina Control — Tablero</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-300">{userId ?? 'dueno'}</span>
          <button
            onClick={handleLogout}
            className="min-h-[48px] min-w-[48px] px-4 text-sm text-gray-300 underline"
          >
            cerrar sesion
          </button>
        </div>
      </header>

      {/* Period selector */}
      <div className="px-4 pt-4 pb-2">
        <PeriodSelector
          preset={period.preset}
          customFrom={period.customFrom}
          customTo={period.customTo}
          onPreset={(p) => {
            period.setPreset(p)
            setFilterLowStock(false)
          }}
          onCustomFrom={period.setCustomFrom}
          onCustomTo={period.setCustomTo}
          lastInventoryAt={data?.last_inventory_at ?? null}
        />
      </div>

      <main className="flex-1 px-4 pb-6 flex flex-col gap-4">
        {/* Loading state */}
        {isLoading && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <SkeletonWidget />
              <SkeletonWidget />
            </div>
            <SkeletonTable />
          </>
        )}

        {/* Empty state */}
        {isEmpty && (
          <EmptyState onPreset={(p) => period.setPreset(p)} />
        )}

        {/* Content */}
        {!isLoading && data && !isEmpty && (
          <>
            {/* Widgets row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <LowStockWidget
                items={data.low_stock}
                onVerTodos={() => setFilterLowStock(true)}
              />
              <OrdersWidget
                completed={data.orders_summary.completed_count}
                photoOnly={data.orders_summary.photo_only_count}
              />
            </div>

            {/* Products table */}
            <ProductTable
              products={data.products}
              onRowClick={(productId) => navigate(`/tablero/producto/${productId}`)}
              filterLowStock={filterLowStock}
            />

            {/* CSV error banner */}
            {csvError && (
              <div role="alert" className="bg-orange-100 border border-orange-300 text-orange-800 text-sm rounded px-4 py-3">
                {csvError}
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-3 mt-2">
              <button
                onClick={() => { void handleDownloadCsv() }}
                disabled={csvLoading}
                className="px-5 py-3 bg-gray-900 text-white text-sm font-semibold rounded min-h-[48px] disabled:opacity-50"
              >
                {csvLoading ? 'descargando...' : 'descargar CSV'}
              </button>
              {filterLowStock && (
                <button
                  onClick={() => setFilterLowStock(false)}
                  className="px-5 py-3 border border-gray-900 text-gray-900 text-sm font-semibold rounded min-h-[48px]"
                >
                  ver todos los productos
                </button>
              )}
            </div>
          </>
        )}
      </main>

      {/* Error banner */}
      {isError && showError && (
        <ErrorBanner
          message="Error al cargar el tablero."
          onDismiss={() => setShowError(false)}
          onRetry={handleRetry}
        />
      )}
    </div>
  )
}
