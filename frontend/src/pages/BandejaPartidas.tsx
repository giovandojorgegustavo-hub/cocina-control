import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePendingPurchaseOrders } from '../lib/purchaseOrders'
import { useAuthWithGetters } from '../lib/auth'
import { formatRelativeDate } from '../lib/date'
import { ErrorBanner } from '../components/ErrorBanner'
import type { PurchaseOrderPendingItem } from '../lib/types'

// ---------------------------------------------------------------------------
// Status badge — only open and partially_received appear in this bandeja
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: 'open' | 'partially_received' }) {
  if (status === 'open') {
    return (
      <span className="inline-block bg-gray-900 text-white text-xs font-bold uppercase tracking-wider px-2 py-1">
        ABIERTA
      </span>
    )
  }
  return (
    <span className="inline-block bg-yellow-400 text-yellow-900 text-xs font-bold uppercase tracking-wider px-2 py-1">
      RECIBIDA PARCIAL
    </span>
  )
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
        <div className="h-5 bg-gray-200 rounded w-24" />
      </div>
      <div className="h-3 bg-gray-100 rounded w-48" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Order row
// ---------------------------------------------------------------------------

interface OrderRowProps {
  order: PurchaseOrderPendingItem
  onTap: (id: string) => void
}

function OrderRow({ order, onTap }: OrderRowProps) {
  return (
    <button
      onClick={() => onTap(order.id)}
      className={[
        'w-full text-left px-4 py-4',
        'min-h-[72px]',
        'flex flex-col gap-1',
        'active:opacity-70',
        order.derived_status === 'open'
          ? 'bg-white border-l-4 border-l-gray-900 border-y border-r border-gray-200'
          : 'bg-yellow-50 border-l-4 border-l-yellow-400 border-y border-r border-yellow-200',
      ].join(' ')}
      aria-label={`Orden de ${order.supplier_name}, estado: ${order.derived_status}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-base font-bold uppercase tracking-wide text-gray-900">
          {order.supplier_name}
        </span>
        <StatusBadge status={order.derived_status} />
      </div>
      <span className="text-sm text-gray-600">
        {formatRelativeDate(order.created_at)} &middot; {order.pending_items_summary}
      </span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function BandejaPartidas() {
  const navigate = useNavigate()
  const { userId } = useAuthWithGetters()
  const { data, isLoading, isError, refetch } = usePendingPurchaseOrders(userId)
  const [showError, setShowError] = useState(true)

  const orders = data ?? []
  const hasData = orders.length > 0

  function handleRetry() {
    setShowError(true)
    void refetch()
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate('/')}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver al home"
        >
          &lt;
        </button>
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-400">ENTRADA</p>
          <h1 className="text-base font-bold uppercase tracking-wide">bandeja de ordenes</h1>
        </div>
      </header>

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
              No hay ordenes con entregas pendientes.
            </p>
            <p className="text-gray-500 text-sm mt-2">
              Cuando el dueno cargue una, aparece aca.
            </p>
          </div>
        )}

        {!isLoading && hasData && (
          <div className="flex flex-col gap-px bg-gray-300">
            {orders.map((order) => (
              <OrderRow
                key={order.id}
                order={order}
                onTap={(id) => navigate(`/entradas/${id}`)}
              />
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
