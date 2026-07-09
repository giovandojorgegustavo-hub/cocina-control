import { test, expect } from '@playwright/test'

test('manifest.webmanifest is served with correct content type', async ({
  request,
}) => {
  const response = await request.get('/manifest.webmanifest')

  expect(response.status()).toBe(200)

  const contentType = response.headers()['content-type'] ?? ''
  const isValidContentType =
    contentType.includes('application/manifest+json') ||
    contentType.includes('application/json')
  expect(isValidContentType).toBe(true)

  const body = await response.json()
  expect(body.name).toBe('Cocina Control')
  expect(body.display).toBe('standalone')
})
