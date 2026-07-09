import { useEffect, useReducer, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  useDelivery,
  useOpenDelivery,
  useConfirmItem,
  useValidateDelivery,
} from '../lib/deliveries'
import { formatRelativeDate } from '../lib/date'
import type { DeliveryItem } from '../lib/types'

// ---------------------------------------------------------------------------
// Local item state — mirrors server state with optimistic overlay
// ---------------------------------------------------------------------------

interface LocalItem extends DeliveryItem {
  // optimistic: true while the confirm request is in flight
  confirming: boolean
  // confirmed locally (optimistic or server-confirmed)
  confirmedLocally: boolean
  // the qty we last sent to /confirm (may differ from announced)
  confirmedQty: number | null
}

type ItemMap = Record<string, LocalItem>

type Action =
  | { type: 'INIT'; items: DeliveryItem[] }
  | { type: 'OPTIMISTIC_CONFIRM'; itemId: string; qty: number }
  | { type: 'REVERT_CONFIRM'; itemId: string }
  | { type: 'SERVER_CONFIRMED'; itemId: string; qty: number }

function itemsReducer(state: ItemMap, action: Action): ItemMap {
  switch (action.type) {
    case 'INIT': {
      const next: ItemMap = {}
      for (const item of action.items) {
        const alreadyConfirmed = item.received_qty !== null
        next[item.id] = {
          ...item,
          confirming: false,
          confirmedLocally: alreadyConfirmed,
          confirmedQty: alreadyConfirmed ? item.received_qty : null,
        }
      }
      return next
    }
    case 'OPTIMISTIC_CONFIRM': {
      const prev = state[action.itemId]
      if (!prev) return state
      return {
        ...state,
        [action.itemId]: {
          ...prev,
          confirming: true,
          confirmedLocally: true,
          confirmedQty: action.qty,
        },
      }
    }
    case 'REVERT_CONFIRM': {
      const prev = state[action.itemId]
      if (!prev) return state
      return {
        ...state,
        [action.itemId]: {
          ...prev,
          confirming: false,
          // If the server had confirmed it before (received_qty !== null), keep
          // it confirmed — the revert is only for the optimistic layer.
          confirmedLocally: prev.received_qty !== null,
          confirmedQty: prev.received_qty !== null ? prev.received_qty : null,
        },
      }
    }
    case 'SERVER_CONFIRMED': {
      const prev = state[action.itemId]
      if (!prev) return state
      return {
        ...state,
        [action.itemId]: {
          ...prev,
          confirming: false,
          confirmedLocally: true,
          confirmedQty: action.qty,
          received_qty: action.qty,
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
// Skeleton rows for loading state
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
  const differsFromAnnounced =
    isConfirmed &&
    item.confirmedQty !== null &&
    item.confirmedQty !== item.announced_qty

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

      {/* Product name + qty */}
      <div className="flex-1 min-w-0">
        <span
          className={[
            'font-bold text-sm uppercase tracking-wide',
            isConfirmed ? 'text-gray-400' : 'text-gray-900',
          ].join(' ')}
        >
          {item.product_name}
        </span>
        <span
          className={[
            'ml-2 text-sm',
            isConfirmed ? 'text-gray-400' : 'text-gray-600',
          ].join(' ')}
        >
          {isConfirmed && item.confirmedQty !== null
            ? `${item.confirmedQty} ${item.unit}`
            : `${item.announced_qty} ${item.unit}`}
        </span>
        {differsFromAnnounced && (
          <span className="ml-2 text-xs text-gray-400">
            (anunciado: {item.announced_qty} {item.unit})
          </span>
        )}
      </div>

      {/* Right side */}
      {isConfirmed ? (
        <span className="text-green-600 font-bold text-lg flex-shrink-0" aria-label="Confirmado">
          ✓
        </span>
      ) : (
        <div className="flex gap-2 flex-shrink-0">
          <button
            onClick={() => onConfirm(item.id, item.announced_qty)}
            disabled={item.confirming}
            className={[
              'min-h-[48px] px-3 text-sm font-semibold border',
              item.confirming
                ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-wait'
                : 'bg-gray-900 text-white border-gray-900 active:opacity-70',
            ].join(' ')}
            aria-label={`Confirmar ${item.product_name} con cantidad anunciada`}
          >
            OK — llegó así
          </button>
          <button
            onClick={() => onEdit(item)}
            disabled={item.confirming}
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
// Edit quantity modal
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
    String(item.announced_qty),
  )

  useEffect(() => {
    // Auto-focus, select all so the operator can overtype immediately
    if (inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [])

  function handleSubmit() {
    const parsed = parseFloat(value.replace(',', '.'))
    if (isNaN(parsed) || parsed < 0) return
    onConfirm(item.id, parsed)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleSubmit()
    if (e.key === 'Escape') onClose()
  }

  const parsed = parseFloat(value.replace(',', '.'))
  const isValid = !isNaN(parsed) && parsed >= 0

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black bg-opacity-50"
      role="dialog"
      aria-modal="true"
      aria-label={`Editar cantidad de ${item.product_name}`}
    >
      <div className="bg-white w-full max-w-sm mx-4 flex flex-col">
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
                (anunciado: {item.announced_qty} {item.unit})
              </span>
            </p>
          </div>
        </div>

        {/* Input */}
        <div className="px-6 py-8 flex flex-col items-center gap-4">
          <p className="text-sm text-gray-600 uppercase tracking-wide">Cantidad recibida</p>
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
// Validated overlay (Pantalla 4)
// ---------------------------------------------------------------------------

interface ValidatedOverlayProps {
  supplierName: string
  itemCount: number
  onDone: () => void
}

function ValidatedOverlay({ supplierName, itemCount, onDone }: ValidatedOverlayProps) {
  useEffect(() => {
    const timer = setTimeout(onDone, 1500)
    return () => clearTimeout(timer)
  }, [onDone])

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
        ENTREGA VALIDADA
      </h1>
      <p className="text-gray-600 text-base mb-10">
        {supplierName} — {itemCount} {itemCount === 1 ? 'producto' : 'productos'} → stock
        actualizado
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
// Read-only view for validada deliveries
// ---------------------------------------------------------------------------

interface ReadOnlyViewProps {
  items: LocalItem[]
  validatedAt: string | null
  supplierName: string
  onBack: () => void
}

function ReadOnlyView({ items, validatedAt, supplierName, onBack }: ReadOnlyViewProps) {
  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={onBack}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver"
        >
          &lt;
        </button>
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-400">ENTRADA</p>
          <h1 className="text-base font-bold uppercase tracking-wide">{supplierName}</h1>
        </div>
      </header>

      <div className="px-4 py-3 bg-green-50 border-b border-green-200">
        <p className="text-sm text-green-800 font-medium">
          Entrega validada{validatedAt ? ` el ${formatRelativeDate(validatedAt)}` : ''}.
        </p>
      </div>

      <main className="flex-1 overflow-y-auto">
        {items.map((item) => (
          <div
            key={item.id}
            className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-2 min-h-[56px]"
          >
            <span className="flex-1 font-bold text-sm uppercase tracking-wide text-gray-500">
              {item.product_name}
            </span>
            <span className="text-sm text-gray-500">
              recibido: {item.received_qty ?? '—'} {item.unit}
            </span>
            {item.received_qty !== item.announced_qty && (
              <span className="text-xs text-gray-400 ml-1">
                (anunciado: {item.announced_qty})
              </span>
            )}
          </div>
        ))}
      </main>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function Verificacion() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data, isLoading, isError, refetch } = useDelivery(id ?? '')
  const openMutation = useOpenDelivery()
  const confirmMutation = useConfirmItem()
  const validateMutation = useValidateDelivery()

  // Local optimistic item state
  const [localItems, dispatch] = useReducer(itemsReducer, {})

  // Which item is being edited in the modal
  const [editingItem, setEditingItem] = useReducer(
    (_: LocalItem | null, next: LocalItem | null) => next,
    null,
  )

  // Toast state
  const [toast, setToast] = useReducer(
    (_: ToastState, next: ToastState) => next,
    { visible: false, message: '' },
  )

  // Show the validated confirmation overlay
  const [showValidated, setShowValidated] = useReducer((_: boolean, next: boolean) => next, false)

  // Has the /open call been attempted for this load? Prevents double-firing.
  const openAttempted = useRef(false)

  // Init local items when server data arrives
  useEffect(() => {
    if (data?.items) {
      dispatch({ type: 'INIT', items: data.items })
    }
  }, [data])

  // Auto-open: if status is no_leida, call /open once on mount
  useEffect(() => {
    if (data && data.status === 'no_leida' && !openAttempted.current) {
      openAttempted.current = true
      openMutation.mutate(data.id)
    }
    // If status is en_verificacion, we already opened it (idempotent)
    if (data && data.status === 'en_verificacion' && !openAttempted.current) {
      openAttempted.current = true
    }
  }, [data, openMutation])

  // Dismiss toast after 3 seconds
  useEffect(() => {
    if (!toast.visible) return
    const t = setTimeout(() => setToast({ visible: false, message: '' }), 3000)
    return () => clearTimeout(t)
  }, [toast.visible])

  // Derived: ordered list from localItems preserving server order
  const orderedItems: LocalItem[] = data
    ? data.items.map((i) => localItems[i.id] ?? { ...i, confirming: false, confirmedLocally: false, confirmedQty: null })
    : []

  const confirmedCount = orderedItems.filter((i) => i.confirmedLocally).length
  const totalCount = orderedItems.length
  const allConfirmed = totalCount > 0 && confirmedCount === totalCount

  // First pending item index (for ▶ focus indicator)
  const firstPendingIndex = orderedItems.findIndex((i) => !i.confirmedLocally)

  // ---------------------------------------------------------------------------
  // Confirm handler (shared by row OK button and modal OK)
  // ---------------------------------------------------------------------------

  const handleConfirm = useCallback(
    (itemId: string, qty: number) => {
      if (!id) return

      // Optimistic update
      dispatch({ type: 'OPTIMISTIC_CONFIRM', itemId, qty })

      // Close modal if open
      setEditingItem(null)

      confirmMutation.mutate(
        { deliveryId: id, itemId, receivedQty: qty },
        {
          onSuccess: () => {
            dispatch({ type: 'SERVER_CONFIRMED', itemId, qty })
          },
          onError: () => {
            dispatch({ type: 'REVERT_CONFIRM', itemId })
            setToast({
              visible: true,
              message: navigator.onLine
                ? 'No se pudo confirmar. Intentá de nuevo.'
                : 'Sin conexion — se guarda cuando vuelva.',
            })
          },
        },
      )
    },
    [id, confirmMutation],
  )

  // ---------------------------------------------------------------------------
  // Validate handler
  // ---------------------------------------------------------------------------

  const handleValidate = useCallback(() => {
    if (!id || !data) return

    validateMutation.mutate(id, {
      onSuccess: () => {
        setShowValidated(true)
      },
      onError: (error) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const status = (error as any)?.response?.status
        if (status === 409) {
          setToast({ visible: true, message: 'Esta entrega ya fue validada.' })
          setTimeout(() => navigate('/'), 1500)
        } else {
          setToast({ visible: true, message: 'No se pudo validar. Tocá de nuevo.' })
        }
      },
    })
  }, [id, data, validateMutation, navigate])

  // ---------------------------------------------------------------------------
  // Guard: no id param (should never happen due to router)
  // ---------------------------------------------------------------------------

  if (!id) {
    return null
  }

  // ---------------------------------------------------------------------------
  // Loading state
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
          <div className="flex flex-col">
            {[1, 2, 3, 4].map((n) => (
              <SkeletonItemRow key={n} />
            ))}
          </div>
        </main>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Error state (no data at all)
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
          <p className="text-gray-700 font-medium">No se pudo cargar la entrega.</p>
          <button
            onClick={() => void refetch()}
            className="min-h-[48px] px-6 bg-gray-900 text-white font-semibold active:opacity-70"
          >
            Reintentar
          </button>
        </main>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Read-only: validada
  // ---------------------------------------------------------------------------

  if (data && data.status === 'validada') {
    return (
      <ReadOnlyView
        items={orderedItems}
        validatedAt={data.validated_at}
        supplierName={data.supplier_name}
        onBack={() => navigate('/entradas')}
      />
    )
  }

  // ---------------------------------------------------------------------------
  // Validated confirmation overlay (Pantalla 4)
  // ---------------------------------------------------------------------------

  if (showValidated && data) {
    return (
      <ValidatedOverlay
        supplierName={data.supplier_name}
        itemCount={data.item_count}
        onDone={() => navigate('/')}
      />
    )
  }

  // ---------------------------------------------------------------------------
  // Verification screen (Pantalla 2 + 3)
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
          <h1 className="text-base font-bold uppercase tracking-wide">
            {data?.supplier_name ?? ''}
          </h1>
        </div>
      </header>

      {/* Item list */}
      <main className="flex-1 overflow-y-auto">
        <p className="text-xs text-gray-400 px-4 py-2 border-b border-gray-200 bg-white">
          al validar, la entrega impacta el stock
        </p>
        {orderedItems.map((item, idx) => (
          <ItemRow
            key={item.id}
            item={item}
            isFocused={idx === firstPendingIndex}
            onConfirm={handleConfirm}
            onEdit={(i) => setEditingItem(i)}
          />
        ))}
      </main>

      {/* Validate button */}
      <div className="flex-shrink-0 px-4 py-3 bg-white border-t border-gray-200">
        <button
          onClick={handleValidate}
          disabled={!allConfirmed || validateMutation.isPending}
          className={[
            'w-full min-h-[56px] font-bold text-base uppercase tracking-wide',
            allConfirmed && !validateMutation.isPending
              ? 'bg-gray-900 text-white active:opacity-70'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed',
          ].join(' ')}
          aria-label={`Validar entrega ${confirmedCount} de ${totalCount}`}
        >
          {validateMutation.isPending
            ? 'validando...'
            : `validar entrega (${confirmedCount}/${totalCount})`}
        </button>
      </div>

      {/* Edit modal (Pantalla 3) */}
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
