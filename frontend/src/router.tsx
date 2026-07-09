import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Login } from './pages/Login'
import { Home } from './pages/Home'
import { Bandeja } from './pages/Bandeja'
import { Verificacion } from './pages/Verificacion'
import { NuevoPedido } from './pages/NuevoPedido'
import { BandejaPedidos } from './pages/BandejaPedidos'
import { CompletarPedido } from './pages/CompletarPedido'
import { InventarioLista } from './pages/InventarioLista'
import { ContarProducto } from './pages/ContarProducto'
import { InventarioCompletado } from './pages/InventarioCompletado'
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
    path: '/inventario',
    element: (
      <RequireAuth>
        <RequireRole role="operator">
          <InventarioLista />
        </RequireRole>
      </RequireAuth>
    ),
  },
  {
    path: '/inventario/contar/:productId',
    element: (
      <RequireAuth>
        <RequireRole role="operator">
          <ContarProducto />
        </RequireRole>
      </RequireAuth>
    ),
  },
  {
    path: '/inventario/completado',
    element: (
      <RequireAuth>
        <RequireRole role="operator">
          <InventarioCompletado />
        </RequireRole>
      </RequireAuth>
    ),
  },
  {
    path: '/pedidos/nuevo',
    element: (
      <RequireAuth>
        <RequireRole role="operator">
          <NuevoPedido />
        </RequireRole>
      </RequireAuth>
    ),
  },
  {
    // Bandeja de pedidos — accessible to operator and owner
    // The role filter is enforced by the backend; RequireAuth is enough here.
    path: '/pedidos',
    element: (
      <RequireAuth>
        <BandejaPedidos />
      </RequireAuth>
    ),
  },
  {
    path: '/pedidos/:id/completar',
    element: (
      <RequireAuth>
        <RequireRole role="operator">
          <CompletarPedido />
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
