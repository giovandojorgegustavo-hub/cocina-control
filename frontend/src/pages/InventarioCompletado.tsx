/**
 * /inventario/completado — Pantalla 3: Confirmación final del conteo
 *
 * Auto-navigates to home after 1.5s.
 * NEVER shows quantities, totals, or differences (Principio #1).
 */
import { useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

interface LocationState {
  productCount?: number
}

export function InventarioCompletado() {
  const navigate = useNavigate()
  const location = useLocation()
  const state = location.state as LocationState | null

  const productCount = state?.productCount ?? 0

  // Auto-navigate to home after 1.5s
  useEffect(() => {
    const timer = setTimeout(() => {
      navigate('/', { replace: true })
    }, 1500)
    return () => clearTimeout(timer)
  }, [navigate])

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
          onClick={() => navigate('/inventario', { replace: true })}
          className="flex-1 min-h-[56px] text-sm font-semibold border border-gray-400 text-gray-700 bg-white active:opacity-70 uppercase tracking-wide"
        >
          corregir un producto
        </button>

        <button
          data-testid="btn-listo"
          onClick={() => navigate('/', { replace: true })}
          className="flex-1 min-h-[56px] font-bold text-base bg-gray-900 text-white active:opacity-70 uppercase tracking-wide"
          autoFocus
        >
          listo
        </button>
      </div>
    </div>
  )
}
