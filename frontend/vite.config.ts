import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// Base path for the app. Default is '/' (dev and root builds).
// In production, build with: VITE_BASE_PATH=/interno/ npm run build
//
// The value MUST start with '/'; the trailing '/' is added defensively.
// A missing leading slash is a common typo and Vite only warns — we reject
// it up front so misconfiguration surfaces as an error at build time.
//
// Note: in dev, the /api proxy is registered as literal '/api'. Setting
// VITE_BASE_PATH to a non-root value in dev breaks API calls (they resolve
// to e.g. /interno/api/... which the proxy doesn't match). Only set the
// var in production builds; keep dev on '/'.
const rawBase = process.env.VITE_BASE_PATH ?? '/'
if (rawBase !== '' && !rawBase.startsWith('/')) {
  throw new Error(
    `VITE_BASE_PATH must start with '/'. Got: ${JSON.stringify(rawBase)}. ` +
      `Example: /interno/`,
  )
}
const basePath = rawBase === '' || rawBase.endsWith('/') ? rawBase || '/' : `${rawBase}/`

export default defineConfig({
  // Dev + preview proxy: same-origin requests to /api are forwarded to the FastAPI
  // backend. This mirrors the production topology where Caddy proxies /api to the
  // backend on the same origin, so the frontend never needs CORS. Backend URL is
  // configurable via VITE_DEV_PROXY_TARGET (default: http://127.0.0.1:8000).
  //
  // The same proxy config is applied to `preview` so that:
  //   - Playwright (which runs against `vite preview`) does not serve the SPA
  //     index.html as a fallback for /api requests. Tests that don't mock a
  //     specific endpoint get a real network error, matching the old behavior
  //     (before /api was same-origin).
  //   - Manual smoke tests against `vite preview` still hit a real backend if
  //     it is running.
  base: basePath,
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icons/icon-192.png', 'icons/icon-512.png'],
      manifest: {
        name: 'Cocina Control',
        short_name: 'Cocina',
        description: 'Control de inventario para dark kitchen',
        lang: 'es',
        theme_color: '#111827',
        background_color: '#ffffff',
        display: 'standalone',
        orientation: 'any',
        start_url: basePath,
        scope: basePath,
        icons: [
          {
            src: 'icons/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: 'icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
          },
          {
            src: 'icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        // IMPORTANTE: las llamadas a /api/** NO se cachean por diseño.
        // Los datos sensibles del dominio (inventario, auditoría) deben venir siempre del servidor.
        // No agregar runtimeCaching para /api sin revisión de seguridad.
      },
    }),
  ],
})
