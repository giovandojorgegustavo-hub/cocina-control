import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthWithGetters } from '../lib/auth'
import { apiClient } from '../lib/api'

interface ActionButtonProps {
  title: string
  subtitle: string
  to: string
}

function ActionButton({ title, subtitle, to }: ActionButtonProps) {
  const navigate = useNavigate()

  return (
    <button
      onClick={() => navigate(to)}
      className={[
        // Touch target: min 120px tall on mobile, fill available height on tablet
        'flex flex-col items-center justify-center',
        'min-h-[120px] md:min-h-0 md:flex-1',
        'w-full md:w-auto',
        'bg-gray-900 text-white',
        'px-4 py-6',
        'rounded-none border-0',
        'active:bg-gray-700',
        // Ensure tappable area is never below 48px (WAI-ARIA)
        'min-w-[48px]',
      ].join(' ')}
      aria-label={`${title} — ${subtitle}`}
    >
      <span className="text-3xl md:text-4xl font-black tracking-widest uppercase leading-none">
        {title}
      </span>
      <span className="mt-2 text-sm md:text-base font-normal text-gray-400 normal-case">
        {subtitle}
      </span>
    </button>
  )
}

export function Home() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { clearToken, userId, role } = useAuthWithGetters()

  const canCreateOrders = role === 'owner' || role === 'admin'

  async function handleLogout() {
    try {
      await apiClient.post('/auth/logout')
    } catch {
      // best-effort — ignore errors, always clear locally
    }
    // Clear query cache before token so next user never sees stale data
    queryClient.clear()
    clearToken()
    navigate('/login', { replace: true })
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center justify-between flex-shrink-0">
        <h1 className="text-xl font-bold tracking-wide">Cocina Control</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-300">{userId ?? 'usuario'}</span>
          <button
            onClick={handleLogout}
            className="min-h-[48px] min-w-[48px] px-4 text-sm text-gray-300 underline"
          >
            cerrar
          </button>
        </div>
      </header>

      {/*
        Main area: 3 (or 4) action buttons.
        Tablet landscape (md+): side by side, each filling available width, filling remaining height.
        Mobile: stacked vertically, each ~1/4 screen height.
        owner/admin get an extra NUEVA ORDEN button.
      */}
      <main className="flex-1 flex flex-col md:flex-row gap-px bg-gray-300 overflow-hidden">
        <ActionButton title="ENTRADA" subtitle="(llegó una entrega)" to="/entradas" />
        <ActionButton title="INVENTARIO" subtitle="(contar stock)" to="/inventario" />
        <ActionButton title="PEDIDO" subtitle="(foto al empacar)" to="/pedidos/nuevo" />
        {canCreateOrders && (
          <ActionButton title="NUEVA ORDEN" subtitle="(cargar compra)" to="/ordenes/nueva" />
        )}
      </main>

      {/* Footer — acceso a la bandeja de pedidos (issue #136): la bandeja
          existia pero ninguna pantalla navegaba hacia ella */}
      <footer className="bg-gray-900 flex-shrink-0">
        <button
          onClick={() => navigate('/pedidos')}
          className="w-full min-h-[48px] px-4 py-3 flex justify-between items-center text-sm text-gray-300 active:bg-gray-700"
          aria-label="Ver pedidos — pendientes y completados"
        >
          <span className="font-semibold uppercase tracking-wide">ver pedidos</span>
          <span className="text-gray-500">pendientes y completados →</span>
        </button>
      </footer>
    </div>
  )
}
