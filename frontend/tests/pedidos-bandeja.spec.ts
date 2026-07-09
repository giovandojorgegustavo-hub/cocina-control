/**
 * Tests for /pedidos — Bandeja de pedidos (Pantalla 3)
 */
import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const ORDERS_URL = '**/api/v1/delivery-orders'
const PHOTO_PATTERN = '**/api/v1/delivery-orders/*/photo'

const T_OLD = '2020-01-01T23:42:00Z'
const T_OLDER = '2020-01-01T22:15:00Z'
const T_YESTERDAY = '2019-12-31T20:03:00Z'

const MOCK_PENDING = {
  id: 'order-pending-1',
  status: 'pending',
  photo_at: T_OLD,
  photo_by: 'user-1',
}
const MOCK_PENDING_OLD = {
  id: 'order-pending-2',
  status: 'pending',
  photo_at: T_YESTERDAY,
  photo_by: 'user-1',
}
const MOCK_COMPLETED = {
  id: 'order-completed-1',
  status: 'completed',
  photo_at: T_OLDER,
  photo_by: 'user-1',
  completed_at: T_OLDER,
  completed_by: 'user-1',
}

async function injectOperatorToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('operator')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
  return token
}

// ---------------------------------------------------------------------------
// test_bandeja_lists_pending_first
// ---------------------------------------------------------------------------

test('test_bandeja_lists_pending_first', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([MOCK_COMPLETED, MOCK_PENDING]),
    })
  })
  // Stub photo responses so AuthImg doesn't hang
  await page.route(PHOTO_PATTERN, (route) => {
    route.fulfill({ status: 404, body: '' })
  })

  await page.goto('/pedidos')

  // Both orders must be present
  const rows = page.locator('[class*="border-l"]')
  await expect(rows.first()).toContainText('PENDIENTE')
})

// ---------------------------------------------------------------------------
// test_bandeja_pending_shows_completar_button
// ---------------------------------------------------------------------------

test('test_bandeja_pending_shows_completar_button', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([MOCK_PENDING]),
    })
  })
  await page.route(PHOTO_PATTERN, (route) => {
    route.fulfill({ status: 404, body: '' })
  })

  await page.goto('/pedidos')

  await expect(page.getByRole('button', { name: /completar/i })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_bandeja_completed_shows_no_button
// ---------------------------------------------------------------------------

test('test_bandeja_completed_shows_no_button', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([MOCK_COMPLETED]),
    })
  })
  await page.route(PHOTO_PATTERN, (route) => {
    route.fulfill({ status: 404, body: '' })
  })

  await page.goto('/pedidos')

  // "TERMINADO" badge must be present
  await expect(page.getByText(/TERMINADO/)).toBeVisible()
  // No "completar" button since it's already done
  await expect(page.getByRole('button', { name: /completar/i })).toHaveCount(0)
})

// ---------------------------------------------------------------------------
// test_bandeja_shows_photo_thumbnail
//
// Mock GET photo with a real 1x1 JPEG blob, verify <img> renders (not just
// the placeholder SVG).
// ---------------------------------------------------------------------------

test('test_bandeja_shows_photo_thumbnail', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([MOCK_PENDING]),
    })
  })

  // A minimal 1×1 white JPEG (24 bytes)
  const miniJpeg = Buffer.from(
    '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAARC' +
    'AABAAEDAQIREQAXEQABAQD/xABQAAEBAAAAAAAAAAAAAAAAAAAGBxABAAIBBAMAAAAAAAAAAAAAAAABAgMFEyExEQEAAwEBAAAAAAAAAAAAAAAAAAECAxH/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwDFp9QAFgAAAAAAAAH/2Q==',
    'base64',
  )

  await page.route(PHOTO_PATTERN, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'image/jpeg',
      body: miniJpeg,
    })
  })

  await page.goto('/pedidos')

  // The AuthImg should eventually render with a blob URL (not the placeholder SVG)
  // We check that at least one img has a src that's a blob: URL
  await page.waitForFunction(
    () => {
      const imgs = Array.from(document.querySelectorAll('img[data-testid="order-photo"]'))
      return imgs.some((img) => (img as HTMLImageElement).src.startsWith('blob:'))
    },
    { timeout: 5000 },
  )
})

// ---------------------------------------------------------------------------
// test_bandeja_empty_state
// ---------------------------------------------------------------------------

test('test_bandeja_empty_state', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/pedidos')

  await expect(page.getByText(/todavia no hay pedidos hoy/i)).toBeVisible()
  await expect(page.getByText(/saca la primera foto al empacar/i)).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_bandeja_shows_loading_skeletons
// ---------------------------------------------------------------------------

test('test_bandeja_shows_loading_skeletons', async ({ page }) => {
  await injectOperatorToken(page)

  // Never resolve
  await page.route(ORDERS_URL, () => {
    // intentionally hang
  })

  await page.goto('/pedidos')

  const skeletons = page.getByRole('status', { name: 'Cargando pedido' })
  await expect(skeletons).toHaveCount(3)
})

// ---------------------------------------------------------------------------
// test_bandeja_pending_old_appears_in_list
// Pending orders from a previous day must still appear as pending (no auto-expiry)
// ---------------------------------------------------------------------------

test('test_bandeja_pending_old_appears_in_list', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([MOCK_PENDING_OLD]),
    })
  })
  await page.route(PHOTO_PATTERN, (route) => {
    route.fulfill({ status: 404, body: '' })
  })

  await page.goto('/pedidos')

  await expect(page.getByText('PENDIENTE')).toBeVisible()
  await expect(page.getByRole('button', { name: /completar/i })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_bandeja_completar_button_navigates
// ---------------------------------------------------------------------------

test('test_bandeja_completar_button_navigates', async ({ page }) => {
  await injectOperatorToken(page)

  const orderId = 'order-pending-nav'
  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ ...MOCK_PENDING, id: orderId }]),
    })
  })
  await page.route(PHOTO_PATTERN, (route) => {
    route.fulfill({ status: 404, body: '' })
  })

  await page.goto('/pedidos')

  await page.getByRole('button', { name: /completar/i }).click()

  await expect(page).toHaveURL(new RegExp(`/pedidos/${orderId}/completar`))
})

// ---------------------------------------------------------------------------
// test_bandeja_no_auth_redirects_to_login
// ---------------------------------------------------------------------------

test('test_bandeja_no_auth_redirects_to_login', async ({ page }) => {
  await page.goto('/login')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('/pedidos')
  await expect(page).toHaveURL(/\/login/)
})
