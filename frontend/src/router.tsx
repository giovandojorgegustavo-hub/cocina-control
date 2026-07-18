import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Login } from './pages/Login'
import { Home } from './pages/Home'
import { BandejaPartidas } from './pages/BandejaPartidas'
import { VerificacionPartida } from './pages/VerificacionPartida'
import { OrdenesLista } from './pages/OrdenesLista'
import { OrdenDetalle } from './pages/OrdenDetalle'
import { OrdenNueva } from './pages/OrdenNueva'
import { NuevoPedido } from './pages/NuevoPedido'
import { BandejaPedidos } from './pages/BandejaPedidos'
import { CompletarPedido } from './pages/CompletarPedido'
import { InventarioLista } from './pages/InventarioLista'
import { ContarProducto } from './pages/ContarProducto'
import { InventarioCompletado } from './pages/InventarioCompletado'
import { Tablero } from './pages/Tablero'
import { Trazabilidad } from './pages/Trazabilidad'
import { RequireAuth, RequireRole, RequireAnyRole } from './lib/guards'

// React Router requires basename WITHOUT trailing slash.
// import.meta.env.BASE_URL is injected by Vite and equals basePath from vite.config.ts.
// When BASE_URL is '/', basename becomes '' — identical to the current behaviour.
const basename = import.meta.env.BASE_URL.replace(/\/$/, '')

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/',
    element: (
      <RequireAuth>
        <RequireAnyRole roles={['cocinero', 'admin']}>
          <Home />
        </RequireAnyRole>
      </RequireAuth>
    ),
  },
  {
    path: '/entradas',
    element: (
      <RequireAuth>
        <RequireAnyRole roles={['cocinero', 'admin', 'owner']}>
          <BandejaPartidas />
        </RequireAnyRole>
      </RequireAuth>
    ),
  },
  {
    path: '/entradas/:orderId',
    element: (
      <RequireAuth>
        <RequireAnyRole roles={['cocinero', 'admin', 'owner']}>
          <VerificacionPartida />
        </RequireAnyRole>
      </RequireAuth>
    ),
  },
  {
    path: '/ordenes',
    element: (
      <RequireAuth>
        <RequireAnyRole roles={['owner', 'admin']}>
          <OrdenesLista />
        </RequireAnyRole>
      </RequireAuth>
    ),
  },
  {
    path: '/ordenes/:id',
    element: (
      <RequireAuth>
        <RequireAnyRole roles={['owner', 'admin']}>
          <OrdenDetalle />
        </RequireAnyRole>
      </RequireAuth>
    ),
  },
  {
    path: '/ordenes/nueva',
    element: (
      <RequireAuth>
        <RequireAnyRole roles={['owner', 'admin']}>
          <OrdenNueva />
        </RequireAnyRole>
      </RequireAuth>
    ),
  },
  {
    path: '/inventario',
    element: (
      <RequireAuth>
        <RequireAnyRole roles={['cocinero', 'admin', 'owner']}>
          <InventarioLista />
        </RequireAnyRole>
      </RequireAuth>
    ),
  },
  {
    path: '/inventario/contar/:productId',
    element: (
      <RequireAuth>
        <RequireAnyRole roles={['cocinero', 'admin', 'owner']}>
          <ContarProducto />
        </RequireAnyRole>
      </RequireAuth>
    ),
  },
  {
    path: '/inventario/completado',
    element: (
      <RequireAuth>
        <RequireAnyRole roles={['cocinero', 'admin', 'owner']}>
          <InventarioCompletado />
        </RequireAnyRole>
      </RequireAuth>
    ),
  },
  {
    path: '/pedidos/nuevo',
    element: (
      <RequireAuth>
        <RequireAnyRole roles={['cocinero', 'admin', 'owner']}>
          <NuevoPedido />
        </RequireAnyRole>
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
        <RequireAnyRole roles={['cocinero', 'admin', 'owner']}>
          <CompletarPedido />
        </RequireAnyRole>
      </RequireAuth>
    ),
  },
  {
    path: '/tablero',
    element: (
      <RequireAuth>
        <RequireRole role="owner">
          <Tablero />
        </RequireRole>
      </RequireAuth>
    ),
  },
  {
    path: '/tablero/producto/:productId',
    element: (
      <RequireAuth>
        <RequireRole role="owner">
          <Trazabilidad />
        </RequireRole>
      </RequireAuth>
    ),
  },
  {
    path: '*',
    element: <Navigate to="/login" replace />,
  },
], { basename })
