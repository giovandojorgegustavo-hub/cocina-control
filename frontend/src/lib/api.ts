import axios from 'axios'
import { useAuth } from './auth'
import { queryClient } from './queryClient'

// API base URL resolution:
//   1. If VITE_API_URL is set explicitly, it wins (absolute URL or prefix for exotic setups).
//   2. Otherwise, derive from import.meta.env.BASE_URL (injected by Vite from basePath):
//      - dev  (base '/'      ): BASE_URL = '' → requests go to /api/v1/... → Vite proxy.
//      - prod (base '/interno/'): BASE_URL = '/interno' → requests go to /interno/api/v1/...
//        → Caddy proxies to the backend.
//   The trailing slash is stripped because we concatenate '/api/v1' with a leading slash.
const BASE_URL = import.meta.env.VITE_API_URL || import.meta.env.BASE_URL.replace(/\/$/, '')

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use((config) => {
  const token = useAuth.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      queryClient.clear()
      useAuth.getState().clearToken()
    }
    return Promise.reject(error)
  },
)
