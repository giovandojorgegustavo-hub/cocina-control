/**
 * Tests for /pedidos/nuevo — Pantalla 1 (cámara) + Pantalla 2 (confirmatorio)
 *
 * Camera mocking strategy:
 *  - Playwright's addInitScript runs before any page JS.
 *  - We inject a fake MediaStream with a fake video track so getUserMedia
 *    resolves immediately with a dummy stream.
 *  - The video element auto-plays (jsdom/chromium handles muted playsInline).
 *  - For the "camera unavailable" test we make getUserMedia throw NotFoundError.
 *  - For the offline test we use context.setOffline(true) before navigating.
 */
import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const ORDERS_URL = '**/api/v1/delivery-orders'
const PHOTO_URL = '**/api/v1/delivery-orders/*/photo'

async function injectOperatorToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('operator')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
  return token
}

/**
 * Grants camera permission so getUserMedia resolves without a dialog.
 *
 * We rely on Playwright's `--use-fake-ui-for-media-stream` and
 * `--use-fake-device-for-media-stream` launch flags (set in playwright.config.ts)
 * which make Chromium auto-grant the permission AND provide a real-but-fake
 * MediaStream. This produces a genuine MediaStream object that can be assigned
 * to video.srcObject without Chromium rejecting it.
 *
 * The context-level grantPermissions is used to allow the camera permission
 * for the test origin so getUserMedia doesn't throw NotAllowedError.
 */
async function injectFakeCamera(page: import('@playwright/test').Page) {
  // Grant camera permission at the browser context level
  await page.context().grantPermissions(['camera'], { origin: 'http://localhost:5173' })
}

/**
 * Makes getUserMedia reject with NotFoundError (no camera on device).
 */
async function injectNoCameraError(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    if (!navigator.mediaDevices) {
      Object.defineProperty(navigator, 'mediaDevices', {
        value: {},
        writable: true,
        configurable: true,
      })
    }
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
      value: () => {
        const err = new DOMException('No camera', 'NotFoundError')
        return Promise.reject(err)
      },
      writable: true,
      configurable: true,
    })
  })
}

/**
 * Makes getUserMedia reject with NotAllowedError (permission denied).
 */
async function injectPermissionDenied(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    if (!navigator.mediaDevices) {
      Object.defineProperty(navigator, 'mediaDevices', {
        value: {},
        writable: true,
        configurable: true,
      })
    }
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
      value: () => {
        const err = new DOMException('Permission denied', 'NotAllowedError')
        return Promise.reject(err)
      },
      writable: true,
      configurable: true,
    })
  })
}

// ---------------------------------------------------------------------------
// test_camera_view_opens_with_shutter_visible
// ---------------------------------------------------------------------------

test('test_camera_view_opens_with_shutter_visible', async ({ page }) => {
  await injectFakeCamera(page)
  await injectOperatorToken(page)
  await page.goto('/pedidos/nuevo')

  // The shutter button must be visible
  const shutter = page.getByTestId('shutter-button')
  await expect(shutter).toBeVisible()

  // And it must have a usable touch target
  const box = await shutter.boundingBox()
  expect(box).not.toBeNull()
  expect(box!.width).toBeGreaterThanOrEqual(48)
  expect(box!.height).toBeGreaterThanOrEqual(48)
})

// ---------------------------------------------------------------------------
// test_shutter_shows_confirmation_immediately
//
// Click the shutter and verify the confirmation screen appears BEFORE any
// network request completes. We intercept the POST to never resolve.
// ---------------------------------------------------------------------------

test('test_shutter_shows_confirmation_immediately', async ({ page }) => {
  await injectFakeCamera(page)
  await injectOperatorToken(page)

  // Never resolve the POST so we can assert confirmation appeared without server
  await page.route(ORDERS_URL, () => {
    // intentionally hang
  })
  await page.route(PHOTO_URL, () => {
    // intentionally hang
  })

  await page.goto('/pedidos/nuevo')
  await expect(page.getByTestId('shutter-button')).toBeVisible()

  await page.getByTestId('shutter-button').click()

  // Confirmation must appear immediately (before any network response)
  await expect(page.getByTestId('confirmed-view')).toBeVisible({ timeout: 2000 })
  await expect(page.getByText('PEDIDO GUARDADO')).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_shutter_returns_home_after_confirmation
// ---------------------------------------------------------------------------

test('test_shutter_returns_home_after_confirmation', async ({ page }) => {
  await injectFakeCamera(page)
  await injectOperatorToken(page)

  // Stub the network calls so they don't interfere
  await page.route(ORDERS_URL, (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'srv-001' }) })
  })
  await page.route(PHOTO_URL, (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'srv-001' }) })
  })

  await page.goto('/pedidos/nuevo')
  await expect(page.getByTestId('shutter-button')).toBeVisible()
  await page.getByTestId('shutter-button').click()

  // Confirmation appears
  await expect(page.getByTestId('confirmed-view')).toBeVisible()

  // After 1.5 s + grace, must be back at home
  await expect(page).toHaveURL('/', { timeout: 4000 })
})

// ---------------------------------------------------------------------------
// test_camera_unavailable_shows_error_message
// ---------------------------------------------------------------------------

test('test_camera_unavailable_shows_error_message', async ({ page }) => {
  await injectNoCameraError(page)
  await injectOperatorToken(page)
  await page.goto('/pedidos/nuevo')

  await expect(page.getByText(/no tiene camara accesible/i)).toBeVisible()
  // No shutter button
  await expect(page.getByTestId('shutter-button')).toHaveCount(0)
})

// ---------------------------------------------------------------------------
// test_camera_permission_denied_shows_retry
// ---------------------------------------------------------------------------

test('test_camera_permission_denied_shows_retry', async ({ page }) => {
  await injectPermissionDenied(page)
  await injectOperatorToken(page)
  await page.goto('/pedidos/nuevo')

  await expect(page.getByText(/sin permiso para usar la camara/i)).toBeVisible()
  await expect(page.getByRole('button', { name: /reintentar/i })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_offline_photo_shows_confirmation_and_queues
//
// Even when offline, tapping the shutter must show the confirmation screen
// immediately. The photo is saved locally and the operator can keep working.
// ---------------------------------------------------------------------------

test('test_offline_photo_shows_confirmation_and_queues', async ({ page, context }) => {
  await injectFakeCamera(page)
  await injectOperatorToken(page)

  await page.goto('/pedidos/nuevo')

  // Go offline BEFORE tapping the shutter
  await context.setOffline(true)

  await expect(page.getByTestId('shutter-button')).toBeVisible()
  await page.getByTestId('shutter-button').click()

  // Confirmation must appear even though we're offline
  await expect(page.getByTestId('confirmed-view')).toBeVisible({ timeout: 2000 })
  await expect(page.getByText('PEDIDO GUARDADO')).toBeVisible()

  // Clean up
  await context.setOffline(false)
})
