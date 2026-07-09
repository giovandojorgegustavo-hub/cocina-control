import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type UserRole = 'operator' | 'owner'

interface AuthState {
  token: string | null
  role: UserRole | null
  userId: string | null
  setToken: (token: string, role: UserRole, userId: string) => void
  clearToken: () => void
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      role: null,
      userId: null,
      setToken: (token, role, userId) => set({ token, role, userId }),
      clearToken: () => set({ token: null, role: null, userId: null }),
    }),
    {
      name: 'cocina-auth',
    },
  ),
)
