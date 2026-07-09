/**
 * /inventario — Pantalla 1: Lista de productos a contar
 *
 * Operator only. Starts or resumes an in-progress inventory count.
 * Never shows expected values, previous stock, or averages (Principio #1).
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../lib/api'
import { useProducts } from '../lib/products'
import {
  getSavedCountId,
  saveCountId,
  clearSavedCountId,
  startInventoryCount,
  useCompleteInventoryCount,
} from '../lib/inventory'
import { useAuthWithGetters } from '../lib/auth'
import { formatDayMonth } from '../lib/date'
import type { InventoryCount, InventoryCountItem, Product } from '../lib/types'

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function SkeletonRow() {
  return (
    <div
      role="status"
      aria-label="Cargando producto"
      className="bg-white border-b border-gray-200 px-4 py-4 animate-pulse flex items-center gap-3 min-h-[64px]"
    >
      <div className="h-4 bg-gray-200 rounded w-4 flex-shrink-0" />
      <div className="flex-1 h-4 bg-gray-200 rounded w-32" />
      <div className="h-9 bg-gray-200 rounded w-24 flex-shrink-0" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Product row — pending
// ---------------------------------------------------------------------------

interface PendingRowProps {
  product: Product
  isFocused: boolean
  onCount: (productId: string) => void
}

function PendingRow({ product, isFocused, onCount }: PendingRowProps) {
  return (
    <div
      className={[
        'border-b border-gray-200 px-4 py-3 flex items-center gap-2 min-h-[64px] bg-white',
        isFocused ? 'bg-blue-50' : '',
      ].join(' ')}
    >
      <span className="w-4 flex-shrink-0 text-gray-900 font-bold text-sm" aria-hidden="true">
        {isFocused ? '▶' : ''}
      </span>

      <span className="flex-1 font-bold text-sm uppercase tracking-wide text-gray-900">
        {product.name}
      </span>

      <button
        onClick={() => onCount(product.id)}
        className="min-h-[48px] px-4 text-sm font-semibold bg-gray-900 text-white active:opacity-70"
        aria-label={`Contar ${product.name}`}
      >
        contar
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Product row — counted
// ---------------------------------------------------------------------------

interface CountedRowProps {
  product: Product
  item: InventoryCountItem
  onChange: (productId: string, itemId: string) => void
}

function CountedRow({ product, item, onChange }: CountedRowProps) {
  return (
    <div className="border-b border-gray-200 px-4 py-3 flex items-center gap-2 min-h-[64px] bg-gray-50">
      <span className="w-4 flex-shrink-0" aria-hidden="true" />

      <div className="flex-1 min-w-0">
        <span className="font-bold text-sm uppercase tracking-wide text-gray-400">
          {product.name}
        </span>
        <span className="ml-2 text-sm text-gray-400">
          contado {item.quantity} {product.unit}
        </span>
      </div>

      <button
        onClick={() => onChange(product.id, item.id)}
        className="min-h-[48px] px-4 text-sm font-semibold border border-gray-400 text-gray-500 bg-white active:opacity-70"
        aria-label={`Cambiar conteo de ${product.name}`}
      >
        cambiar
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function InventarioLista() {
  const navigate = useNavigate()
  const { userId } = useAuthWithGetters()

  // countId in state — drives the count query below
  const [countId, setCountId] = useState<string | null>(null)
  // 'idle' → bootstrap not started yet (or reset after 404)
  // 'loading' → bootstrap in flight
  // 'done' → countId is set and valid
  // 'error' → bootstrap failed (POST error)
  const [bootstrapState, setBootstrapState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')

  // Prevents double-start in StrictMode / concurrent renders
  const bootstrapStarted = useRef(false)

  // Inline query instead of useInventoryCount so we can detect 404 explicitly
  const {
    data: count,
    isLoading: countLoading,
    error: countQueryError,
  } = useQuery<InventoryCount>({
    queryKey: ['inventory-count', countId],
    queryFn: () =>
      apiClient.get<InventoryCount>(`/inventory-counts/${countId!}`).then((r) => r.data),
    enabled: countId !== null && bootstrapState === 'done',
    staleTime: 0,
    networkMode: 'offlineFirst',
    retry: false, // do not retry 404s
  })

  const { data: products, isLoading: productsLoading, isError: productsError } = useProducts()

  const completeMutation = useCompleteInventoryCount()

  // Toast
  const [toast, setToast] = useState<{ visible: boolean; message: string }>({
    visible: false,
    message: '',
  })

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast.visible) return
    const t = setTimeout(() => setToast({ visible: false, message: '' }), 3000)
    return () => clearTimeout(t)
  }, [toast.visible])

  // ---------------------------------------------------------------------------
  // Bootstrap: one effect, two phases.
  // Phase 1: on userId available, try saved count or POST new.
  // Phase 2: if the saved count returns a 404, clear it and POST new.
  // ---------------------------------------------------------------------------

  // Phase 1 — run once per userId
  useEffect(() => {
    if (!userId) return
    if (bootstrapStarted.current) return
    bootstrapStarted.current = true

    setBootstrapState('loading')

    const saved = getSavedCountId(userId)

    if (saved) {
      // Try to resume — if the server returns 404, Phase 2 handles it
      setCountId(saved)
      setBootstrapState('done')
    } else {
      startInventoryCount()
        .then((resp) => {
          saveCountId(userId, resp.id)
          setCountId(resp.id)
          setBootstrapState('done')
        })
        .catch(() => {
          setBootstrapState('error')
        })
    }
  }, [userId])

  // Phase 2 — saved count is gone (404) → clear and POST new
  useEffect(() => {
    if (!userId || !countQueryError) return

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const status = (countQueryError as any)?.response?.status
    if (status !== 404 && status !== 403) return // only handle "not found" cases

    // Clear the stale id
    clearSavedCountId(userId)
    setCountId(null)
    setBootstrapState('loading')
    bootstrapStarted.current = true // keep guard on to not re-run Phase 1

    startInventoryCount()
      .then((resp) => {
        saveCountId(userId, resp.id)
        setCountId(resp.id)
        setBootstrapState('done')
      })
      .catch(() => {
        setBootstrapState('error')
      })
  }, [userId, countQueryError])

  // ---------------------------------------------------------------------------
  // Derived data
  // ---------------------------------------------------------------------------

  // Build a map of product_id → effective item (most recent count per product)
  const itemByProductId: Record<string, InventoryCountItem> = {}
  if (count?.items) {
    for (const item of count.items) {
      // The server already returns only the leaf (effective) item per product.
      // We trust the backend contract from docs/diseno.md 6.e.
      itemByProductId[item.product_id] = item
    }
  }

  const activeProducts: Product[] = products ?? []

  const pendingProducts = activeProducts
    .filter((p) => !(p.id in itemByProductId))
    .sort((a, b) => a.name.localeCompare(b.name))

  const countedProducts = activeProducts
    .filter((p) => p.id in itemByProductId)
    .sort((a, b) => a.name.localeCompare(b.name))

  const totalCount = activeProducts.length
  const doneCount = countedProducts.length
  const allCounted = totalCount > 0 && doneCount === totalCount

  // Count date from the server response, fallback to today
  const countDateLabel = count?.started_at
    ? `conteo del ${formatDayMonth(count.started_at)}`
    : 'conteo en curso'

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleCount = useCallback(
    (productId: string) => {
      navigate(`/inventario/contar/${productId}`)
    },
    [navigate],
  )

  const handleChange = useCallback(
    (productId: string, itemId: string) => {
      navigate(`/inventario/contar/${productId}?item_id=${itemId}`)
    },
    [navigate],
  )

  const handleComplete = useCallback(() => {
    if (!countId || !userId) return
    if (completeMutation.isPending) return

    completeMutation.mutate(countId, {
      onSuccess: () => {
        clearSavedCountId(userId)
        navigate('/inventario/completado', {
          state: { productCount: totalCount },
        })
      },
      onError: () => {
        setToast({ visible: true, message: 'No se pudo terminar el conteo. Intentá de nuevo.' })
      },
    })
  }, [countId, userId, completeMutation, navigate, totalCount])

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  const isLoading = bootstrapState === 'idle' || bootstrapState === 'loading' || countLoading || productsLoading

  if (isLoading) {
    return (
      <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
        <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
          <button
            onClick={() => navigate('/')}
            className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
            aria-label="Volver al inicio"
          >
            &lt;
          </button>
          <h1 className="text-base font-bold uppercase tracking-wide">INVENTARIO</h1>
        </header>
        <main className="flex-1 overflow-y-auto">
          {[1, 2, 3, 4, 5].map((n) => (
            <SkeletonRow key={n} />
          ))}
        </main>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Bootstrap error state
  // ---------------------------------------------------------------------------

  if (bootstrapState === 'error' && !countId) {
    return (
      <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
        <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
          <button
            onClick={() => navigate('/')}
            className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
            aria-label="Volver al inicio"
          >
            &lt;
          </button>
          <h1 className="text-base font-bold uppercase tracking-wide">INVENTARIO</h1>
        </header>
        <main className="flex-1 flex flex-col items-center justify-center px-8 text-center gap-4">
          <p className="text-gray-700 font-medium">No se pudo iniciar el conteo.</p>
          <button
            onClick={() => {
              if (!userId) return
              bootstrapStarted.current = true
              setBootstrapState('loading')
              startInventoryCount()
                .then((resp) => {
                  saveCountId(userId, resp.id)
                  setCountId(resp.id)
                  setBootstrapState('done')
                })
                .catch(() => {
                  setBootstrapState('error')
                })
            }}
            className="min-h-[48px] px-6 bg-gray-900 text-white font-semibold active:opacity-70"
          >
            Reintentar
          </button>
        </main>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Products error
  // ---------------------------------------------------------------------------

  if (productsError && activeProducts.length === 0) {
    return (
      <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
        <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
          <button
            onClick={() => navigate('/')}
            className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
            aria-label="Volver al inicio"
          >
            &lt;
          </button>
          <h1 className="text-base font-bold uppercase tracking-wide">INVENTARIO — {countDateLabel}</h1>
        </header>
        <main className="flex-1 flex flex-col items-center justify-center px-8 text-center">
          <p className="text-gray-700 font-medium">No se pudo cargar el catálogo.</p>
        </main>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Empty catalogue
  // ---------------------------------------------------------------------------

  if (activeProducts.length === 0) {
    return (
      <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
        <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
          <button
            onClick={() => navigate('/')}
            className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
            aria-label="Volver al inicio"
          >
            &lt;
          </button>
          <h1 className="text-base font-bold uppercase tracking-wide">INVENTARIO</h1>
        </header>
        <main className="flex-1 flex flex-col items-center justify-center px-8 text-center">
          <p className="text-gray-700 font-medium" data-testid="empty-catalogue">
            No hay productos cargados. Pedile al dueño que los cargue.
          </p>
        </main>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Main list
  // ---------------------------------------------------------------------------

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate('/')}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver al inicio"
        >
          &lt;
        </button>
        <h1 className="text-base font-bold uppercase tracking-wide truncate">
          INVENTARIO — {countDateLabel}
        </h1>
      </header>

      <main className="flex-1 overflow-y-auto pb-24">
        {/* Pending products */}
        {pendingProducts.map((product, idx) => (
          <PendingRow
            key={product.id}
            product={product}
            isFocused={idx === 0}
            onCount={handleCount}
          />
        ))}

        {/* Counted products */}
        {countedProducts.map((product) => (
          <CountedRow
            key={product.id}
            product={product}
            item={itemByProductId[product.id]}
            onChange={handleChange}
          />
        ))}
      </main>

      {/* Sticky footer */}
      <footer className="fixed bottom-0 left-0 right-0 border-t border-gray-200 bg-white px-4 py-3">
        <button
          data-testid="terminar-conteo"
          onClick={handleComplete}
          disabled={!allCounted || completeMutation.isPending}
          className={[
            'w-full min-h-[56px] font-bold text-base uppercase tracking-wide',
            allCounted && !completeMutation.isPending
              ? 'bg-gray-900 text-white active:opacity-70'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed',
          ].join(' ')}
          aria-label={`Terminar conteo ${doneCount} de ${totalCount}`}
        >
          {completeMutation.isPending
            ? 'cerrando...'
            : `terminar conteo (${doneCount}/${totalCount})`}
        </button>
      </footer>

      {/* Toast */}
      {toast.visible && (
        <div
          role="alert"
          aria-live="assertive"
          className="fixed bottom-24 left-4 right-4 z-50 bg-red-600 text-white px-4 py-3 text-sm font-medium"
        >
          {toast.message}
        </div>
      )}
    </div>
  )
}
