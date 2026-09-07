import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthWithGetters } from '../lib/auth'
import { apiClient } from '../lib/api'

interface ActionCardProps {
  title: string
  subtitle: string
  to: string
}

// Dark, touch-friendly card. Keeps the kitchen-first visual language (dark
// surface, big tap target) but now lives inside a grouped grid instead of a
// full-height column, so the home reads as a menu rather than a wall.
function ActionCard({ title, subtitle, to }: ActionCardProps) {
  const navigate = useNavigate()

  return (
    <button
      onClick={() => navigate(to)}
      className={[
        'flex flex-col items-start justify-center text-left',
        // Generous tap target for kitchen staff (min 48px WAI-ARIA, ~120px here)
        'min-h-[120px] min-w-[48px] w-full',
        'bg-gray-900 text-white',
        'px-5 py-6',
        'rounded-lg border-0',
        'active:bg-gray-700',
      ].join(' ')}
      aria-label={`${title} — ${subtitle}`}
    >
      <span className="text-2xl md:text-3xl font-black tracking-wide uppercase leading-none">
        {title}
      </span>
      <span className="mt-2 text-sm md:text-base font-normal text-gray-400 normal-case">
        {subtitle}
      </span>
    </button>
  )
}

// Small uppercase section header — same lightweight style as Precios' headers.
function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-3">
      {children}
    </h2>
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
    <div className="min-h-screen flex flex-col bg-gray-50">
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
        Grouped menu. Kitchen staff (cocinero) only see OPERACIÓN; owner/admin
        also get the CARTA section. Role comes synchronously from the decoded
        JWT (useAuthWithGetters), so the CARTA section never flashes for a
        cocinero — it is simply never rendered unless canCreateOrders is true.
      */}
      <main className="flex-1 px-4 py-6 flex flex-col gap-8">
        {/* OPERACIÓN — visible to every role */}
        <section aria-label="Operación">
          <SectionHeader>Operación</SectionHeader>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <ActionCard title="Entrada" subtitle="Llegó una entrega" to="/entradas" />
            <ActionCard title="Inventario" subtitle="Contar stock" to="/inventario" />
            <ActionCard title="Pedidos" subtitle="Bandeja y foto" to="/pedidos" />
            {canCreateOrders && (
              <ActionCard title="Nueva orden" subtitle="Cargar compra" to="/ordenes/nueva" />
            )}
          </div>
        </section>

        {/* CARTA — owner/admin only */}
        {canCreateOrders && (
          <section aria-label="Carta">
            <SectionHeader>Carta</SectionHeader>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <ActionCard title="Precios y descuentos" subtitle="Carta y promociones" to="/precios" />
              <ActionCard title="Extras y opciones" subtitle="Adicionales por grupo" to="/opciones" />
              <ActionCard title="Distritos de reparto" subtitle="Zonas y tarifas" to="/zonas" />
              <ActionCard title="Asistente" subtitle="Cambios por chat" to="/asistente" />
            </div>
          </section>
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
