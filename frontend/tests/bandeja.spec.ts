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
  // Must mention the action to retry (case-insensitive)
  await expect(toast).toContainText(/reintentar/i)
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

// ---------------------------------------------------------------------------
// test_bandeja_shows_cached_data_when_refetch_fails (C-1)
// The list must remain visible even when isError===true, as long as there is
// previously fetched data. Operator with intermittent connection sees last state.
//
// Strategy: first fetch succeeds (populates cache), then the retry button
// triggers a second fetch that fails. TanStack Query keeps stale data in
// `data` while isError becomes true. The component must show the list AND
// the error banner simultaneously.
// ---------------------------------------------------------------------------

test('test_bandeja_shows_cached_data_when_refetch_fails', async ({ page }) => {
  await injectOperatorToken(page)

  let callCount = 0
  await page.route(DELIVERIES_URL, (route) => {
    callCount++
    if (callCount === 1) {
      // First fetch: success — populates TanStack Query cache
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'del-cached',
            supplier_name: 'PROVEEDOR CACHEADO',
            status: 'no_leida',
            item_count: 2,
            created_at: T_OLD,
          },
        ]),
      })
    } else {
      // Subsequent fetches: failure — triggers isError while data is stale
      route.fulfill({ status: 500, body: '' })
    }
  })

  await page.goto('/entradas')

  // Initial success: list is visible, no error banner
  await expect(page.getByText('PROVEEDOR CACHEADO')).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)

  // Navigate away via SPA routing (clicking the back button in the header)
  // so React state + TanStack Query cache stay alive in the same JS context.
  await page.getByRole('button', { name: /volver al home/i }).click()
  await expect(page).toHaveURL('/')

  // Navigate back to /entradas via SPA — triggers second fetch (which fails)
  // while TanStack Query still holds the stale cache from the first call.
  await page.getByRole('button', { name: /ENTRADA/i }).click()
  await expect(page).toHaveURL(/\/entradas/)

  // After the second (failing) fetch: the error banner must appear
  await expect(page.getByRole('alert')).toBeVisible()

  // AND the stale cached list must still be visible (C-1 core assertion)
  await expect(page.getByText('PROVEEDOR CACHEADO')).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_bandeja_shows_offline_banner_when_disconnected (C-2)
// The global OfflineBanner must appear on /entradas when offline.
// ---------------------------------------------------------------------------

test('test_bandeja_shows_offline_banner_when_disconnected', async ({ page, context }) => {
  await injectOperatorToken(page)

  await page.route(DELIVERIES_URL, (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await page.goto('/entradas')
  await context.setOffline(true)

  await expect(page.getByText(/sin conexi/i)).toBeVisible()

  await context.setOffline(false)
})

// ---------------------------------------------------------------------------
// test_en_verificacion_shows_no_leido_badge_and_groups_with_no_leida (C-4)
// en_verificacion must render the same "NO LEIDO" badge and appear in the
// same sort position as no_leida (both before validada).
// ---------------------------------------------------------------------------

test('test_en_verificacion_shows_no_leido_badge_and_groups_with_no_leida', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DELIVERIES_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'del-v',
          supplier_name: 'VALIDADO SA',
          status: 'validada',
          item_count: 1,
          created_at: T_OLD,
        },
        {
          id: 'del-ev',
          supplier_name: 'EN VERIFICACION SRL',
          status: 'en_verificacion',
          item_count: 4,
          created_at: T_OLDER,
        },
        {
          id: 'del-nl',
          supplier_name: 'NO LEIDA SRL',
          status: 'no_leida',
          item_count: 2,
          created_at: T_OLDEST,
        },
      ]),
    })
  })

  await page.goto('/entradas')

  // Both no_leida and en_verificacion must show "NO LEIDO" badge
  const badges = page.getByText('NO LEIDO')
  await expect(badges).toHaveCount(2)

  // en_verificacion must appear before validada (same group as no_leida)
  const allRows = page.getByRole('button', { name: /entrega de/i })
  const count = await allRows.count()
  expect(count).toBe(3)

  // The validada row (VALIDADO SA) must be last
  await expect(allRows.last()).toContainText('VALIDADO SA')

  // Both pending rows (no_leida and en_verificacion) must be in positions 0 and 1
  await expect(allRows.nth(0)).not.toContainText('VALIDADO SA')
  await expect(allRows.nth(1)).not.toContainText('VALIDADO SA')
})

// ---------------------------------------------------------------------------
// test_bandeja_no_leida_order_newest_first_within_group (CS-2)
// Two no_leida deliveries: the newer one must appear first.
// ---------------------------------------------------------------------------

test('test_bandeja_no_leida_order_newest_first_within_group', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DELIVERIES_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'del-older',
          supplier_name: 'PROVEEDOR VIEJO',
          status: 'no_leida',
          item_count: 1,
          created_at: T_OLDER, // 09:00
        },
        {
          id: 'del-newer',
          supplier_name: 'PROVEEDOR NUEVO',
          status: 'no_leida',
          item_count: 1,
          created_at: T_OLD, // 12:00 — newer
        },
      ]),
    })
  })

  await page.goto('/entradas')

  const allRows = page.getByRole('button', { name: /entrega de/i })
  // PROVEEDOR NUEVO (12:00) must be first
  await expect(allRows.first()).toContainText('PROVEEDOR NUEVO')
  await expect(allRows.last()).toContainText('PROVEEDOR VIEJO')
})
