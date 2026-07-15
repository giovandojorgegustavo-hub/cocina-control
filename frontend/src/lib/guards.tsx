import { useEffect, type ReactElement } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from './auth'
import { useAuthWithGetters } from './auth'
import { decodeToken } from './auth'
import type { UserRole } from './auth'

export function RequireAuth({ children }: { children: ReactElement }) {
  const token = useAuth((s) => s.token)
  const clearToken = useAuth((s) => s.clearToken)

  const isValid = token ? decodeToken(token) !== null : false

  useEffect(() => {
    if (token && !isValid) clearToken()
  }, [token, isValid, clearToken])

  if (!isValid) return <Navigate to="/login" replace />
  return children
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
    const redirect = userRole === 'owner' ? '/tablero' : '/'
    return <Navigate to={redirect} replace />
  }

  return <>{children}</>
}

// Redirects away if the authenticated user does not have ANY of the allowed roles.
// Use this for routes accessible by multiple roles (e.g. cocinero + admin).
// Assumes it is always rendered inside a RequireAuth boundary (token exists).
export function RequireAnyRole({
  roles,
  children,
}: {
  roles: UserRole[]
  children: React.ReactNode
}) {
  const { role: userRole } = useAuthWithGetters()

  if (userRole === null) {
    return <Navigate to="/login" replace />
  }

  if (!roles.includes(userRole)) {
    const redirect = userRole === 'owner' ? '/tablero' : '/'
    return <Navigate to={redirect} replace />
  }

  return <>{children}</>
}
