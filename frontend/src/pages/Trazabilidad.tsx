import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useDashboardSummary, useTraceability, downloadCsv } from '../lib/dashboard'
import { usePeriod } from '../lib/usePeriod'
import { PeriodSelector } from '../components/PeriodSelector'
import { ErrorBanner } from '../components/ErrorBanner'
import { formatRelativeDate } from '../lib/date'
import type { TraceabilityEvent } from '../lib/types'

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function SkeletonRow() {
  return (
    <div
      role="status"
      aria-label="Cargando evento"
      className="border-b border-gray-100 py-3 px-4 animate-pulse"
    >
      <div className="flex gap-4">
        <div className="h-3 bg-gray-200 rounded w-24" />
        <div className="h-3 bg-gray-200 rounded w-16" />
        <div className="h-3 bg-gray-100 rounded w-12" />
        <div className="h-3 bg-gray-100 rounded flex-1" />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Event type badge
// ---------------------------------------------------------------------------

const TYPE_STYLES: Record<string, string> = {
  ENTREGA: 'bg-blue-100 text-blue-800',
  PEDIDO: 'bg-purple-100 text-purple-800',
  INVENTARIO: 'bg-green-100 text-green-800',
}

function TypeBadge({ type }: { type: string }) {
  const style = TYPE_STYLES[type] ?? 'bg-gray-100 text-gray-700'
  return (
    <span className={`inline-block text-xs font-bold px-2 py-0.5 rounded uppercase ${style}`}>
      {type}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Events table
// ---------------------------------------------------------------------------

interface EventsTableProps {
  events: TraceabilityEvent[]
}

function buildNote(event: TraceabilityEvent): string {
  // Render corrections as pairs:
  // If corrected_by_note is set, the event was corrected → show that label.
  // If corrects_id is set (and no corrected_by_note), it is a correction → show note.
  if (event.corrected_by_note) return event.corrected_by_note
  if (event.note) return event.note
  return ''
}

function EventsTable({ events }: EventsTableProps) {
  // Backend returns ASC; display newest first
  const sorted = [...events].reverse()

  if (sorted.length === 0) {
    return (
      <p className="text-gray-400 text-sm py-6 text-center">
        Sin eventos en este periodo.
      </p>
    )
  }

  return (
    <>
      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-3 py-2 font-semibold text-gray-600 uppercase text-xs">
                Fecha
              </th>
              <th className="text-left px-3 py-2 font-semibold text-gray-600 uppercase text-xs">
                Tipo
              </th>
              <th className="text-right px-3 py-2 font-semibold text-gray-600 uppercase text-xs">
                Cantidad
              </th>
              <th className="text-left px-3 py-2 font-semibold text-gray-600 uppercase text-xs">
                Operario
              </th>
              <th className="text-left px-3 py-2 font-semibold text-gray-600 uppercase text-xs">
                Nota
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((event) => {
              const note = buildNote(event)
              const isCorrected = !!event.corrected_by_note
              return (
                <tr
                  key={event.id}
                  className={[
                    'border-b border-gray-100',
                    isCorrected ? 'opacity-50' : '',
                  ].join(' ')}
                >
                  <td className="px-3 py-3 text-gray-600 whitespace-nowrap">
                    {formatRelativeDate(event.date)}
                  </td>
                  <td className="px-3 py-3">
                    <TypeBadge type={event.type} />
                  </td>
                  <td className="px-3 py-3 text-right text-gray-700">
                    {event.qty} {event.unit}
                  </td>
                  <td className="px-3 py-3 text-gray-700">{event.operator}</td>
                  <td className="px-3 py-3 text-gray-500 text-xs">{note}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile list */}
      <div className="md:hidden flex flex-col gap-2">
        {sorted.map((event) => {
          const note = buildNote(event)
          const isCorrected = !!event.corrected_by_note
          return (
            <div
              key={event.id}
              className={[
                'bg-white border border-gray-200 rounded-lg p-3',
                isCorrected ? 'opacity-50' : '',
              ].join(' ')}
            >
              <div className="flex items-center gap-2 mb-1">
                <TypeBadge type={event.type} />
                <span className="text-xs text-gray-500">{formatRelativeDate(event.date)}</span>
              </div>
              <div className="text-sm text-gray-700 flex flex-wrap gap-x-4">
                <span>
                  <strong>
                    {event.qty} {event.unit}
                  </strong>
                </span>
                <span>{event.operator}</span>
              </div>
              {note && <p className="text-xs text-gray-400 mt-1">{note}</p>}
            </div>
          )
        })}
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Trazabilidad() {
  const { productId } = useParams<{ productId: string }>()
  const navigate = useNavigate()

  const period = usePeriod('7d')
  const safeProductId = productId ?? ''

  // We need the summary to get product metadata (name, stock_now, consumption)
  const {
    data: summaryData,
    isLoading: summaryLoading,
  } = useDashboardSummary(period.from, period.to)

  const {
    data: events,
    isLoading: eventsLoading,
    isError,
    refetch,
  } = useTraceability(safeProductId, period.from, period.to)

  const [showError, setShowError] = useState(true)
  const [csvLoading, setCsvLoading] = useState(false)

  const isLoading = summaryLoading || eventsLoading

  // Find product metadata from summary
  const productMeta = summaryData?.products.find((p) => p.product_id === safeProductId)
  const productName = productMeta?.name ?? safeProductId.toUpperCase()
  const stockNow = productMeta?.stock_now
  const stockUnit = productMeta?.unit ?? ''
  const consumption = productMeta?.consumption
  const consumptionAvailable = productMeta?.consumption_available ?? false

  function handleRetry() {
    setShowError(true)
    void refetch()
  }

  async function handleDownloadCsv() {
    setCsvLoading(true)
    try {
      await downloadCsv(period.from, period.to, 'all')
    } catch {
      // best-effort
    } finally {
      setCsvLoading(false)
    }
  }

  // Error state: product not found in summary (404 equivalent on the client)
  const productNotFound = !summaryLoading && summaryData && !productMeta

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate('/tablero')}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver al tablero"
        >
          &lt;
        </button>
        <h1 className="text-lg font-bold tracking-wide uppercase">
          Trazabilidad — {productName}
        </h1>
      </header>

      {/* Period selector */}
      <div className="px-4 pt-4 pb-2">
        <PeriodSelector
          preset={period.preset}
          customFrom={period.customFrom}
          customTo={period.customTo}
          onPreset={period.setPreset}
          onCustomFrom={period.setCustomFrom}
          onCustomTo={period.setCustomTo}
          lastInventoryAt={summaryData?.last_inventory_at ?? null}
        />
      </div>

      <main className="flex-1 px-4 pb-6 flex flex-col gap-4">
        {/* Product not found */}
        {productNotFound && (
          <div
            role="alert"
            className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm"
          >
            Producto no encontrado en el periodo seleccionado.
          </div>
        )}

        {/* Metrics */}
        {!productNotFound && (
          <div className="flex flex-wrap gap-4">
            {isLoading ? (
              <>
                <div className="h-5 bg-gray-200 rounded w-32 animate-pulse" />
                <div className="h-5 bg-gray-200 rounded w-40 animate-pulse" />
              </>
            ) : (
              <>
                {stockNow !== undefined && (
                  <p className="text-base text-gray-700">
                    Stock ahora:{' '}
                    <strong>
                      {stockNow} {stockUnit}
                    </strong>
                  </p>
                )}
                <p className="text-base text-gray-700">
                  Consumo del periodo:{' '}
                  {consumptionAvailable ? (
                    <strong>
                      {consumption} {stockUnit}
                    </strong>
                  ) : (
                    <span className="text-gray-400">sin dato de inicio</span>
                  )}
                </p>
              </>
            )}
          </div>
        )}

        {/* Events */}
        <section aria-label="Eventos del producto">
          <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-2">
            Eventos
          </h2>

          {isLoading ? (
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
            </div>
          ) : (
            !productNotFound && events && (
              <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <EventsTable events={events} />
              </div>
            )
          )}
        </section>

        {/* Actions */}
        <div className="flex gap-3 mt-2">
          <button
            onClick={() => { void handleDownloadCsv() }}
            disabled={csvLoading}
            className="px-5 py-3 bg-gray-900 text-white text-sm font-semibold rounded min-h-[48px] disabled:opacity-50"
          >
            {csvLoading ? 'descargando...' : 'descargar CSV'}
          </button>
        </div>
      </main>

      {/* Error banner */}
      {isError && showError && (
        <ErrorBanner
          message="Error al cargar la trazabilidad."
          onDismiss={() => setShowError(false)}
          onRetry={handleRetry}
        />
      )}
    </div>
  )
}
