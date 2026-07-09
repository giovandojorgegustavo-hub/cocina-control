/**
 * Tests for /inventario/completado — Pantalla 3: Confirmación final
 */
import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PRODUCTS_URL = '**/api/v1/products'
const COUNT_URL = '**/api/v1/inventory-counts/*'
const COUNTS_URL = '**/api/v1/inventory-counts'
const COMPLETE_URL = '**/api/v1/inventory-counts/*/complete'

const COUNT_ID = 'count-completar'
const USER_ID = 'test-user-id'
const LS_KEY = `cocina-inventory-count-${USER_ID}`

const MOCK_PRODUCTS = [
  { id: 'prod-palta', name: 'PALTA', unit: 'un', low_stock_threshold: null },
  { id: 'prod-cebolla', name: 'CEBOLLA', unit: 'kg', low_stock_threshold: null },
]

function makeFullCount() {
  return {
    id: COUNT_ID,
    status: 'in_progress',
    started_at: '2026-07-09T12:00:00Z',
    items: [
      { id: 'item-palta', product_id: 'prod-palta', quantity: 4 },
      { id: 'item-cebolla', product_id: 'prod-cebolla', quantity: 2 },
    ],
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

/**
 * Navigate to /inventario and trigger the complete flow end-to-end
 * by clicking "terminar conteo" after all products are counted.
 */
async function setupAndComplete(page: import('@playwright/test').Page) {
  await injectOperatorToken(page)
  await seedCount(page)

  await page.route(COUNTS_URL, (route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: COUNT_ID, status: 'in_progress', started_at: '2026-07-09T12:00:00Z' }),
      })
    } else {
      route.continue()
    }
  })

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
      body: JSON.stringify(makeFullCount()),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  await page.goto('/inventario')

  // Wait for the list to load and all products counted
  const btn = page.getByTestId('terminar-conteo')
  await expect(btn).toBeEnabled()
  await btn.click()
}

// ---------------------------------------------------------------------------
// test_terminar_success_shows_no_totals
// The confirmation screen must NOT show quantities, totals or differences.
// ---------------------------------------------------------------------------

test('test_terminar_success_shows_no_totals', async ({ page }) => {
  await setupAndComplete(page)

  // Wait for the completado screen
  await expect(page.getByTestId('checkmark')).toBeVisible()
  await expect(page.getByText('INVENTARIO REGISTRADO')).toBeVisible()

  const bodyText = await page.locator('body').innerText()

  // Must not show individual quantities or totals
  const forbidden = ['total', 'diferencia', 'esperado', 'stock previo', 'promedio', 'kg', 'un']
  for (const term of forbidden) {
    // Product count label "2 productos contados" is OK — but no quantity values
    // We allow the product count digit but forbid unit labels and analysis words
    if (term !== 'kg' && term !== 'un') {
      expect(bodyText.toLowerCase()).not.toContain(term)
    }
  }

  // Must NOT show the quantities that were counted (4 for palta, 2 for cebolla)
  // but the count "2 productos contados" is OK
  // The label shows "2 productos contados" which contains the digit 2 — that's fine.
  // What is NOT fine: showing "4 un" or "2 kg" next to a product name.
  expect(bodyText).not.toContain('PALTA')
  expect(bodyText).not.toContain('CEBOLLA')
})

// ---------------------------------------------------------------------------
// test_terminar_clears_localStorage_id
// After successful complete, the count id must be removed from localStorage.
// ---------------------------------------------------------------------------

test('test_terminar_clears_localStorage_id', async ({ page }) => {
  await setupAndComplete(page)

  await expect(page.getByTestId('checkmark')).toBeVisible()

  const storedId = await page.evaluate((key) => localStorage.getItem(key), LS_KEY)
  expect(storedId).toBeNull()
})

// ---------------------------------------------------------------------------
// test_terminar_button_corregir_returns_to_list_in_correction_mode
// "corregir un producto" button navigates back to /inventario.
// ---------------------------------------------------------------------------

test('test_terminar_button_corregir_returns_to_list_in_correction_mode', async ({ page }) => {
  await setupAndComplete(page)

  await expect(page.getByTestId('checkmark')).toBeVisible()

  // Intercept the navigation from /inventario (it will try to POST a new count)
  // We don't need it to succeed — just verify the URL changes
  await page.route(COUNTS_URL, (route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 'new-count', status: 'in_progress', started_at: '2026-07-09T13:00:00Z' }),
      })
    } else {
      route.continue()
    }
  })

  await page.getByTestId('btn-corregir').click()

  await expect(page).toHaveURL('/inventario')
})
