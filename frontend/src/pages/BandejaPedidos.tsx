/**
 * Pantalla 3 — Bandeja de pedidos
 *
 * Muestra pending primero (más nuevos arriba), luego completed.
 * Cada fila tiene miniatura de la foto, hora relativa, badge de estado
 * y botón "completar" en los pendientes.
 *
 * Las fotos del servidor requieren auth — se sirven via AuthImg.
 * Los pedidos en cola local (aún no subidos) muestran la miniatura
 * desde la Blob local en IndexedDB.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOrders } from '../lib/orders'
import { getAllQueueEntries } from '../lib/photoQueue'
import { useAuthWithGetters } from '../lib/auth'
import { formatRelativeDate } from '../lib/date'
import { AuthImg } from '../components/AuthImg'
import { ErrorBanner } from '../components/ErrorBanner'
import type { DeliveryOrderListItem, PhotoQueueEntry } from '../lib/types'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------

function OrderBadge({ status }: { status: 'pending' | 'completed' }) {
  if (status === 'pending') {
    return (
      <span className="inline-block border-2 border-yellow-500 text-yellow-700 bg-yellow-50 text-xs font-bold uppercase tracking-wider px-2 py-1">
        PENDIENTE
      </span>
    )
  }
  return (
    <span className="inline-block bg-gray-200 text-gray-500 text-xs font-medium px-2 py-1">
      TERMINADO ✓
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
      aria-label="Cargando pedido"
      className="bg-white border border-gray-200 px-4 py-4 animate-pulse flex gap-3 items-center"
    >
      <div className="w-14 h-14 bg-gray-200 rounded flex-shrink-0" />
      <div className="flex-1">
        <div className="h-4 bg-gray-200 rounded w-32 mb-2" />
        <div className="h-3 bg-gray-100 rounded w-24" />
      </div>
      <div className="h-6 bg-gray-200 rounded w-24" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Server order row
// ---------------------------------------------------------------------------

interface OrderRowProps {
  order: DeliveryOrderListItem
  onComplete: (id: string) => void
}

function OrderRow({ order, onComplete }: OrderRowProps) {
  const isPending = order.status === 'pending'
  const photoSrc = `${BASE_URL}/api/v1/delivery-orders/${order.id}/photo`

  return (
    <div
      className={[
        'bg-white border border-gray-200 px-4 py-4 flex gap-3 items-center',
        isPending ? 'border-l-4 border-l-yellow-500' : '',
      ].join(' ')}
    >
      {/* Photo thumbnail */}
      <div className="w-14 h-14 flex-shrink-0 overflow-hidden bg-gray-100">
        <AuthImg
          src={photoSrc}
          alt={`Foto del pedido de las ${formatRelativeDate(order.photo_at)}`}
          className="w-full h-full object-cover"
          data-testid="order-photo"
        />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-900">
          {formatRelativeDate(order.photo_at)}
        </p>
        <p className="text-xs text-gray-500 mt-0.5">
          {order.status === 'completed' ? 'completado' : 'sin detalle todavia'}
        </p>
      </div>

      {/* Badge + action */}
      <div className="flex flex-col items-end gap-2 flex-shrink-0">
        <OrderBadge status={order.status} />
        {isPending && (
          <button
            onClick={() => onComplete(order.id)}
            className="bg-gray-900 text-white text-xs font-bold uppercase tracking-wider px-3 py-2 min-h-[40px] active:opacity-70"
            aria-label={`Completar pedido de las ${formatRelativeDate(order.photo_at)}`}
          >
            completar
          </button>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Local queued order row (photo not yet uploaded)
// ---------------------------------------------------------------------------

interface LocalOrderRowProps {
  entry: PhotoQueueEntry
  localBlobUrl: string
}

function LocalOrderRow({ entry, localBlobUrl }: LocalOrderRowProps) {
  return (
    <div className="bg-white border border-gray-200 border-l-4 border-l-yellow-300 px-4 py-4 flex gap-3 items-center opacity-80">
      <div className="w-14 h-14 flex-shrink-0 overflow-hidden bg-gray-100">
        <img
          src={localBlobUrl}
          alt="Foto del pedido en cola"
          className="w-full h-full object-cover"
        />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-900">
          {formatRelativeDate(entry.timestamp)}
        </p>
        <p className="text-xs text-gray-400 mt-0.5">subiendo...</p>
      </div>
      <div className="flex-shrink-0">
        <span className="inline-block border-2 border-yellow-300 text-yellow-600 bg-yellow-50 text-xs font-bold uppercase tracking-wider px-2 py-1">
          PENDIENTE
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sort helper
// ---------------------------------------------------------------------------

function sortOrders(orders: DeliveryOrderListItem[]): DeliveryOrderListItem[] {
  return [...orders].sort((a, b) => {
    // pending before completed
    if (a.status !== b.status) {
      return a.status === 'pending' ? -1 : 1
    }
    // Within group: newest first
    return new Date(b.photo_at).getTime() - new Date(a.photo_at).getTime()
  })
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function BandejaPedidos() {
  const navigate = useNavigate()
  const { userId } = useAuthWithGetters()
  const { data, isLoading, isError, refetch } = useOrders(userId)
  const [showError, setShowError] = useState(true)

  // Local queue entries (not yet on the server)
  const [localEntries, setLocalEntries] = useState<PhotoQueueEntry[]>([])
  const [localBlobUrls, setLocalBlobUrls] = useState<Map<string, string>>(new Map())

  useEffect(() => {
    let alive = true
    async function loadLocal() {
      const all = await getAllQueueEntries()
      // Only show entries that haven't been confirmed by server yet
      const pending = all.filter(
        (e) => e.status !== 'done' && e.serverId === undefined,
      )
      if (!alive) return
      setLocalEntries(pending)

      // Create blob URLs for rendering
      const urls = new Map<string, string>()
      for (const entry of pending) {
        if (entry.blob) {
          urls.set(entry.localId, URL.createObjectURL(entry.blob))
        }
      }
      setLocalBlobUrls(urls)
    }
    void loadLocal()

    return () => {
      alive = false
      // Revoke blob URLs on unmount
      setLocalBlobUrls((prev) => {
        prev.forEach((url) => URL.revokeObjectURL(url))
        return new Map()
      })
    }
  }, [])

  const sorted = data ? sortOrders(data) : []
  const hasData = sorted.length > 0 || localEntries.length > 0

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
        <h1 className="text-lg font-bold tracking-wide uppercase">PEDIDOS — bandeja</h1>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-y-auto">
        {isLoading && !hasData && (
          <div className="flex flex-col gap-px bg-gray-300">
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </div>
        )}

        {!isLoading && !isError && !hasData && (
          <div className="flex flex-col items-center justify-center h-full px-8 text-center">
            <p className="text-gray-700 text-lg font-medium">
              Todavia no hay pedidos hoy.
            </p>
            <p className="text-gray-500 text-sm mt-2">
              Saca la primera foto al empacar.
            </p>
          </div>
        )}

        {hasData && (
          <div className="flex flex-col gap-px bg-gray-300">
            {/* Local queued entries appear first (they are always pending) */}
            {localEntries.map((entry) => {
              const blobUrl = localBlobUrls.get(entry.localId)
              if (!blobUrl) return null
              return (
                <LocalOrderRow
                  key={entry.localId}
                  entry={entry}
                  localBlobUrl={blobUrl}
                />
              )
            })}
            {/* Server orders */}
            {sorted.map((order) => (
              <OrderRow
                key={order.id}
                order={order}
                onComplete={(id) => navigate(`/pedidos/${id}/completar`)}
              />
            ))}
          </div>
        )}
      </main>

      {isError && showError && (
        <ErrorBanner
          message="Error al cargar pedidos."
          onDismiss={() => setShowError(false)}
          onRetry={handleRetry}
        />
      )}
    </div>
  )
}
