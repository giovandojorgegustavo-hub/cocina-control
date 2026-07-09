import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const DELIVERIES_URL = '**/api/v1/deliveries'

async function injectOperatorToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('operator')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
  return token
}

// Stable timestamps for ordering tests (UTC so formatRelativeDate has predictable output)
// Use a far past date so they always render as "DD/MM HH:mm", regardless of when the test runs
const T_OLD = '2020-01-01T12:00:00Z'
const T_OLDER = '2020-01-01T09:00:00Z'
const T_OLDEST = '2019-12-31T16:00:00Z'

const MOCK_DELIVERIES = [
  {
    id: 'del-1',
    supplier_name: 'CARNICERIA LOPEZ',
    status: 'validada',
    item_count: 3,
    created_at: T_OLD,
  },
  {
    id: 'del-2',
    supplier_name: 'VERDULERIA NUNEZ',
    status: 'no_leida',
    item_count: 8,
    created_at: T_OLDER,
  },
  {
    id: 'del-3',
    supplier_name: 'DISTRIBUIDORA SUR',
    status: 'validada',
    item_count: 5,
    created_at: T_OLDEST,
  },
]

// ---------------------------------------------------------------------------
// test_bandeja_renders_deliveries_in_correct_order
// ---------------------------------------------------------------------------

test('test_bandeja_renders_deliveries_in_correct_order', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DELIVERIES_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_DELIVERIES),
    })
  })

  await page.goto('/entradas')

  // All three suppliers should be visible
  await expect(page.getByText('VERDULERIA NUNEZ')).toBeVisible()
  await expect(page.getByText('CARNICERIA LOPEZ')).toBeVisible()
  await expect(page.getByText('DISTRIBUIDORA SUR')).toBeVisible()

  // The no_leida row must appear before the validada rows
  const allRows = page.getByRole('button', { name: /entrega de/i })
  const count = await allRows.count()
  expect(count).toBe(3)

  // First row must be VERDULERIA NUNEZ (no_leida)
  await expect(allRows.first()).toContainText('VERDULERIA NUNEZ')
})

// ---------------------------------------------------------------------------
// test_bandeja_no_leida_has_dark_badge
// ---------------------------------------------------------------------------

test('test_bandeja_no_leida_has_dark_badge', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DELIVERIES_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_DELIVERIES),
    })
  })

  await page.goto('/entradas')

  // The "NO LEIDO" badge must be visible somewhere on the page
  const badge = page.getByText('NO LEIDO')
  await expect(badge).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_bandeja_shows_empty_state
// ---------------------------------------------------------------------------

test('test_bandeja_shows_empty_state', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DELIVERIES_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/entradas')

  await expect(page.getByText('No hay entregas anunciadas.')).toBeVisible()
  await expect(page.getByText('Cuando el dueño cargue una, aparece acá.')).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_bandeja_shows_loading_skeletons
// ---------------------------------------------------------------------------

test('test_bandeja_shows_loading_skeletons', async ({ page }) => {
  await injectOperatorToken(page)

  // Never resolve — keep the request in flight so skeletons stay visible
  await page.route(DELIVERIES_URL, () => {
    // intentionally do not fulfill to keep loading state
  })

  await page.goto('/entradas')

  // At least 3 skeleton rows must be visible before the response arrives
  const skeletons = page.getByRole('status', { name: 'Cargando entrega' })
  await expect(skeletons).toHaveCount(3)
})

// ---------------------------------------------------------------------------
// test_bandeja_shows_error_toast_on_fetch_failure
// ---------------------------------------------------------------------------

test('test_bandeja_shows_error_toast_on_fetch_failure', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DELIVERIES_URL, (route) => {
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal server error' }),
    })
  })

  await page.goto('/entradas')

  // The error toast must appear (role="alert" from ErrorBanner)
  const toast = page.getByRole('alert')
  await expect(toast).toBeVisible()
  // Must mention the action to retry
  await expect(toast).toContainText('reintentar')
})

// ---------------------------------------------------------------------------
// test_bandeja_row_click_navigates_to_detail
// ---------------------------------------------------------------------------

test('test_bandeja_row_click_navigates_to_detail', async ({ page }) => {
  await injectOperatorToken(page)

  const targetId = 'del-2'

  await page.route(DELIVERIES_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: targetId,
          supplier_name: 'VERDULERIA NUNEZ',
          status: 'no_leida',
          item_count: 8,
          created_at: T_OLD,
        },
      ]),
    })
  })

  await page.goto('/entradas')

  // Click the delivery row
  await page.getByRole('button', { name: /VERDULERIA NUNEZ/i }).click()

  // Should navigate to /entradas/{id}
  await expect(page).toHaveURL(new RegExp(`/entradas/${targetId}`))
})

// ---------------------------------------------------------------------------
// test_bandeja_no_auth_redirects_to_login
// ---------------------------------------------------------------------------

test('test_bandeja_no_auth_redirects_to_login', async ({ page }) => {
  // Navigate to origin to clear sessionStorage, then go directly to /entradas
  await page.goto('/login')
  await page.evaluate(() => sessionStorage.clear())

  await page.goto('/entradas')

  await expect(page).toHaveURL(/\/login/)
})
