import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const PENDING_URL = '**/api/v1/purchase-orders/pending'

async function injectCociToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('cocinero')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

const T_OPEN = '2020-01-10T12:00:00Z'
const T_PARTIAL = '2020-01-09T10:00:00Z'

const MOCK_PENDING = [
  {
    id: 'order-1',
    supplier_name: 'VERDULERIA NUNEZ',
    created_at: T_OPEN,
    derived_status: 'open',
    pending_items_summary: '3 productos · todo pendiente',
  },
  {
    id: 'order-2',
    supplier_name: 'CARNICERIA LOPEZ',
    created_at: T_PARTIAL,
    derived_status: 'partially_received',
    pending_items_summary: 'faltan 40 kg POLLO',
  },
]

// ---------------------------------------------------------------------------
// test_bandeja_partidas_renders_pending_orders
// ---------------------------------------------------------------------------

test('test_bandeja_partidas_renders_pending_orders', async ({ page }) => {
  await injectCociToken(page)

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PENDING),
    })
  })

  await page.goto('/entradas')

  await expect(page.getByText('VERDULERIA NUNEZ')).toBeVisible()
  await expect(page.getByText('CARNICERIA LOPEZ')).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_bandeja_partidas_shows_empty_state
// ---------------------------------------------------------------------------

test('test_bandeja_partidas_shows_empty_state', async ({ page }) => {
  await injectCociToken(page)

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/entradas')

  await expect(page.getByText(/No hay ordenes con entregas pendientes/i)).toBeVisible()
  await expect(page.getByText(/Cuando el dueno cargue una/i)).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_bandeja_partidas_shows_loading_skeletons
// ---------------------------------------------------------------------------

test('test_bandeja_partidas_shows_loading_skeletons', async ({ page }) => {
  await injectCociToken(page)

  // Never resolve — keep loading
  await page.route(PENDING_URL, () => {
    // intentionally do not fulfill
  })

  await page.goto('/entradas')

  const skeletons = page.getByRole('status', { name: 'Cargando orden' })
  await expect(skeletons).toHaveCount(3)
})

// ---------------------------------------------------------------------------
// test_bandeja_partidas_row_click_navigates_to_detail
// ---------------------------------------------------------------------------

test('test_bandeja_partidas_row_click_navigates_to_detail', async ({ page }) => {
  await injectCociToken(page)

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([MOCK_PENDING[0]]),
    })
  })

  // Mock the draft endpoint to avoid an error when navigating
  await page.route('**/api/v1/purchase-orders/order-1/partida-draft', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        order_id: 'order-1',
        supplier_name: 'VERDULERIA NUNEZ',
        partida_number: 1,
        items: [],
      }),
    })
  })

  await page.goto('/entradas')
  await expect(page.getByText('VERDULERIA NUNEZ')).toBeVisible()

  await page.getByRole('button', { name: /Orden de VERDULERIA NUNEZ/i }).click()

  await expect(page).toHaveURL(/\/entradas\/order-1/)
})

// ---------------------------------------------------------------------------
// test_bandeja_partidas_no_monetary_fields — CRITICAL rule-of-gold assertion
// ---------------------------------------------------------------------------

test('test_bandeja_partidas_no_monetary_fields', async ({ page }) => {
  await injectCociToken(page)

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PENDING),
    })
  })

  await page.goto('/entradas')
  await expect(page.getByText('VERDULERIA NUNEZ')).toBeVisible()

  // Must NOT show any monetary amount at any point
  await expect(page.locator('body')).not.toContainText('S/.')
})

// ---------------------------------------------------------------------------
// test_bandeja_partidas_no_auth_redirects_to_login
// ---------------------------------------------------------------------------

test('test_bandeja_partidas_no_auth_redirects_to_login', async ({ page }) => {
  await page.goto('/login')
  await page.evaluate(() => sessionStorage.clear())

  await page.goto('/entradas')

  await expect(page).toHaveURL(/\/login/)
})

// ---------------------------------------------------------------------------
// test_bandeja_partidas_shows_error_on_fetch_failure
// ---------------------------------------------------------------------------

test('test_bandeja_partidas_shows_error_on_fetch_failure', async ({ page }) => {
  await injectCociToken(page)

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal server error' }),
    })
  })

  await page.goto('/entradas')

  const banner = page.getByRole('alert')
  await expect(banner).toBeVisible()
  await expect(banner).toContainText(/reintentar/i)
})

// ---------------------------------------------------------------------------
// test_401_response_clears_token_and_redirects_to_login (Fix 1 / SEG-ALTO)
// When the axios interceptor receives a 401, it must call queryClient.clear()
// and clearToken(). We verify the observable side-effects: auth token is gone
// from sessionStorage and the guard redirects to /login.
// ---------------------------------------------------------------------------

test('test_401_response_clears_token_and_redirects_to_login', async ({ page }) => {
  await injectCociToken(page)

  // Route /entradas to trigger the interceptor with a 401
  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Unauthorized' }),
    })
  })

  await page.goto('/entradas')

  // The 401 interceptor clears the token → RequireAuth redirects to /login
  await expect(page).toHaveURL(/\/login/, { timeout: 5000 })

  // Verify sessionStorage token is gone
  const stored = await page.evaluate(() => sessionStorage.getItem('cocina-auth'))
  const parsed = JSON.parse(stored ?? '{}') as { state?: { token?: string | null } }
  expect(parsed?.state?.token ?? null).toBeNull()
})
