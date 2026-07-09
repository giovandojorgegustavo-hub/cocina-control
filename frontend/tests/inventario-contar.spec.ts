/**
 * Tests for /inventario/contar/:productId — Pantalla 2: Contar producto
 */
import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PRODUCTS_URL = '**/api/v1/products'
const COUNT_URL = '**/api/v1/inventory-counts/*'
const ITEMS_URL = '**/api/v1/inventory-counts/*/items'

const COUNT_ID = 'count-contar'
const USER_ID = 'test-user-id'
const LS_KEY = `cocina-inventory-count-${USER_ID}`

const MOCK_PRODUCTS = [
  { id: 'prod-palta', name: 'PALTA', unit: 'un', low_stock_threshold: null },
  { id: 'prod-cebolla', name: 'CEBOLLA', unit: 'kg', low_stock_threshold: null },
  { id: 'prod-tomate', name: 'TOMATE', unit: 'kg', low_stock_threshold: null },
]

function makeCount(items: Array<{ id: string; product_id: string; quantity: number }> = []) {
  return {
    id: COUNT_ID,
    status: 'in_progress',
    started_at: '2026-07-09T12:00:00Z',
    items,
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

async function seedCount(page: import('@playwright/test').Page, id = COUNT_ID) {
  await page.evaluate(
    ([key, val]) => localStorage.setItem(key, val),
    [LS_KEY, id],
  )
}

async function setupBasicMocks(
  page: import('@playwright/test').Page,
  countItems: Array<{ id: string; product_id: string; quantity: number }> = [],
) {
  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    // Let /complete and /items/* pass through unless we override
    if (url.match(/\/items\/[^/]+\/correct$/)) return route.continue()
    if (url.endsWith('/complete')) return route.continue()
    if (url.match(/\/items$/) && route.request().method() === 'POST') return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCount(countItems)),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })
}

// ---------------------------------------------------------------------------
// test_contar_input_has_no_default_value
// Principio #1: input must start empty, not pre-loaded with expected quantity.
// ---------------------------------------------------------------------------

test('test_contar_input_has_no_default_value', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)
  await setupBasicMocks(page)

  await page.goto('/inventario/contar/prod-palta')

  const input = page.getByTestId('qty-input')
  await expect(input).toBeVisible()
  await expect(input).toHaveValue('')
})

// ---------------------------------------------------------------------------
// test_contar_saves_and_navigates_to_next_pending
// SIGUIENTE → saves via POST /items and goes to next pending product.
// ---------------------------------------------------------------------------

test('test_contar_saves_and_navigates_to_next_pending', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  let postItemBody: unknown = null

  await page.route(ITEMS_URL, (route) => {
    postItemBody = route.request().postDataJSON()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ item_id: 'item-new', product_id: 'prod-palta', quantity: 4 }),
    })
  })

  // After save, the count now has PALTA counted; CEBOLLA and TOMATE still pending
  let countCallCount = 0
  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.match(/\/items$/) && route.request().method() === 'POST') return route.continue()
    if (url.includes('/complete')) return route.continue()
    if (url.match(/\/items\/[^/]+\/correct$/)) return route.continue()

    countCallCount++
    const items =
      countCallCount > 1
        ? [{ id: 'item-new', product_id: 'prod-palta', quantity: 4 }]
        : []
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCount(items)),
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

  const input = page.getByTestId('qty-input')
  await input.fill('4')

  await page.getByTestId('btn-siguiente').click()

  // Should navigate to next pending (alphabetically CEBOLLA)
  await expect(page).toHaveURL(/\/inventario\/contar\/prod-cebolla/)

  // Verify payload
  expect(postItemBody).toMatchObject({ product_id: 'prod-palta', quantity: 4 })
})

// ---------------------------------------------------------------------------
// test_contar_ok_y_volver_returns_to_list
// ---------------------------------------------------------------------------

test('test_contar_ok_y_volver_returns_to_list', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  await page.route(ITEMS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ item_id: 'item-new', product_id: 'prod-palta', quantity: 2 }),
    })
  })

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.match(/\/items$/) && route.request().method() === 'POST') return route.continue()
    if (url.includes('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCount()),
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

  await page.getByTestId('qty-input').fill('2')
  await page.getByTestId('btn-ok-volver').click()

  await expect(page).toHaveURL('/inventario')
})

// ---------------------------------------------------------------------------
// test_contar_zero_valid
// Quantity 0 is a valid explicit count.
// ---------------------------------------------------------------------------

test('test_contar_zero_valid', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  let postItemBody: unknown = null

  await page.route(ITEMS_URL, (route) => {
    postItemBody = route.request().postDataJSON()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ item_id: 'item-zero', product_id: 'prod-palta', quantity: 0 }),
    })
  })

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.match(/\/items$/) && route.request().method() === 'POST') return route.continue()
    if (url.includes('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCount()),
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

  const input = page.getByTestId('qty-input')
  await input.fill('0')

  const btnSiguiente = page.getByTestId('btn-siguiente')
  await expect(btnSiguiente).toBeEnabled()
  await btnSiguiente.click()

  // Verify 0 was sent
  await page.waitForTimeout(200) // allow mutation to fire
  expect(postItemBody).toMatchObject({ quantity: 0 })
})

// ---------------------------------------------------------------------------
// test_contar_negative_and_infinity_rejected
// Negative numbers and non-finite values must disable the save buttons.
// ---------------------------------------------------------------------------

test('test_contar_negative_and_infinity_rejected', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)
  await setupBasicMocks(page)

  await page.goto('/inventario/contar/prod-palta')

  const input = page.getByTestId('qty-input')
  const btnSig = page.getByTestId('btn-siguiente')
  const btnOk = page.getByTestId('btn-ok-volver')

  // Negative
  await input.fill('-1')
  await expect(btnSig).toBeDisabled()
  await expect(btnOk).toBeDisabled()

  // Infinity string (not finite)
  await input.fill('Infinity')
  await expect(btnSig).toBeDisabled()
  await expect(btnOk).toBeDisabled()

  // Empty string (cleared) — NaN equivalent for a number input
  await input.fill('')
  await expect(btnSig).toBeDisabled()
  await expect(btnOk).toBeDisabled()
})

// ---------------------------------------------------------------------------
// test_error_toast_keeps_typed_value
// On server 500, toast appears and the input keeps the typed quantity.
// ---------------------------------------------------------------------------

test('test_error_toast_keeps_typed_value', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  await page.route(ITEMS_URL, (route) => {
    route.fulfill({ status: 500, body: '' })
  })

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.match(/\/items$/) && route.request().method() === 'POST') return route.continue()
    if (url.includes('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCount()),
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

  const input = page.getByTestId('qty-input')
  await input.fill('7')
  await page.getByTestId('btn-ok-volver').click()

  // Toast should appear
  await expect(page.getByRole('alert')).toBeVisible()

  // Typed value must NOT be cleared
  await expect(input).toHaveValue('7')
})
