import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Login } from './pages/Login'
import { Home } from './pages/Home'
import { Bandeja } from './pages/Bandeja'
import { Verificacion } from './pages/Verificacion'
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
    path: '/entradas',
    element: (
      <RequireAuth>
        <RequireRole role="operator">
          <Bandeja />
        </RequireRole>
      </RequireAuth>
    ),
  },
  {
    path: '/entradas/:id',
    element: (
      <RequireAuth>
        <RequireRole role="operator">
          <Verificacion />
        </RequireRole>
      </RequireAuth>
    ),
  },
  {
    // Placeholder for Frontend #6 — inventory screen
    path: '/inventario',
    element: (
      <RequireAuth>
        <RequireRole role="operator">
          <div className="min-h-screen flex items-center justify-center bg-gray-50">
            <p className="text-gray-500 text-sm">Inventario — viene en Frontend #6</p>
          </div>
        </RequireRole>
      </RequireAuth>
    ),
  },
  {
    // Placeholder for Frontend #5 — new order screen
    path: '/pedidos/nuevo',
    element: (
      <RequireAuth>
        <RequireRole role="operator">
          <div className="min-h-screen flex items-center justify-center bg-gray-50">
            <p className="text-gray-500 text-sm">Nuevo pedido — viene en Frontend #5</p>
          </div>
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
