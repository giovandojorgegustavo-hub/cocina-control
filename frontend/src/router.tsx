import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Login } from './pages/Login'
import { Home } from './pages/Home'
import { RequireAuth, RequireRole } from './lib/guards'

function OwnerPlaceholder() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50">
      <p className="text-gray-500 text-sm">Tablero del dueño — viene en el proximo issue</p>
    </main>
  )
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/',
    element: (
      <RequireAuth>
        <RequireRole role="operator">
          <Home />
        </RequireRole>
      </RequireAuth>
    ),
  },
  {
    path: '/tablero',
    element: (
      <RequireAuth>
        <RequireRole role="owner">
          <OwnerPlaceholder />
        </RequireRole>
      </RequireAuth>
    ),
  },
  {
    path: '*',
    element: <Navigate to="/login" replace />,
  },
])
