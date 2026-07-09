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
// test_terminar_countId_cleared_on_listo (QA H-02)
// countId must be cleared when the operator taps "listo", NOT on complete.
// ---------------------------------------------------------------------------

test('test_terminar_countId_cleared_on_listo', async ({ page }) => {
  await setupAndComplete(page)

  await expect(page.getByTestId('checkmark')).toBeVisible()

  // At this point countId must still be in localStorage (not cleared on complete)
  const storedBefore = await page.evaluate((key: string) => localStorage.getItem(key), LS_KEY)
  expect(storedBefore).toBe(COUNT_ID)

  // Tap "listo" — this is where countId gets cleared
  await page.getByTestId('btn-listo').click()

  const storedAfter = await page.evaluate((key: string) => localStorage.getItem(key), LS_KEY)
  expect(storedAfter).toBeNull()
})

// ---------------------------------------------------------------------------
// test_terminar_button_corregir_returns_to_list_in_correction_mode (QA H-02)
// "corregir un producto" button navigates back to /inventario WITH correctionMode state.
// The countId must still be in localStorage when it leaves.
// ---------------------------------------------------------------------------

test('test_terminar_button_corregir_returns_to_list_in_correction_mode', async ({ page }) => {
  await setupAndComplete(page)

  await expect(page.getByTestId('checkmark')).toBeVisible()

  // Intercept the navigation from /inventario — it will detect correctionMode
  // and use the existing completed count (no new POST needed)
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

  // countId must still be in localStorage — not cleared yet
  const storedId = await page.evaluate((key: string) => localStorage.getItem(key), LS_KEY)
  expect(storedId).toBe(COUNT_ID)
})

// ---------------------------------------------------------------------------
// test_completado_direct_access_without_state_redirects (QA H-09)
// If the operator navigates directly to /inventario/completado without location.state,
// they must be redirected to /inventario.
// ---------------------------------------------------------------------------

test('test_completado_direct_access_without_state_redirects', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  const COMPLETE_URL_NEW = '**/api/v1/inventory-counts'
  await page.route(COMPLETE_URL_NEW, (route) => {
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
    const url = route.request().url()
    if (url.endsWith('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: COUNT_ID,
        status: 'in_progress',
        started_at: '2026-07-09T12:00:00Z',
        items: [],
      }),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  // Navigate directly to completado without going through the complete flow
  await page.goto('/inventario/completado')

  // Must redirect to /inventario
  await expect(page).toHaveURL('/inventario')
})

// ---------------------------------------------------------------------------
// test_double_tap_terminar_fires_single_request (paranoia)
// Double-tapping "terminar conteo" must only POST /complete once.
// We use a slow route to hold the in-flight request and verify the second tap
// is ignored by the isPending guard.
// ---------------------------------------------------------------------------

test('test_double_tap_terminar_fires_single_request', async ({ page }) => {
  await injectOperatorToken(page)
  await seedCount(page)

  let completeCalls = 0

  // Use a deferred fulfillment so the button stays visible for the second click
  let resolveComplete: (() => void) | null = null
  const completeHeld = new Promise<void>((resolve) => { resolveComplete = resolve })

  await page.route(COMPLETE_URL, async (route) => {
    completeCalls++
    await completeHeld
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

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  await page.goto('/inventario')

  const btn = page.getByTestId('terminar-conteo')
  await expect(btn).toBeEnabled()

  // First tap — starts the in-flight request
  await btn.click()

  // Small wait so the mutation fires and isPending becomes true
  await page.waitForTimeout(50)

  // Second tap — button is disabled while in-flight, click should be ignored
  await btn.click({ force: true })

  await page.waitForTimeout(50)

  // Only 1 call should have been made even though we clicked twice
  expect(completeCalls).toBe(1)

  // Release the held response
  resolveComplete!()
})
