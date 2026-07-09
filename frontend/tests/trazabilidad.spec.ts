import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const SUMMARY_URL = '**/api/v1/dashboard/summary**'
const TRACEABILITY_URL = '**/api/v1/dashboard/traceability/**'

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------

async function injectToken(page: import('@playwright/test').Page, role: 'operator' | 'owner') {
  const token = makeTestJwt(role)
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
  return token
}

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_SUMMARY = {
  products: [
    {
      product_id: 'prod-palta',
      name: 'PALTA',
      unit: 'un',
      stock_now: 4,
      entries: 20,
      consumption: 18,
      consumption_available: true,
      alert: false,
      low_stock_threshold: 10,
    },
  ],
  low_stock: [],
  orders_summary: { completed_count: 0, photo_only_count: 0 },
  last_inventory_at: null,
}

// Backend returns events ASC; we expect the page to show them newest first (DESC)
const MOCK_EVENTS_ASC = [
  {
    id: 'ev-1',
    date: '2026-07-08T12:00:00Z', // oldest
    type: 'INVENTARIO',
    qty: 10,
    unit: 'un',
    operator: 'Maria',
    note: null,
    corrects_id: null,
    corrected_by_note: null,
  },
  {
    id: 'ev-2',
    date: '2026-07-08T17:35:00Z',
    type: 'ENTREGA',
    qty: 15,
    unit: 'un',
    operator: 'Juan',
    note: 'corrige el de 14:32',
    corrects_id: 'ev-old',
    corrected_by_note: null,
  },
  {
    id: 'ev-3',
    date: '2026-07-08T22:30:00Z', // newest
    type: 'INVENTARIO',
    qty: 4,
    unit: 'un',
    operator: 'Juan',
    note: null,
    corrects_id: null,
    corrected_by_note: null,
  },
]

// Pair: one corrected event + one correction
const MOCK_EVENTS_WITH_CORRECTION = [
  {
    id: 'ev-original',
    date: '2026-07-08T14:32:00Z',
    type: 'ENTREGA',
    qty: 12,
    unit: 'un',
    operator: 'Juan',
    note: null,
    corrects_id: null,
    corrected_by_note: 'corregido → 15 un', // this event was corrected
  },
  {
    id: 'ev-correction',
    date: '2026-07-08T14:35:00Z',
    type: 'ENTREGA',
    qty: 15,
    unit: 'un',
    operator: 'Juan',
    note: 'corrige el de 14:32',
    corrects_id: 'ev-original',
    corrected_by_note: null,
  },
]

// ---------------------------------------------------------------------------
// test_traceability_shows_events_newest_first
// ---------------------------------------------------------------------------

test('test_traceability_shows_events_newest_first', async ({ page }) => {
  await injectToken(page, 'owner')

  await page.route(SUMMARY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY),
    })
  })

  await page.route(TRACEABILITY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_EVENTS_ASC),
    })
  })

  await page.goto('/tablero/producto/prod-palta')

  // The desktop table must have ev-3 (INVENTARIO, 22:30) before ev-1 (INVENTARIO, 12:00)
  // We verify row order by checking that the first row contains "4 un" (ev-3) and
  // the last row contains "10 un" (ev-1)
  const tableRows = page.locator('table tbody tr')
  const rowCount = await tableRows.count()
  expect(rowCount).toBe(3)

  // First row is newest: ev-3 with qty=4
  await expect(tableRows.first()).toContainText('4 un')
  // Last row is oldest: ev-1 with qty=10
  await expect(tableRows.last()).toContainText('10 un')
})

// ---------------------------------------------------------------------------
// test_traceability_shows_corrections_as_pairs
// ---------------------------------------------------------------------------

test('test_traceability_shows_corrections_as_pairs', async ({ page }) => {
  await injectToken(page, 'owner')

  await page.route(SUMMARY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY),
    })
  })

  await page.route(TRACEABILITY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_EVENTS_WITH_CORRECTION),
    })
  })

  await page.goto('/tablero/producto/prod-palta')

  // The original (corrected) event must show its correction note.
  // Both the desktop table and mobile cards render the text; use first() to avoid strict-mode.
  await expect(page.getByText('corregido → 15 un').first()).toBeVisible()

  // The correction event must show its note too
  await expect(page.getByText('corrige el de 14:32').first()).toBeVisible()

  // Both rows must be visible (the corrected one with reduced opacity)
  const tableRows = page.locator('table tbody tr')
  const rowCount = await tableRows.count()
  expect(rowCount).toBe(2)
})

// ---------------------------------------------------------------------------
// test_traceability_operator_redirects
// ---------------------------------------------------------------------------

test('test_traceability_operator_redirects', async ({ page }) => {
  await injectToken(page, 'operator')

  await page.goto('/tablero/producto/prod-palta')

  // Operator must be redirected to their home /
  await expect(page).toHaveURL('/')
})

// ---------------------------------------------------------------------------
// test_traceability_nonexistent_product_shows_error
// ---------------------------------------------------------------------------

test('test_traceability_nonexistent_product_shows_error', async ({ page }) => {
  await injectToken(page, 'owner')

  // Summary does NOT include the product being requested
  const summaryWithoutProduct = {
    ...MOCK_SUMMARY,
    products: [],
    low_stock: [],
  }

  await page.route(SUMMARY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(summaryWithoutProduct),
    })
  })

  await page.route(TRACEABILITY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/tablero/producto/prod-inexistente')

  await expect(
    page.getByText(/producto no encontrado/i),
  ).toBeVisible()
})
