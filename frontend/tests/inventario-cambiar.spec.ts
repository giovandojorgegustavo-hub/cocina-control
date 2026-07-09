/**
 * Tests for correction flow — /inventario/contar/:productId?item_id=X
 */
import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PRODUCTS_URL = '**/api/v1/products'
const COUNT_URL = '**/api/v1/inventory-counts/*'
const ITEMS_URL = '**/api/v1/inventory-counts/*/items'
const CORRECT_URL = '**/api/v1/inventory-counts/*/items/*/correct'

const COUNT_ID = 'count-cambiar'
const USER_ID = 'test-user-id'
const LS_KEY = `cocina-inventory-count-${USER_ID}`
const ITEM_ID = 'item-palta-original'

const MOCK_PRODUCTS = [
  { id: 'prod-palta', name: 'PALTA', unit: 'un', low_stock_threshold: null },
  { id: 'prod-cebolla', name: 'CEBOLLA', unit: 'kg', low_stock_threshold: null },
]

function makeCountWithPalta(qty: number, status = 'in_progress') {
  return {
    id: COUNT_ID,
    status,
    started_at: '2026-07-09T12:00:00Z',
    items: [{ id: ITEM_ID, product_id: 'prod-palta', quantity: qty }],
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function injectOperatorToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('operator', 3600, USER_ID)
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

async function seedCount(page: import('@playwright/test').Page) {
  await page.evaluate(
    ([key, val]) => localStorage.setItem(key, val),
    [LS_KEY, COUNT_ID],
  )
}

// ---------------------------------------------------------------------------
// test_cambiar_shows_previous_value_in_banner
// The correction banner must show the product name and the previous quantity.
// ---------------------------------------------------------------------------

test('test_cambiar_shows_previous_value_in_banner', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.match(/\/items\/[^/]+\/correct$/) && route.request().method() === 'POST') return route.continue()
    if (url.match(/\/items$/) && route.request().method() === 'POST') return route.continue()
    if (url.endsWith('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCountWithPalta(4)),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  await page.goto(`/inventario/contar/prod-palta?item_id=${ITEM_ID}`)

  const banner = page.getByTestId('correction-banner')
  await expect(banner).toBeVisible()

  // Banner must mention the product name and previous value
  await expect(banner).toContainText('CAMBIANDO')
  await expect(banner).toContainText('PALTA')
  await expect(banner).toContainText('4')
  await expect(banner).toContainText('un')
})

// ---------------------------------------------------------------------------
// test_cambiar_input_empty_at_start_banner_shows_previous (QA H-01)
// In correction mode the input must start EMPTY. The banner carries the reference value.
// ---------------------------------------------------------------------------

test('test_cambiar_input_empty_at_start_banner_shows_previous', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.match(/\/items\/[^/]+\/correct$/) && route.request().method() === 'POST') return route.continue()
    if (url.match(/\/items$/) && route.request().method() === 'POST') return route.continue()
    if (url.endsWith('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCountWithPalta(7)),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  await page.goto(`/inventario/contar/prod-palta?item_id=${ITEM_ID}`)

  // Input must be EMPTY — the operator types the new value
  const input = page.getByTestId('qty-input')
  await expect(input).toHaveValue('')

  // Banner still shows the previous value as reference
  const banner = page.getByTestId('correction-banner')
  await expect(banner).toContainText('7')
  await expect(banner).toContainText('un')
})

// ---------------------------------------------------------------------------
// test_cambiar_calls_correct_endpoint_not_items
// When correcting, must call POST /items/{itemId}/correct, NOT POST /items.
// ---------------------------------------------------------------------------

test('test_cambiar_calls_correct_endpoint_not_items', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  let correctCalled = false
  let itemsPostCalled = false

  await page.route(CORRECT_URL, (route) => {
    correctCalled = true
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ new_item_id: 'item-corrected', corrects_id: ITEM_ID }),
    })
  })

  await page.route(ITEMS_URL, (route) => {
    if (route.request().method() === 'POST') {
      itemsPostCalled = true
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
    } else {
      route.continue()
    }
  })

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.match(/\/items\/[^/]+\/correct$/) && route.request().method() === 'POST') return route.continue()
    if (url.match(/\/items$/) && route.request().method() === 'POST') return route.continue()
    if (url.endsWith('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCountWithPalta(4)),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  await page.goto(`/inventario/contar/prod-palta?item_id=${ITEM_ID}`)

  // Change value and submit
  await page.getByTestId('qty-input').fill('6')
  await page.getByTestId('btn-ok-volver').click()

  await page.waitForTimeout(300)

  expect(correctCalled).toBe(true)
  expect(itemsPostCalled).toBe(false)
})

// ---------------------------------------------------------------------------
// test_correct_403_shows_deadline_expired_message (QA H-04)
// A 403 response on correct must show a specific "plazo vencido" message.
// ---------------------------------------------------------------------------

test('test_correct_403_shows_deadline_expired_message', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  await page.route(CORRECT_URL, (route) => {
    route.fulfill({ status: 403, body: '' })
  })

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.match(/\/items\/[^/]+\/correct$/) && route.request().method() === 'POST') return route.continue()
    if (url.endsWith('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCountWithPalta(4)),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  await page.goto(`/inventario/contar/prod-palta?item_id=${ITEM_ID}`)

  await page.getByTestId('qty-input').fill('5')
  await page.getByTestId('btn-ok-volver').click()

  const alert = page.getByRole('alert')
  await expect(alert).toBeVisible()
  await expect(alert).toContainText('plazo')
  await expect(alert).toContainText('dueño')
})

// ---------------------------------------------------------------------------
// test_contar_without_countId_redirects_to_inventario (QA H-05)
// Navigating to contar without a countId in localStorage must redirect to /inventario.
// ---------------------------------------------------------------------------

test('test_contar_without_countId_redirects_to_inventario', async ({ page }) => {
  const token = makeTestJwt('operator', 3600, USER_ID)
  const lsKey = LS_KEY
  await page.goto('/login')
  await page.evaluate(
    ([t, key]) => {
      sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
      // Ensure no countId in localStorage
      localStorage.removeItem(key)
    },
    [token, lsKey],
  )

  const COUNTS_URL = '**/api/v1/inventory-counts'
  await page.route(COUNTS_URL, (route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 'new-count', status: 'in_progress', started_at: '2026-07-09T12:00:00Z' }),
      })
    } else {
      route.continue()
    }
  })

  await page.route(COUNT_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'new-count', status: 'in_progress', started_at: '2026-07-09T12:00:00Z', items: [] }),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  await page.goto('/inventario/contar/prod-palta')

  // Must redirect to /inventario, not stay or show null
  await expect(page).toHaveURL('/inventario')
})

// ---------------------------------------------------------------------------
// test_cambiar_shows_only_ok_button_no_siguiente (QA H-08)
// In correction mode SIGUIENTE must not be rendered; only "OK y volver".
// ---------------------------------------------------------------------------

test('test_cambiar_shows_only_ok_button_no_siguiente', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.match(/\/items\/[^/]+\/correct$/) && route.request().method() === 'POST') return route.continue()
    if (url.endsWith('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCountWithPalta(4)),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  await page.goto(`/inventario/contar/prod-palta?item_id=${ITEM_ID}`)

  // "OK y volver" must be present
  await expect(page.getByTestId('btn-ok-volver')).toBeVisible()

  // "SIGUIENTE" must NOT be rendered in correction mode
  await expect(page.getByTestId('btn-siguiente')).toHaveCount(0)
})

// ---------------------------------------------------------------------------
// test_corregir_after_complete_returns_to_list_with_completed_count (QA H-02)
// "corregir un producto" from the completado screen navigates to /inventario
// while the countId is still in localStorage (not cleared yet).
// ---------------------------------------------------------------------------

test('test_corregir_after_complete_returns_to_list_with_completed_count', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  const COUNTS_URL = '**/api/v1/inventory-counts'
  const COMPLETE_URL = '**/api/v1/inventory-counts/*/complete'

  // Full count with BOTH mock products counted (needed for terminar to be enabled)
  const fullCount = {
    id: COUNT_ID,
    status: 'in_progress',
    started_at: '2026-07-09T12:00:00Z',
    items: [
      { id: 'item-palta', product_id: 'prod-palta', quantity: 4 },
      { id: 'item-cebolla', product_id: 'prod-cebolla', quantity: 2 },
    ],
  }

  await page.route(COMPLETE_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: COUNT_ID, status: 'completed', completed_at: '2026-07-09T13:00:00Z' }),
    })
  })

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.endsWith('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(fullCount),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  await page.route(COUNTS_URL, (route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 'new-count', status: 'in_progress', started_at: '2026-07-09T14:00:00Z' }),
      })
    } else {
      route.continue()
    }
  })

  await page.goto('/inventario')

  // Wait for terminar button (both products counted → enabled)
  const btn = page.getByTestId('terminar-conteo')
  await expect(btn).toBeEnabled()
  await btn.click()

  // Should arrive at completado
  await expect(page.getByTestId('checkmark')).toBeVisible()

  // countId must still be in localStorage at this point
  const storedId = await page.evaluate((key: string) => localStorage.getItem(key), LS_KEY)
  expect(storedId).toBe(COUNT_ID)

  // Tap "corregir un producto"
  await page.getByTestId('btn-corregir').click()

  // Must be back at /inventario
  await expect(page).toHaveURL('/inventario')
})
