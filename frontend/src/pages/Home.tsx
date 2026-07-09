import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'

export function Home() {
  const navigate = useNavigate()
  const clearToken = useAuth((s) => s.clearToken)

  function handleLogout() {
    clearToken()
    navigate('/login')
  }

  return (
    <main className="min-h-screen bg-gray-50">
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">Cocina Control</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-300">operator@placeholder</span>
          <button
            onClick={handleLogout}
            className="min-h-[48px] min-w-[48px] px-4 text-sm text-gray-300 underline"
          >
            cerrar
          </button>
        </div>
      </header>

      <section className="p-4">
        <p className="text-gray-500 text-sm text-center mt-8">
          Home — los tres botones grandes vienen en Frontend #2
        </p>
      </section>
    </main>
  )
}
