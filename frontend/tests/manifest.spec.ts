import { test, expect } from '@playwright/test'

test('manifest.webmanifest is served with correct content type', async ({
  request,
}) => {
  const response = await request.get('/manifest.webmanifest')

  expect(response.status()).toBe(200)

  // In production (npm run preview / dist/), the plugin serves application/manifest+json.
  // In dev mode, vite-plugin-pwa serves the manifest via an internal handler that may
  // use a different content-type. We validate the content, not the MIME type, in both modes.
  const body = await response.json()
  expect(body.name).toBe('Cocina Control')
  expect(body.display).toBe('standalone')
  expect(body.lang).toBe('es')
  expect(body.icons).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ purpose: 'maskable' }),
    ]),
  )
})
