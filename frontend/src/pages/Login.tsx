import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthWithGetters } from '../lib/auth'
import { apiClient } from '../lib/api'
import type { UserRole } from '../lib/auth'

type ErrorKind = 'credentials' | 'rate_limit' | 'network' | 'offline' | null

interface LoginResponse {
  token: string
  role: UserRole
  user_id: string
}

export function Login() {
  const navigate = useNavigate()
  const { setToken, role } = useAuthWithGetters()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ErrorKind>(null)
  const [isOffline, setIsOffline] = useState(!navigator.onLine)

  // Redirect if already authenticated
  useEffect(() => {
    if (role === 'operator') navigate('/', { replace: true })
    else if (role === 'owner') navigate('/tablero', { replace: true })
  }, [role, navigate])

  useEffect(() => {
    function handleOnline() { setIsOffline(false) }
    function handleOffline() { setIsOffline(true) }
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (isOffline) {
      setError('offline')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const { data } = await apiClient.post<LoginResponse>('/auth/login', {
        email,
        password,
      })
      setToken(data.token)
      if (data.role === 'operator') {
        navigate('/', { replace: true })
      } else {
        navigate('/tablero', { replace: true })
      }
    } catch (err: unknown) {
      if (!navigator.onLine) {
        setError('offline')
        return
      }
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 401) {
        setError('credentials')
      } else if (status === 429) {
        setError('rate_limit')
      } else {
        setError('network')
      }
    } finally {
      setLoading(false)
    }
  }

  const errorMessages: Record<NonNullable<ErrorKind>, string> = {
    credentials: 'Email o contraseña incorrectos',
    rate_limit: 'Demasiados intentos, esperá un minuto',
    network: 'No se pudo entrar, probá de nuevo',
    offline: 'Sin conexión',
  }

  const isDisabled = loading || isOffline

  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm space-y-8">
        <h1 className="text-4xl font-bold text-center text-gray-900">
          Cocina Control
        </h1>

        <form
          onSubmit={handleSubmit}
          className="space-y-4"
          aria-label="Formulario de acceso"
        >
          <div className="space-y-2">
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-700"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              autoFocus
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isDisabled}
              placeholder="operario@cocina.com"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-gray-900 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed"
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700"
            >
              Contraseña
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isDisabled}
              placeholder="••••••••"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-gray-900 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed"
            />
          </div>

          {error && (
            <p role="alert" className="text-sm text-red-600">
              {errorMessages[error]}
            </p>
          )}

          <button
            type="submit"
            disabled={isDisabled}
            className="w-full min-h-[56px] bg-gray-900 text-white font-semibold rounded-lg disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed active:bg-gray-700"
          >
            {loading ? 'Entrando...' : 'Entrar'}
          </button>
        </form>
      </div>
    </main>
  )
}
