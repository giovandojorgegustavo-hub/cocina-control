import axios from 'axios'
import { useAuth } from './auth'

// In dev, VITE_API_URL is empty and requests go to /api/v1/... — Vite proxies them
// to the backend (see vite.config.ts). In production, VITE_API_URL is the absolute
// URL of the backend baked into the build (same origin behind Caddy is also OK).
const BASE_URL = import.meta.env.VITE_API_URL ?? ''

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
      useAuth.getState().clearToken()
    }
    return Promise.reject(error)
  },
)
