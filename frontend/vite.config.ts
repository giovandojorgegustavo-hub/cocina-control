import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
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
        start_url: '/',
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
