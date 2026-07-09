import { useNavigate } from 'react-router-dom'
import { useDeliveries } from '../lib/deliveries'
import { useAuthWithGetters } from '../lib/auth'
import { formatRelativeDate } from '../lib/date'
import type { DeliveryListItem, DeliveryStatus } from '../lib/types'
import { ErrorBanner } from '../components/ErrorBanner'
import { useState } from 'react'

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

// The wireframe treats `en_verificacion` as unread in the bandeja: an
// abandoned verification still appears as pending. The detail page (Frontend #4)
// reads the real status and knows how to resume where the operator left off.
interface BadgeProps {
  status: DeliveryStatus
}

function StatusBadge({ status }: BadgeProps) {
  if (status === 'no_leida' || status === 'en_verificacion') {
    return (
      <span className="inline-block bg-gray-900 text-white text-xs font-bold uppercase tracking-wider px-2 py-1">
        NO LEIDO
      </span>
    )
  }
  // validada
  return (
    <span className="inline-block bg-gray-200 text-gray-500 text-xs font-medium px-2 py-1">
      validado ✓
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
      aria-label="Cargando entrega"
      className="bg-white border border-gray-200 px-4 py-4 animate-pulse"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="h-4 bg-gray-200 rounded w-40" />
        <div className="h-5 bg-gray-200 rounded w-20" />
      </div>
      <div className="h-3 bg-gray-100 rounded w-32" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Delivery row
// ---------------------------------------------------------------------------

interface DeliveryRowProps {
  delivery: DeliveryListItem
  onTap: (id: string) => void
}

function DeliveryRow({ delivery, onTap }: DeliveryRowProps) {
  // The wireframe treats `en_verificacion` as unread in the bandeja: same
  // visual group and same left-border style as no_leida.
  const isPending = delivery.status === 'no_leida' || delivery.status === 'en_verificacion'
  const isValidated = delivery.status === 'validada'

  return (
    <button
      onClick={() => onTap(delivery.id)}
      className={[
        'w-full text-left px-4 py-4',
        'min-h-[72px]',
        'flex flex-col gap-1',
        'active:opacity-70',
        // Pending (no_leida + en_verificacion): white bg, strong left border
        isPending ? 'bg-white border-l-4 border-l-gray-900 border-y border-r border-gray-200' : '',
        // Validated: muted gray bg
        isValidated ? 'bg-gray-100 border border-gray-200' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      aria-label={`Entrega de ${delivery.supplier_name}, estado: ${delivery.status}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className={[
            'text-base font-bold uppercase tracking-wide',
            isValidated ? 'text-gray-400' : 'text-gray-900',
          ].join(' ')}
        >
          {delivery.supplier_name}
        </span>
        <StatusBadge status={delivery.status} />
      </div>
      <span className={['text-sm', isValidated ? 'text-gray-400' : 'text-gray-600'].join(' ')}>
        {formatRelativeDate(delivery.created_at)} &middot;{' '}
        {delivery.item_count === 1 ? '1 producto' : `${delivery.item_count} productos`}
      </span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Sort helper: pending deliveries first (no_leida and en_verificacion share
// group 0 — the wireframe treats an abandoned verification as still pending),
// then validada. Within each group: newest first.
// ---------------------------------------------------------------------------

// The wireframe treats `en_verificacion` as no_leida in the bandeja: a
// verification abandoned mid-way still appears as pending to the operator.
const STATUS_ORDER: Record<DeliveryStatus, number> = {
  no_leida: 0,
  en_verificacion: 0, // same group as no_leida
  validada: 1,
}

function sortDeliveries(deliveries: DeliveryListItem[]): DeliveryListItem[] {
  return [...deliveries].sort((a, b) => {
    const statusDiff = STATUS_ORDER[a.status] - STATUS_ORDER[b.status]
    if (statusDiff !== 0) return statusDiff
    // Within same status: newest first
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Bandeja() {
  const navigate = useNavigate()
  const { userId } = useAuthWithGetters()
  const { data, isLoading, isError, refetch } = useDeliveries(userId)
  const [showError, setShowError] = useState(true)

  const sorted = data ? sortDeliveries(data) : []
  const hasData = sorted.length > 0

  // Reset banner visibility on each new error so the toast re-appears after
  // a dismiss if a subsequent refetch also fails.
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
        <h1 className="text-lg font-bold tracking-wide uppercase">ENTRADA — entregas</h1>
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

        {/* Empty state: only when there's no data AND no error AND not loading */}
        {!isLoading && !isError && !hasData && (
          <div className="flex flex-col items-center justify-center h-full px-8 text-center">
            <p className="text-gray-700 text-lg font-medium">No hay entregas anunciadas.</p>
            <p className="text-gray-500 text-sm mt-2">
              Cuando el dueño cargue una, aparece acá.
            </p>
          </div>
        )}

        {/*
          Show the list whenever there is cached data, regardless of error state.
          An operator on an intermittent connection keeps seeing the last known
          bandeja while the app retries in the background.
        */}
        {!isLoading && hasData && (
          <div className="flex flex-col gap-px bg-gray-300">
            {sorted.map((delivery) => (
              <DeliveryRow
                key={delivery.id}
                delivery={delivery}
                onTap={(id) => navigate(`/entradas/${id}`)}
              />
            ))}
          </div>
        )}
      </main>

      {/* Error banner — overlays at the bottom without hiding the list */}
      {isError && showError && (
        <ErrorBanner
          message="Error al cargar."
          onDismiss={() => setShowError(false)}
          onRetry={handleRetry}
        />
      )}
    </div>
  )
}
