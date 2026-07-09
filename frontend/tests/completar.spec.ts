/**
 * Tests for /pedidos/:id/completar — Pantalla 4 (completar) + Pantalla 5 (terminado)
 */
import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const PRODUCTS_URL = '**/api/v1/products'
const ORDER_URL = '**/api/v1/delivery-orders/*'
const COMPLETE_URL = '**/api/v1/delivery-orders/*/complete'
const PHOTO_URL = '**/api/v1/delivery-orders/*/photo'

const ORDER_ID = 'order-completar-1'
const PHOTO_AT = '2020-01-01T23:42:00Z'

const MOCK_ORDER = {
  id: ORDER_ID,
  status: 'pending',
  photo_at: PHOTO_AT,
  photo_by: 'user-1',
  completed_at: null,
  completed_by: null,
  items: [],
}

const MOCK_PRODUCTS = [
  { id: 'prod-1', name: 'PALTA', unit: 'kg', low_stock_threshold: null },
  { id: 'prod-2', name: 'POLLO', unit: 'kg', low_stock_threshold: null },
  { id: 'prod-3', name: 'TOMATE', unit: 'kg', low_stock_threshold: null },
]

async function injectOperatorToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('operator')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
  return token
}

async function setupBasicMocks(page: import('@playwright/test').Page) {
  await page.route(ORDER_URL, (route) => {
    // Only match the detail endpoint (no /complete, /photo suffix)
    const url = route.request().url()
    if (url.endsWith(ORDER_ID)) {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_ORDER),
      })
    } else {
      route.continue()
    }
  })
  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })
  await page.route(PHOTO_URL, (route) => {
    route.fulfill({ status: 404, body: '' })
  })
}

// ---------------------------------------------------------------------------
// test_complete_requires_at_least_one_product
// ---------------------------------------------------------------------------

test('test_complete_requires_at_least_one_product', async ({ page }) => {
  await injectOperatorToken(page)
  await setupBasicMocks(page)

  await page.goto(`/pedidos/${ORDER_ID}/completar`)

  // Product cards must be visible
  await expect(page.getByText('PALTA')).toBeVisible()

  // "terminar pedido" button must be disabled (zero products selected)
  const btn = page.getByTestId('terminar-pedido')
  await expect(btn).toBeVisible()
  // aria-disabled because we use CSS opacity instead of HTML disabled for styling
  await expect(btn).toHaveAttribute('aria-disabled', 'true')
})

// ---------------------------------------------------------------------------
// test_tap_product_selects_x1
// ---------------------------------------------------------------------------

test('test_tap_product_selects_x1', async ({ page }) => {
  await injectOperatorToken(page)
  await setupBasicMocks(page)

  await page.goto(`/pedidos/${ORDER_ID}/completar`)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Tap PALTA
  await page.getByRole('button', { name: /PALTA/i }).click()

  // The card should now show ×1 badge
  await expect(page.getByText('×1')).toBeVisible()

  // aria-pressed must be true
  const card = page.getByRole('button', { name: /PALTA.*cantidad 1/i })
  await expect(card).toHaveAttribute('aria-pressed', 'true')
})

// ---------------------------------------------------------------------------
// test_tap_product_twice_sums_to_x2
// ---------------------------------------------------------------------------

test('test_tap_product_twice_sums_to_x2', async ({ page }) => {
  await injectOperatorToken(page)
  await setupBasicMocks(page)

  await page.goto(`/pedidos/${ORDER_ID}/completar`)
  await expect(page.getByText('POLLO')).toBeVisible()

  // Tap POLLO twice
  await page.getByRole('button', { name: /POLLO/i }).click()
  await page.getByRole('button', { name: /POLLO.*cantidad 1/i }).click()

  // Should show ×2
  await expect(page.getByText('×2')).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_tap_selected_badge_decrements
// ---------------------------------------------------------------------------

test('test_tap_selected_badge_decrements', async ({ page }) => {
  await injectOperatorToken(page)
  await setupBasicMocks(page)

  await page.goto(`/pedidos/${ORDER_ID}/completar`)
  await expect(page.getByText('TOMATE')).toBeVisible()

  // Select TOMATE twice → ×2
  await page.getByRole('button', { name: /TOMATE/i }).click()
  await page.getByRole('button', { name: /TOMATE.*cantidad 1/i }).click()
  await expect(page.getByText('×2')).toBeVisible()

  // Click the quantity badge to decrement → ×1
  await page.getByRole('button', { name: /quitar una unidad de TOMATE/i }).click()
  await expect(page.getByText('×1')).toBeVisible()
  await expect(page.getByText('×2')).toHaveCount(0)
})

// ---------------------------------------------------------------------------
// test_dejar_solo_foto_returns_to_bandeja_without_calling_backend
// ---------------------------------------------------------------------------

test('test_dejar_solo_foto_returns_to_bandeja_without_calling_backend', async ({ page }) => {
  await injectOperatorToken(page)
  await setupBasicMocks(page)

  let completeCalled = false
  await page.route(COMPLETE_URL, () => {
    completeCalled = true
    // intentionally hang
  })

  await page.goto(`/pedidos/${ORDER_ID}/completar`)
  await expect(page.getByTestId('dejar-solo-foto')).toBeVisible()

  await page.getByTestId('dejar-solo-foto').click()

  await expect(page).toHaveURL(/\/pedidos$/)
  expect(completeCalled).toBe(false)
})

// ---------------------------------------------------------------------------
// test_terminar_pedido_calls_complete_and_returns_bandeja
// ---------------------------------------------------------------------------

test('test_terminar_pedido_calls_complete_and_returns_bandeja', async ({ page }) => {
  await injectOperatorToken(page)
  await setupBasicMocks(page)

  let completeBody: unknown = null
  await page.route(COMPLETE_URL, (route) => {
    const req = route.request()
    completeBody = JSON.parse(req.postData() ?? '{}')
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: ORDER_ID, status: 'completed', items: [] }),
    })
  })

  // Stub the orders list used when navigating back to bandeja
  // Use an exact URL pattern so it only matches GET /delivery-orders (no suffix)
  await page.route('**/api/v1/delivery-orders?**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await page.goto(`/pedidos/${ORDER_ID}/completar`)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Select PALTA
  await page.getByRole('button', { name: /PALTA/i }).click()
  await expect(page.getByText('×1')).toBeVisible()

  // Terminate
  await page.getByTestId('terminar-pedido').click()

  // Confirmation screen (Pantalla 5)
  await expect(page.getByTestId('terminado-view')).toBeVisible({ timeout: 3000 })
  await expect(page.getByText('PEDIDO TERMINADO')).toBeVisible()

  // Back to bandeja after 1.5 s
  await expect(page).toHaveURL(/\/pedidos$/, { timeout: 4000 })

  // Verify the payload sent to the backend
  expect(completeBody).toMatchObject({
    items: expect.arrayContaining([
      expect.objectContaining({ product_id: 'prod-1', quantity: 1 }),
    ]),
  })
})

// ---------------------------------------------------------------------------
// test_photo_visible_while_completing
//
// The AuthImg for the order photo must be rendered in the completar layout.
// We stub the photo endpoint with a real JPEG blob and verify the img gets
// a blob: URL (not the placeholder).
// ---------------------------------------------------------------------------

test('test_photo_visible_while_completing', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(ORDER_URL, (route) => {
    const url = route.request().url()
    if (url.endsWith(ORDER_ID)) {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_ORDER),
      })
    } else {
      route.continue()
    }
  })
  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  // Serve a minimal 1×1 JPEG for the photo
  const miniJpeg = Buffer.from(
    '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAARC' +
    'AABAAEDAQIREQAXEQABAQD/xABQAAEBAAAAAAAAAAAAAAAAAAAGBxABAAIBBAMAAAAAAAAAAAAAAAABAgMFEyExEQEAAwEBAAAAAAAAAAAAAAAAAAECAxH/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwDFp9QAFgAAAAAAAAH/2Q==',
    'base64',
  )
  await page.route(PHOTO_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'image/jpeg',
      body: miniJpeg,
    })
  })

  await page.goto(`/pedidos/${ORDER_ID}/completar`)
  await expect(page.getByText('PALTA')).toBeVisible()

  // The AuthImg should load the blob and set src to blob:
  await page.waitForFunction(
    () => {
      const img = document.querySelector('[data-testid="order-photo-completar"]') as HTMLImageElement | null
      return img !== null && img.src.startsWith('blob:')
    },
    { timeout: 5000 },
  )
})
