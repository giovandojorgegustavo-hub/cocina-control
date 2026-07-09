/**
 * /inventario/completado — Pantalla 3: Confirmación final del conteo
 *
 * Auto-navigates to home after 1.5s.
 * NEVER shows quantities, totals, or differences (Principio #1).
 *
 * QA H-02: the countId is cleared HERE (not in InventarioLista) so that the
 * "corregir un producto" button can navigate to /inventario while the countId is
 * still in localStorage. Only when the operator confirms they are done (listo /
 * auto-timer) do we erase it.
 *
 * QA H-09: if the operator lands here directly (no location.state), redirect to
 * /inventario to avoid a broken screen.
 */
import { useEffect } from 'react'
import { useNavigate, useLocation, Navigate } from 'react-router-dom'
import { clearSavedCountId } from '../lib/inventory'
import { useAuthWithGetters } from '../lib/auth'

interface LocationState {
  productCount?: number
  completedCountId?: string
}

export function InventarioCompletado() {
  const navigate = useNavigate()
  const location = useLocation()
  const { userId } = useAuthWithGetters()

  const state = location.state as LocationState | null

  const productCount = state?.productCount
  const completedCountId = state?.completedCountId

  // QA H-09: guard against direct URL access without state
  if (productCount === undefined) {
    return <Navigate to="/inventario" replace />
  }

  return (
    <InventarioCompletadoContent
      productCount={productCount}
      completedCountId={completedCountId ?? null}
      userId={userId}
      navigate={navigate}
    />
  )
}

// ---------------------------------------------------------------------------
// Separated into inner component so the hook rules are satisfied after the
// early-return guard above.
// ---------------------------------------------------------------------------

interface ContentProps {
  productCount: number
  completedCountId: string | null
  userId: string | null
  navigate: ReturnType<typeof useNavigate>
}

function InventarioCompletadoContent({
  productCount,
  completedCountId,
  userId,
  navigate,
}: ContentProps) {
  // QA H-02: clear the countId when done (listo / auto-timer)
  const clearCount = () => {
    if (userId && completedCountId) {
      clearSavedCountId(userId)
    }
  }

  // Auto-navigate to home after 1.5s and clear countId
  useEffect(() => {
    const timer = setTimeout(() => {
      clearCount()
      navigate('/', { replace: true })
    }, 1500)
    return () => clearTimeout(timer)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate])

  const handleListo = () => {
    clearCount()
    navigate('/', { replace: true })
  }

  const handleCorregir = () => {
    // QA H-02: do NOT clear countId here — it stays in localStorage so
    // /inventario can resume the completed count in correction mode.
    navigate('/inventario', {
      replace: true,
      state: { correctionMode: true },
    })
  }

  return (
    <div
      role="status"
      aria-live="assertive"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-white px-8 text-center gap-6"
    >
      {/* Large green checkmark */}
      <span
        className="text-green-500 text-9xl font-black leading-none"
        aria-hidden="true"
        data-testid="checkmark"
      >
        ✓
      </span>

      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-black uppercase tracking-wider text-gray-900">
          INVENTARIO REGISTRADO
        </h1>
        <p className="text-gray-600 text-base" data-testid="product-count-label">
          {productCount} {productCount === 1 ? 'producto contado' : 'productos contados'}
        </p>
      </div>

      <div className="flex gap-3 w-full max-w-sm mt-4">
        <button
          data-testid="btn-corregir"
          onClick={handleCorregir}
          className="flex-1 min-h-[56px] text-sm font-semibold border border-gray-400 text-gray-700 bg-white active:opacity-70 uppercase tracking-wide"
        >
          corregir un producto
        </button>

        <button
          data-testid="btn-listo"
          onClick={handleListo}
          className="flex-1 min-h-[56px] font-bold text-base bg-gray-900 text-white active:opacity-70 uppercase tracking-wide"
          autoFocus
        >
          listo
        </button>
      </div>
    </div>
  )
}
