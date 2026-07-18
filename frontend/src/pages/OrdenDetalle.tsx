/**
 * Detalle de orden de compra (issue #101) — reglas del dueño:
 *  - Orden abierta SIN recepciones: editar cantidad/costo y quitar lineas
 *    (todo append-only con motivo opcional).
 *  - Orden CON recepciones: no se desarma — solo anular con motivo.
 *  - Cerrada/anulada: solo lectura.
 */
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  usePurchaseOrder,
  useAnnulOrder,
  useRemoveOrderLine,
  useEditOrderLine,
} from '../lib/purchaseOrders'
import { useAuthWithGetters } from '../lib/auth'
import { formatRelativeDate } from '../lib/date'
import type { PurchaseOrderDetailItem, PurchaseOrderStatus } from '../lib/types'

const STATUS_LABEL: Record<PurchaseOrderStatus, string> = {
  open: 'ABIERTA',
  partially_received: 'RECIBIDA PARCIAL',
  closed: 'CERRADA',
  annulled: 'ANULADA',
}

function StatusBadge({ status }: { status: PurchaseOrderStatus }) {
  const dark = status === 'open' || status === 'partially_received'
  return (
    <span
      className={[
        'text-[10px] font-bold uppercase px-2 py-1',
        dark ? 'bg-gray-900 text-white' : 'bg-gray-200 text-gray-600',
      ].join(' ')}
    >
      {STATUS_LABEL[status]}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Fila de linea con edicion inline
// ---------------------------------------------------------------------------

function LineRow({
  item,
  editable,
  onEdit,
  onRemove,
  busy,
}: {
  item: PurchaseOrderDetailItem
  editable: boolean
  onEdit: (patch: { expected_qty?: number; unit_cost?: number; reason?: string }) => void
  onRemove: (reason?: string) => void
  busy: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [qty, setQty] = useState(item.expected_qty)
  const [cost, setCost] = useState(item.unit_cost)
  const [reason, setReason] = useState('')
  const [confirmingRemove, setConfirmingRemove] = useState(false)

  function handleSave() {
    const patch: { expected_qty?: number; unit_cost?: number; reason?: string } = {}
    if (qty !== item.expected_qty) patch.expected_qty = parseFloat(qty)
    if (cost !== item.unit_cost) patch.unit_cost = parseFloat(cost)
    if (reason.trim()) patch.reason = reason.trim()
    if (patch.expected_qty === undefined && patch.unit_cost === undefined) {
      setEditing(false)
      return
    }
    onEdit(patch)
    setEditing(false)
    setReason('')
  }

  if (editing) {
    return (
      <div className="bg-white px-4 py-3 flex flex-col gap-2 border-l-4 border-gray-900">
        <p className="text-sm font-semibold text-gray-900">{item.product_name}</p>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1 text-[10px] uppercase text-gray-500">
            cantidad ({item.unit})
            <input
              type="number"
              inputMode="decimal"
              min="0.001"
              step="any"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              className="min-h-[44px] px-2 border border-gray-300 text-sm text-gray-900"
              aria-label={`Cantidad de ${item.product_name}`}
            />
          </label>
          <label className="flex flex-col gap-1 text-[10px] uppercase text-gray-500">
            costo unit.
            <input
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              value={cost}
              onChange={(e) => setCost(e.target.value)}
              className="min-h-[44px] px-2 border border-gray-300 text-sm text-gray-900"
              aria-label={`Costo de ${item.product_name}`}
            />
          </label>
        </div>
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="motivo (opcional)"
          aria-label={`Motivo del cambio de ${item.product_name}`}
          className="min-h-[44px] px-2 border border-gray-300 text-sm"
        />
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={busy}
            className="flex-1 min-h-[44px] bg-gray-900 text-white text-sm font-bold uppercase active:opacity-80"
          >
            guardar cambio
          </button>
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="min-h-[44px] px-4 border border-gray-300 text-sm text-gray-600"
          >
            cancelar
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">{item.product_name}</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {item.expected_qty} {item.unit} × S/. {item.unit_cost} = S/. {item.line_total}
          </p>
          <p className="text-[11px] text-gray-400 mt-0.5">
            recibido {item.received_qty} · pendiente {item.pending_qty}
          </p>
        </div>
        {editable && (
          <div className="flex flex-col gap-1 flex-shrink-0">
            <button
              type="button"
              onClick={() => {
                setQty(item.expected_qty)
                setCost(item.unit_cost)
                setEditing(true)
              }}
              className="min-h-[36px] px-3 text-xs font-semibold text-gray-700 border border-gray-300 active:bg-gray-100"
              aria-label={`Editar ${item.product_name}`}
            >
              editar
            </button>
            {confirmingRemove ? (
              <button
                type="button"
                onClick={() => {
                  onRemove()
                  setConfirmingRemove(false)
                }}
                disabled={busy}
                className="min-h-[36px] px-3 text-xs font-bold text-white bg-red-600 active:opacity-80"
                aria-label={`Confirmar quitar ${item.product_name}`}
              >
                confirmar
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmingRemove(true)}
                className="min-h-[36px] px-3 text-xs font-semibold text-red-600 border border-red-300 active:bg-red-50"
                aria-label={`Quitar ${item.product_name}`}
              >
                quitar
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pagina
// ---------------------------------------------------------------------------

export function OrdenDetalle() {
  const navigate = useNavigate()
  const { id } = useParams<{ id: string }>()
  const { userId } = useAuthWithGetters()

  const { data: order, isLoading, isError } = usePurchaseOrder(id ?? '', userId)
  const annulMutation = useAnnulOrder(id ?? '')
  const removeMutation = useRemoveOrderLine(id ?? '')
  const editMutation = useEditOrderLine(id ?? '')

  const [annulling, setAnnulling] = useState(false)
  const [annulReason, setAnnulReason] = useState('')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const busy =
    annulMutation.isPending || removeMutation.isPending || editMutation.isPending

  // Reglas del dueño: editable solo abierta y sin partidas recibidas
  const editable =
    !!order && order.derived_status === 'open' && order.partida_count === 0
  const annullable =
    !!order &&
    (order.derived_status === 'open' || order.derived_status === 'partially_received')

  function onError() {
    setErrorMsg('No se pudo guardar. Toca de nuevo para reintentar.')
    setTimeout(() => setErrorMsg(null), 5000)
  }

  async function handleAnnul() {
    if (!annulReason.trim()) return
    annulMutation.mutate(
      { reason: annulReason.trim() },
      {
        onSuccess: () => navigate('/ordenes'),
        onError,
      },
    )
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate('/ordenes')}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver a ordenes"
        >
          &lt;
        </button>
        <h1 className="text-lg font-bold uppercase tracking-wide truncate">
          {order ? order.supplier_name : 'cargando...'}
        </h1>
      </header>

      <main className="flex-1 overflow-y-auto pb-32">
        {isLoading && <p className="px-4 py-6 text-sm text-gray-500">cargando...</p>}
        {isError && (
          <p className="px-4 py-6 text-sm text-red-600">Error al cargar la orden.</p>
        )}

        {order && (
          <>
            <div className="px-4 py-4 flex items-center justify-between">
              <div>
                <p className="text-xs text-gray-500">
                  {formatRelativeDate(order.created_at)} · {order.created_by_name}
                </p>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  {order.partida_count}{' '}
                  {order.partida_count === 1 ? 'partida recibida' : 'partidas recibidas'}
                </p>
              </div>
              <StatusBadge status={order.derived_status} />
            </div>

            {!editable && order.derived_status === 'open' && order.partida_count > 0 && (
              <p className="mx-4 mb-2 px-3 py-2 bg-gray-100 text-[11px] text-gray-600">
                Esta orden ya tiene recepciones: las lineas no se editan. Si hubo un
                error grande, anulala con motivo.
              </p>
            )}

            <div className="flex flex-col gap-px bg-gray-300">
              {order.items.map((item) => (
                <LineRow
                  key={item.id}
                  item={item}
                  editable={editable}
                  busy={busy}
                  onEdit={(patch) =>
                    editMutation.mutate({ itemId: item.id, ...patch }, { onError })
                  }
                  onRemove={(reason) =>
                    removeMutation.mutate({ itemId: item.id, reason }, { onError })
                  }
                />
              ))}
            </div>

            <div className="px-4 py-4 space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Total pedido</span>
                <span className="font-bold text-gray-900">S/. {order.total_ordered}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Recibido</span>
                <span className="text-gray-900">S/. {order.total_received}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Pendiente</span>
                <span className="text-gray-900">S/. {order.pending_amount}</span>
              </div>
            </div>

            {annullable && (
              <div className="px-4 py-2">
                {annulling ? (
                  <div className="flex flex-col gap-2 border-2 border-red-300 p-3 bg-white">
                    <p className="text-sm font-semibold text-gray-900">
                      Anular orden — el motivo es obligatorio
                    </p>
                    <textarea
                      value={annulReason}
                      onChange={(e) => setAnnulReason(e.target.value)}
                      placeholder="ej: el proveedor cancelo la entrega"
                      aria-label="Motivo de anulacion"
                      className="min-h-[64px] px-2 py-1 border border-gray-300 text-sm"
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={handleAnnul}
                        disabled={!annulReason.trim() || busy}
                        className={[
                          'flex-1 min-h-[44px] text-sm font-bold uppercase',
                          annulReason.trim() && !busy
                            ? 'bg-red-600 text-white active:opacity-80'
                            : 'bg-gray-200 text-gray-400',
                        ].join(' ')}
                      >
                        anular orden
                      </button>
                      <button
                        type="button"
                        onClick={() => setAnnulling(false)}
                        className="min-h-[44px] px-4 border border-gray-300 text-sm text-gray-600"
                      >
                        cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setAnnulling(true)}
                    className="w-full min-h-[48px] border border-red-300 text-red-600 text-sm font-semibold active:bg-red-50"
                  >
                    anular orden
                  </button>
                )}
              </div>
            )}
          </>
        )}
      </main>

      {errorMsg && (
        <div
          role="alert"
          aria-live="assertive"
          className="fixed top-4 left-4 right-4 z-50 bg-red-600 text-white px-4 py-3 text-sm font-medium"
        >
          {errorMsg}
        </div>
      )}
    </div>
  )
}
