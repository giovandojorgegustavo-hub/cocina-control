import { useNavigate, Link } from 'react-router-dom'
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
  const { clearToken, userId } = useAuthWithGetters()

  async function handleLogout() {
    try {
      await apiClient.post('/auth/logout')
    } catch {
      // best-effort — ignore errors, always clear locally
    }
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
        Main area: 3 action buttons.
        Tablet landscape (md+): side by side, each 1/3 width, filling remaining height.
        Mobile: stacked vertically, each ~1/4 screen height.
      */}
      <main className="flex-1 flex flex-col md:flex-row gap-px bg-gray-300 overflow-hidden">
        <ActionButton title="ENTRADA" subtitle="llegó una entrega" to="/entradas" />
        <ActionButton title="INVENTARIO" subtitle="contar stock" to="/inventario" />
        <ActionButton title="PEDIDO" subtitle="foto al empacar" to="/pedidos/nuevo" />
      </main>

      {/* Footer link */}
      <footer className="bg-gray-900 flex-shrink-0 flex justify-end items-center px-4 py-3">
        <Link
          to="#"
          onClick={(e) => {
            e.preventDefault()
            alert('Próximamente')
          }}
          className="text-xs text-gray-500 underline"
        >
          ver mis registros
        </Link>
      </footer>
    </div>
  )
}
