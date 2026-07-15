import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { jwtDecode } from 'jwt-decode'

export type UserRole = 'cocinero' | 'owner' | 'admin'

interface JwtPayload {
  sub: string
  role: UserRole
  exp: number
}

export function decodeToken(token: string): JwtPayload | null {
  try {
    const decoded = jwtDecode<JwtPayload>(token)
    if (decoded.exp * 1000 < Date.now()) return null
    return decoded
  } catch {
    return null
  }
}

interface AuthState {
  token: string | null
  setToken: (token: string) => void
  clearToken: () => void
}

// Computed getters derived from the JWT — never persisted
interface AuthGetters {
  role: UserRole | null
  userId: string | null
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      setToken: (token) => set({ token }),
      clearToken: () => set({ token: null }),
    }),
    {
      name: 'cocina-auth',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
)

// Convenience hook that also exposes derived values from the JWT
export function useAuthWithGetters(): AuthState & AuthGetters {
  const state = useAuth()
  const payload = state.token ? decodeToken(state.token) : null

  return {
    ...state,
    role: payload?.role ?? null,
    userId: payload?.sub ?? null,
  }
}
