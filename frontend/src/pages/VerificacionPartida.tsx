import { useEffect, useReducer, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { usePartidaDraft, useValidatePartida } from '../lib/purchaseOrders'
import { useAuthWithGetters } from '../lib/auth'
import type { PartidaDraftItem } from '../lib/types'

// ---------------------------------------------------------------------------
// Local item state — optimistic confirmation, no server round-trips per item
// ---------------------------------------------------------------------------

interface LocalItem extends PartidaDraftItem {
  confirmedLocally: boolean
  confirmedQty: number | null
}

type ItemMap = Record<string, LocalItem>

type Action =
  | { type: 'INIT'; items: PartidaDraftItem[] }
  | { type: 'CONFIRM'; itemId: string; qty: number }
  | { type: 'EDIT'; itemId: string; qty: number }

function itemsReducer(state: ItemMap, action: Action): ItemMap {
  switch (action.type) {
    case 'INIT': {
      const next: ItemMap = {}
      for (const item of action.items) {
        const prev = state[item.purchase_order_item_id]
        // Preserve local state on refetch
        if (prev?.confirmedLocally) {
          next[item.purchase_order_item_id] = { ...prev, ...item, confirmedLocally: prev.confirmedLocally, confirmedQty: prev.confirmedQty }
        } else {
          next[item.purchase_order_item_id] = {
            ...item,
            confirmedLocally: false,
            confirmedQty: null,
          }
        }
      }
      return next
    }
    case 'CONFIRM': {
      const prev = state[action.itemId]
      if (!prev) return state
      return {
        ...state,
        [action.itemId]: {
          ...prev,
          confirmedLocally: true,
          confirmedQty: action.qty,
        },
      }
    }
    case 'EDIT': {
      const prev = state[action.itemId]
      if (!prev) return state
      return {
        ...state,
        [action.itemId]: {
          ...prev,
          confirmedLocally: true,
          confirmedQty: action.qty,
        },
      }
    }
    default:
      return state
  }
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

interface ToastState {
  visible: boolean
  message: string
}

// ---------------------------------------------------------------------------
// Skeleton row
// ---------------------------------------------------------------------------

function SkeletonItemRow() {
  return (
    <div
      role="status"
      aria-label="Cargando producto"
      className="bg-white border-b border-gray-200 px-4 py-4 animate-pulse flex items-center gap-3"
    >
      <div className="h-4 bg-gray-200 rounded w-24" />
      <div className="h-4 bg-gray-200 rounded w-12" />
      <div className="ml-auto h-9 bg-gray-200 rounded w-28" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Item row
// ---------------------------------------------------------------------------

interface ItemRowProps {
  item: LocalItem
  isFocused: boolean
  onConfirm: (itemId: string, qty: number) => void
  onEdit: (item: LocalItem) => void
}

function ItemRow({ item, isFocused, onConfirm, onEdit }: ItemRowProps) {
  const isConfirmed = item.confirmedLocally
  const pendingQty = Number(item.pending_qty)
  const confirmedQty = item.confirmedQty ?? pendingQty
  const alreadyReceived = Number(item.already_received)

  return (
    <div
      className={[
        'border-b border-gray-200 px-4 py-3 flex items-center gap-2 min-h-[64px]',
        isConfirmed ? 'bg-gray-50' : 'bg-white',
        isFocused && !isConfirmed ? 'bg-blue-50' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {/* Focus indicator */}
      <span
        className="text-gray-900 font-bold text-sm w-4 flex-shrink-0"
        aria-hidden="true"
      >
        {isFocused && !isConfirmed ? '▶' : ''}
      </span>

      {/* Product name + qty info */}
      <div className="flex-1 min-w-0">
        <span
          className={[
            'font-bold text-sm uppercase tracking-wide',
            isConfirmed ? 'text-gray-400' : 'text-gray-900',
          ].join(' ')}
        >
          {item.product_name}
        </span>
        {isConfirmed ? (
          <span className="ml-2 text-sm text-gray-400">
            {confirmedQty} {item.unit}
          </span>
        ) : (
          <span className="ml-2 text-sm text-gray-600">
            {pendingQty} {item.unit}
          </span>
        )}
        <span className="block text-xs text-gray-400 mt-0.5">
          (saldo pendiente · ya recibido: {alreadyReceived} {item.unit})
        </span>
      </div>

      {/* Right side */}
      {isConfirmed ? (
        <span
          className="text-green-600 font-bold text-lg flex-shrink-0"
          aria-label="Confirmado"
        >
          ✓
        </span>
      ) : (
        <div className="flex gap-2 flex-shrink-0">
          <button
            id={`ok-${item.purchase_order_item_id}`}
            onClick={() => onConfirm(item.purchase_order_item_id, pendingQty)}
            className="min-h-[48px] px-3 text-sm font-semibold border bg-gray-900 text-white border-gray-900 active:opacity-70"
            aria-label={`Confirmar ${item.product_name} con cantidad pendiente`}
          >
            OK — llego asi
          </button>
          <button
            onClick={() => onEdit(item)}
            className="min-h-[48px] px-3 text-sm font-semibold border border-gray-400 text-gray-700 bg-white active:opacity-70"
            aria-label={`Editar cantidad de ${item.product_name}`}
          >
            editar
          </button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Edit modal (entrada-08)
// ---------------------------------------------------------------------------

interface EditModalProps {
  item: LocalItem
  onConfirm: (itemId: string, qty: number) => void
  onClose: () => void
}

function EditModal({ item, onConfirm, onClose }: EditModalProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [value, setValue] = useReducer(
    (_: string, next: string) => next,
    String(item.pending_qty),
  )

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [])

  function handleSubmit() {
    const parsed = parseFloat(value.replace(',', '.'))
    if (!isFinite(parsed) || parsed < 0) return
    onConfirm(item.purchase_order_item_id, parsed)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleSubmit()
    if (e.key === 'Escape') onClose()
  }

  const parsed = parseFloat(value.replace(',', '.'))
  const isValid = isFinite(parsed) && parsed >= 0

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black bg-opacity-50"
      role="dialog"
      aria-modal="true"
      aria-label={`Editar cantidad de ${item.product_name}`}
      onClick={onClose}
    >
      <div
        className="bg-white w-full max-w-sm mx-4 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal header */}
        <div className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3">
          <button
            onClick={onClose}
            className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
            aria-label="Cerrar edicion"
          >
            &lt;
          </button>
          <div>
            <p className="text-xs uppercase tracking-wide text-gray-400">ENTRADA</p>
            <p className="text-base font-bold uppercase tracking-wide">
              {item.product_name}
              <span className="font-normal text-gray-400 ml-2 text-sm normal-case">
                (saldo pendiente: {item.pending_qty} {item.unit})
              </span>
            </p>
          </div>
        </div>

        {/* Input */}
        <div className="px-6 py-8 flex flex-col items-center gap-4">
          <p className="text-sm text-gray-600 uppercase tracking-wide">
            Cantidad recibida en esta partida
          </p>
          <div className="flex items-center gap-3">
            <input
              ref={inputRef}
              type="number"
              inputMode="decimal"
              min="0"
              step="any"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={handleKeyDown}
              className="border-2 border-gray-900 text-3xl font-bold text-center w-36 py-3 focus:outline-none focus:border-blue-600"
              aria-label="Cantidad recibida"
            />
            <span className="text-lg text-gray-600">{item.unit}</span>
          </div>
        </div>

        {/* Submit */}
        <div className="px-6 pb-6">
          <button
            onClick={handleSubmit}
            disabled={!isValid}
            className={[
              'w-full min-h-[56px] text-base font-bold uppercase tracking-wide',
              isValid
                ? 'bg-gray-900 text-white active:opacity-70'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed',
            ].join(' ')}
          >
            OK y siguiente →
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Validated overlay (entrada-09)
// ---------------------------------------------------------------------------

interface ValidatedOverlayProps {
  supplierName: string
  partidaNumber: number
  orderStatus: 'open' | 'partially_received' | 'closed'
  onDone: () => void
}

function ValidatedOverlay({ supplierName, partidaNumber, orderStatus, onDone }: ValidatedOverlayProps) {
  useEffect(() => {
    const timer = setTimeout(onDone, 1500)
    return () => clearTimeout(timer)
  }, [onDone])

  const isClosed = orderStatus === 'closed'

  return (
    <div
      role="status"
      aria-live="assertive"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-white px-8 text-center"
    >
      <span className="text-green-500 text-8xl font-black mb-6" aria-hidden="true">
        ✓
      </span>
      <h1 className="text-2xl font-black uppercase tracking-wider text-gray-900 mb-3">
        {isClosed ? 'ORDEN COMPLETA' : 'PARTIDA REGISTRADA'}
      </h1>
      <p className="text-gray-600 text-base mb-10">
        {isClosed
          ? `${supplierName} — todo llego → stock actualizado`
          : `${supplierName} — partida #${partidaNumber} → stock actualizado`}
      </p>
      <button
        onClick={onDone}
        className="min-h-[56px] px-10 bg-gray-900 text-white font-bold text-base uppercase tracking-wide active:opacity-70"
        autoFocus
      >
        listo
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function VerificacionPartida() {
  const { orderId } = useParams<{ orderId: string }>()
  const navigate = useNavigate()
  const { userId } = useAuthWithGetters()

  const { data, isLoading, isError, refetch } = usePartidaDraft(orderId ?? '', userId)
  const validateMutation = useValidatePartida()

  // Local optimistic item state
  const [localItems, dispatch] = useReducer(itemsReducer, {})

  // Which item is being edited
  const [editingItem, setEditingItem] = useReducer(
    (_: LocalItem | null, next: LocalItem | null) => next,
    null,
  )

  // Toast
  const [toast, setToast] = useReducer(
    (_: ToastState, next: ToastState) => next,
    { visible: false, message: '' },
  )

  // Validated overlay state
  const [validatedResult, setValidatedResult] = useReducer(
    (_: { partidaNumber: number; orderStatus: 'open' | 'partially_received' | 'closed' } | null,
     next: { partidaNumber: number; orderStatus: 'open' | 'partially_received' | 'closed' } | null) => next,
    null,
  )

  // Guard for validate double-tap
  const validatingRef = useRef(false)

  // Init local items when data arrives
  useEffect(() => {
    if (data?.items) {
      dispatch({ type: 'INIT', items: data.items })
    }
  }, [data])

  // 409 on draft fetch — order no longer accepts partidas
  useEffect(() => {
    if (isError) {
      // We check the error type via the query error — axios throws with response.status
      // The retry:false in the query means we see this immediately
      setToast({ visible: true, message: 'Esta orden ya no acepta partidas' })
      setTimeout(() => navigate('/entradas'), 1500)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isError])

  // Dismiss toast after 3 seconds
  useEffect(() => {
    if (!toast.visible) return
    const t = setTimeout(() => setToast({ visible: false, message: '' }), 3000)
    return () => clearTimeout(t)
  }, [toast.visible])

  // Derived: ordered list
  const orderedItems: LocalItem[] = data
    ? data.items.map(
        (i) =>
          localItems[i.purchase_order_item_id] ?? {
            ...i,
            confirmedLocally: false,
            confirmedQty: null,
          },
      )
    : []

  const confirmedCount = orderedItems.filter((i) => i.confirmedLocally).length
  const totalCount = orderedItems.length
  const allConfirmed = totalCount > 0 && orderedItems.every((i) => i.confirmedLocally)

  const firstPendingIndex = orderedItems.findIndex((i) => !i.confirmedLocally)

  // ---------------------------------------------------------------------------
  // Confirm handler — local only, no server request per item
  // ---------------------------------------------------------------------------

  const handleConfirm = useCallback((itemId: string, qty: number) => {
    dispatch({ type: 'CONFIRM', itemId, qty })
    setEditingItem(null)
  }, [])

  // ---------------------------------------------------------------------------
  // Validate handler — single POST with all items
  // ---------------------------------------------------------------------------

  const handleValidate = useCallback(() => {
    if (!orderId || !data) return
    if (validatingRef.current) return
    validatingRef.current = true

    const items = orderedItems.map((item) => ({
      purchase_order_item_id: item.purchase_order_item_id,
      received_qty: item.confirmedQty ?? Number(item.pending_qty),
    }))

    validateMutation.mutate(
      { orderId, body: { items } },
      {
        onSuccess: (response) => {
          validatingRef.current = false
          const orderStatus = response.data.order_status
          const partidaNumber = response.data.partida_number
          setValidatedResult({ partidaNumber, orderStatus })
        },
        onError: (error) => {
          validatingRef.current = false
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const status = (error as any)?.response?.status
          if (status === 409) {
            setToast({ visible: true, message: 'Esta orden ya no acepta partidas' })
            setTimeout(() => navigate('/entradas'), 1500)
          } else {
            setToast({ visible: true, message: 'No se pudo registrar la partida. Toca de nuevo.' })
          }
        },
      },
    )
  }, [orderId, data, orderedItems, validateMutation, navigate])

  // ---------------------------------------------------------------------------
  // Guard
  // ---------------------------------------------------------------------------

  if (!orderId) return null

  // ---------------------------------------------------------------------------
  // Validated overlay
  // ---------------------------------------------------------------------------

  if (validatedResult && data) {
    return (
      <ValidatedOverlay
        supplierName={data.supplier_name}
        partidaNumber={validatedResult.partidaNumber}
        orderStatus={validatedResult.orderStatus}
        onDone={() => navigate('/entradas')}
      />
    )
  }

  // ---------------------------------------------------------------------------
  // Loading
  // ---------------------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
        <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
          <button
            onClick={() => navigate('/entradas')}
            className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
            aria-label="Volver"
          >
            &lt;
          </button>
          <div className="h-5 bg-gray-700 rounded w-48 animate-pulse" />
        </header>
        <main className="flex-1 overflow-y-auto">
          {[1, 2, 3].map((n) => (
            <SkeletonItemRow key={n} />
          ))}
        </main>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Error (404 / network error on draft fetch)
  // ---------------------------------------------------------------------------

  if (isError && !data) {
    return (
      <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
        <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
          <button
            onClick={() => navigate('/entradas')}
            className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
            aria-label="Volver"
          >
            &lt;
          </button>
          <h1 className="text-lg font-bold uppercase tracking-wide">ENTRADA</h1>
        </header>
        <main className="flex-1 flex flex-col items-center justify-center px-8 text-center gap-4">
          <p className="text-gray-700 font-medium">No se pudo cargar la orden.</p>
          <button
            onClick={() => void refetch()}
            className="min-h-[48px] px-6 bg-gray-900 text-white font-semibold active:opacity-70"
          >
            Reintentar
          </button>
        </main>
        {toast.visible && (
          <div
            role="alert"
            aria-live="assertive"
            className="fixed bottom-20 left-4 right-4 z-50 bg-red-600 text-white px-4 py-3 text-sm font-medium"
          >
            {toast.message}
          </div>
        )}
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Verification screen
  // ---------------------------------------------------------------------------

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate('/entradas')}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver"
        >
          &lt;
        </button>
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-400">ENTRADA</p>
          <h1 className="text-base font-bold uppercase tracking-wide truncate flex-1 min-w-0">
            {data?.supplier_name ?? ''}{data ? ` — Partida #${data.partida_number}` : ''}
          </h1>
        </div>
      </header>

      {/* Item list */}
      <main className="flex-1 overflow-y-auto">
        {totalCount === 0 ? (
          <div className="flex flex-col items-center justify-center h-full px-8 text-center gap-4 py-16">
            <p className="text-gray-600 font-medium">
              Esta orden no tiene productos con saldo pendiente. Avisa al dueno.
            </p>
            <button
              onClick={() => navigate('/entradas')}
              className="min-h-[48px] px-6 bg-gray-900 text-white font-semibold active:opacity-70"
            >
              Volver a la bandeja
            </button>
          </div>
        ) : (
          orderedItems.map((item, idx) => (
            <ItemRow
              key={item.purchase_order_item_id}
              item={item}
              isFocused={idx === firstPendingIndex}
              onConfirm={handleConfirm}
              onEdit={(i) => setEditingItem(i)}
            />
          ))
        )}
      </main>

      {/* Sticky footer */}
      <footer className="sticky bottom-0 border-t border-gray-200 bg-white px-4 py-3 flex-shrink-0">
        <p className="text-sm text-gray-600 text-center mb-2">
          al validar, esta partida impacta el stock
        </p>
        <button
          onClick={handleValidate}
          disabled={!allConfirmed || validateMutation.isPending}
          className={[
            'w-full min-h-[56px] font-bold text-base uppercase tracking-wide',
            allConfirmed && !validateMutation.isPending
              ? 'bg-gray-900 text-white active:opacity-70'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed',
          ].join(' ')}
          aria-label={`Validar partida ${confirmedCount} de ${totalCount}`}
        >
          {validateMutation.isPending
            ? 'registrando...'
            : `validar partida (${confirmedCount}/${totalCount})`}
        </button>
      </footer>

      {/* Edit modal */}
      {editingItem && (
        <EditModal
          item={editingItem}
          onConfirm={handleConfirm}
          onClose={() => setEditingItem(null)}
        />
      )}

      {/* Toast */}
      {toast.visible && (
        <div
          role="alert"
          aria-live="assertive"
          className="fixed bottom-20 left-4 right-4 z-50 bg-red-600 text-white px-4 py-3 text-sm font-medium"
        >
          {toast.message}
        </div>
      )}
    </div>
  )
}
