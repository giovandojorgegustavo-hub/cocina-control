import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { usePurchaseOrders } from '../lib/purchaseOrders'
import { useAuthWithGetters } from '../lib/auth'
import { formatRelativeDate } from '../lib/date'
import { formatSoles } from '../lib/currency'
import { ErrorBanner } from '../components/ErrorBanner'
import type { PurchaseOrderListItem, PurchaseOrderStatus } from '../lib/types'

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

type TabKey = 'open' | 'partially_received' | 'closed' | 'annulled' | 'all'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'open', label: 'Abiertas' },
  { key: 'partially_received', label: 'Recibida parcial' },
  { key: 'closed', label: 'Cerradas' },
  { key: 'annulled', label: 'Anuladas' },
  { key: 'all', label: 'Todas' },
]

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: PurchaseOrderStatus }) {
  switch (status) {
    case 'open':
      return (
        <span className="inline-block bg-gray-900 text-white text-xs font-bold uppercase tracking-wider px-2 py-1">
          ABIERTA
        </span>
      )
    case 'partially_received':
      return (
        <span className="inline-block bg-yellow-400 text-yellow-900 text-xs font-bold uppercase tracking-wider px-2 py-1">
          RECIBIDA PARCIAL
        </span>
      )
    case 'closed':
      return (
        <span className="inline-block bg-gray-300 text-gray-600 text-xs font-medium px-2 py-1">
          CERRADA ✓
        </span>
      )
    case 'annulled':
      return (
        <span className="inline-block bg-gray-200 text-gray-500 text-xs font-medium px-2 py-1">
          ANULADA
        </span>
      )
  }
}

// ---------------------------------------------------------------------------
// Skeleton row
// ---------------------------------------------------------------------------

function SkeletonRow() {
  return (
    <div
      role="status"
      aria-label="Cargando orden"
      className="bg-white border border-gray-200 px-4 py-4 animate-pulse"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="h-4 bg-gray-200 rounded w-40" />
        <div className="h-5 bg-gray-200 rounded w-28" />
      </div>
      <div className="h-3 bg-gray-100 rounded w-56" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Order row — not tappable (orden-03 detail is out of scope for v0.3)
// ---------------------------------------------------------------------------

interface OrderCardProps {
  order: PurchaseOrderListItem
}

function OrderCard({ order }: OrderCardProps) {
  const isMuted = order.derived_status === 'closed' || order.derived_status === 'annulled'
  const isYellow = order.derived_status === 'partially_received'

  function renderSummary() {
    switch (order.derived_status) {
      case 'open':
        return (
          <span className="text-sm text-gray-600">
            {order.item_count} {order.item_count === 1 ? 'producto' : 'productos'} ·{' '}
            {formatSoles(order.total_ordered)}
          </span>
        )
      case 'partially_received':
        return (
          <span className="text-sm text-yellow-800">
            {order.pending_summary ?? ''} · pendiente {formatSoles(order.pending_amount)}
          </span>
        )
      case 'closed':
        return (
          <span className="text-sm text-gray-400">
            total recibido {formatSoles(order.total_received)}
          </span>
        )
      case 'annulled':
        return (
          <span className="text-sm text-gray-400">
            anulada · {order.item_count} {order.item_count === 1 ? 'partida conservada' : 'partidas conservadas'}
          </span>
        )
    }
  }

  return (
    <div
      className={[
        'px-4 py-4 min-h-[72px] flex flex-col gap-1',
        isMuted ? 'bg-gray-100 border border-gray-200' : '',
        isYellow ? 'bg-yellow-50 border border-yellow-200' : '',
        !isMuted && !isYellow ? 'bg-white border border-gray-200' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className={[
            'text-base font-bold uppercase tracking-wide',
            isMuted ? 'text-gray-400' : 'text-gray-900',
          ].join(' ')}
        >
          {order.supplier_name}
        </span>
        <div className="flex items-center gap-2 flex-shrink-0">
          <StatusBadge status={order.derived_status} />
          <span className="text-xs text-gray-400">{formatRelativeDate(order.created_at)}</span>
        </div>
      </div>
      {renderSummary()}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function OrdenesLista() {
  const navigate = useNavigate()
  const { userId, role } = useAuthWithGetters()
  const backTo = role === 'owner' ? '/tablero' : '/'
  const [activeTab, setActiveTab] = useState<TabKey>('open')
  const [showError, setShowError] = useState(true)

  const statusFilter = activeTab === 'all' ? undefined : (activeTab as PurchaseOrderStatus)
  const { data, isLoading, isError, refetch } = usePurchaseOrders(
    activeTab === 'all' ? 'all' : statusFilter,
    userId,
  )

  const orders = data ?? []
  const hasData = orders.length > 0

  function handleRetry() {
    setShowError(true)
    void refetch()
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(backTo)}
            className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
            aria-label="Volver"
          >
            &lt;
          </button>
          <h1 className="text-lg font-bold tracking-wide uppercase">ORDENES DE COMPRA</h1>
        </div>
        <Link
          to="/ordenes/nueva"
          className="min-h-[48px] px-4 flex items-center justify-center bg-white text-gray-900 text-sm font-bold uppercase tracking-wide active:opacity-70"
        >
          + nueva
        </Link>
      </header>

      {/* Tabs */}
      <div className="flex overflow-x-auto bg-white border-b border-gray-200 flex-shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => {
              setActiveTab(tab.key)
              setShowError(true)
            }}
            className={[
              'flex-shrink-0 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
              activeTab === tab.key
                ? 'border-gray-900 text-gray-900'
                : 'border-transparent text-gray-500 active:text-gray-700',
            ].join(' ')}
            aria-pressed={activeTab === tab.key}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <main className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="flex flex-col gap-px bg-gray-300">
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </div>
        )}

        {!isLoading && !isError && !hasData && (
          <div className="flex flex-col items-center justify-center h-full px-8 text-center">
            <p className="text-gray-700 text-lg font-medium">
              No hay ordenes de compra todavia.
            </p>
            <p className="text-gray-500 text-sm mt-2">
              Crea la primera desde &ldquo;+ nueva&rdquo;.
            </p>
          </div>
        )}

        {!isLoading && hasData && (
          <div className="flex flex-col gap-px bg-gray-300">
            {orders.map((order) => (
              <OrderCard key={order.id} order={order} />
            ))}
          </div>
        )}
      </main>

      {isError && showError && (
        <ErrorBanner
          message="Error al cargar las ordenes."
          onDismiss={() => setShowError(false)}
          onRetry={handleRetry}
        />
      )}
    </div>
  )
}
