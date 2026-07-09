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

function makeCountWithPalta(qty: number) {
  return {
    id: COUNT_ID,
    status: 'in_progress',
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
// test_cambiar_input_precargado_with_current_value
// The input must be pre-filled with the current (previous) quantity.
// ---------------------------------------------------------------------------

test('test_cambiar_input_precargado_with_current_value', async ({ page }) => {
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

  const input = page.getByTestId('qty-input')
  await expect(input).toHaveValue('7')
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
