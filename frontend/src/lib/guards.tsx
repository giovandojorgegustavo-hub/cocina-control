import { Navigate } from 'react-router-dom'
import { useAuth } from './auth'
import { useAuthWithGetters } from './auth'
import type { UserRole } from './auth'

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuth((s) => s.token)
  if (!token) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

// Redirects away if the authenticated user does not have the required role.
// Assumes it is always rendered inside a RequireAuth boundary (token exists).
export function RequireRole({
  role,
  children,
}: {
  role: UserRole
  children: React.ReactNode
}) {
  const { role: userRole } = useAuthWithGetters()

  if (userRole === null) {
    // Token present but not yet decoded (shouldn't normally happen)
    return <Navigate to="/login" replace />
  }

  if (userRole !== role) {
    // Wrong role — redirect to the correct home for this user
    const redirect = userRole === 'operator' ? '/' : '/tablero'
    return <Navigate to={redirect} replace />
  }

  return <>{children}</>
}
