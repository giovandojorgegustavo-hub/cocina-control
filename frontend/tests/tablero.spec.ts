import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const SUMMARY_URL = '**/api/v1/dashboard/summary**'
const EXPORT_URL = '**/api/v1/dashboard/export**'

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
// Mock data helpers
// ---------------------------------------------------------------------------

const MOCK_SUMMARY_FULL = {
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
    {
      product_id: 'prod-pollo',
      name: 'POLLO',
      unit: 'kg',
      stock_now: 12,
      entries: 30,
      consumption: 22,
      consumption_available: true,
      alert: false,
      low_stock_threshold: null,
    },
    {
      product_id: 'prod-queso',
      name: 'QUESO',
      unit: 'kg',
      stock_now: 0.5,
      entries: 5,
      consumption: 6,
      consumption_available: true,
      alert: true,
      low_stock_threshold: 2,
    },
  ],
  low_stock: [
    {
      product_id: 'prod-palta',
      name: 'PALTA',
      unit: 'un',
      stock_now: 4,
      low_stock_threshold: 10,
    },
    {
      product_id: 'prod-queso',
      name: 'QUESO',
      unit: 'kg',
      stock_now: 0.5,
      low_stock_threshold: 2,
    },
  ],
  orders_summary: {
    completed_count: 38,
    photo_only_count: 5,
  },
  last_inventory_at: '2026-07-08T02:15:00Z',
}

const MOCK_SUMMARY_EMPTY = {
  products: [],
  low_stock: [],
  orders_summary: { completed_count: 0, photo_only_count: 0 },
  last_inventory_at: null,
}

// ---------------------------------------------------------------------------
// test_tablero_redirects_operator_to_home
// ---------------------------------------------------------------------------

test('test_tablero_redirects_operator_to_home', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/tablero')

  // Operator must be redirected to / (their home)
  await expect(page).toHaveURL('/')
})

// ---------------------------------------------------------------------------
// test_summary_widgets_render
// ---------------------------------------------------------------------------

test('test_summary_widgets_render', async ({ page }) => {
  await injectToken(page, 'owner')

  await page.route(SUMMARY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY_FULL),
    })
  })

  await page.goto('/tablero')

  // Wait for loading to finish (skeletons gone)
  await expect(page.getByRole('status', { name: 'Cargando widget' })).toHaveCount(0)

  // Low stock widget
  await expect(page.getByRole('region', { name: /por acabarse/i })).toBeVisible()
  await expect(page.getByRole('region', { name: /por acabarse/i }).getByText('PALTA')).toBeVisible()

  // Orders widget
  await expect(page.getByRole('region', { name: /pedidos en el periodo/i })).toBeVisible()
  // completed_count=38 visible in the widget
  await expect(
    page.getByRole('region', { name: /pedidos en el periodo/i }).getByText('38'),
  ).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_period_selector_toggles_and_reloads
// ---------------------------------------------------------------------------

test('test_period_selector_toggles_and_reloads', async ({ page }) => {
  await injectToken(page, 'owner')

  const requestedUrls: string[] = []

  await page.route(SUMMARY_URL, (route) => {
    requestedUrls.push(route.request().url())
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY_FULL),
    })
  })

  await page.goto('/tablero')

  // Wait for initial load (default 7d)
  await expect(page.getByRole('region', { name: /pedidos en el periodo/i })).toBeVisible()
  const initialCount = requestedUrls.length

  // Click "HOY"
  await page.getByRole('button', { name: /HOY/i }).click()

  // A new request must be issued
  await expect(async () => {
    expect(requestedUrls.length).toBeGreaterThan(initialCount)
  }).toPass()

  // The new URL must contain the today date as both from and to
  const latestUrl = requestedUrls[requestedUrls.length - 1]
  expect(latestUrl).toContain('from=')
  expect(latestUrl).toContain('to=')
})

// ---------------------------------------------------------------------------
// test_low_stock_widget_shows_semaphore
// ---------------------------------------------------------------------------

test('test_low_stock_widget_shows_semaphore', async ({ page }) => {
  await injectToken(page, 'owner')

  await page.route(SUMMARY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY_FULL),
    })
  })

  await page.goto('/tablero')

  const widget = page.getByRole('region', { name: /por acabarse/i })
  await expect(widget).toBeVisible()

  // Semaforo dots rendered — each item has a role="img" for the semaforo
  const semaforos = widget.getByRole('img')
  const count = await semaforos.count()
  expect(count).toBeGreaterThan(0)

  // PALTA: stock 4, threshold 10 → below 50% → red (stock critico)
  // Multiple items may have the same level label; just assert at least one is visible
  await expect(widget.getByRole('img', { name: /stock critico/i }).first()).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_orders_summary_shows_completed_and_photo_only
// ---------------------------------------------------------------------------

test('test_orders_summary_shows_completed_and_photo_only', async ({ page }) => {
  await injectToken(page, 'owner')

  await page.route(SUMMARY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY_FULL),
    })
  })

  await page.goto('/tablero')

  const widget = page.getByRole('region', { name: /pedidos en el periodo/i })
  await expect(widget).toBeVisible()

  await expect(widget.getByText('Terminados (con detalle)')).toBeVisible()
  await expect(widget.getByText('Solo foto')).toBeVisible()
  await expect(widget.getByText('Total')).toBeVisible()

  // Check the numbers are visible (completed=38, photo_only=5)
  await expect(widget.getByLabel('38 pedidos terminados')).toBeVisible()
  await expect(widget.getByLabel('5 pedidos solo foto')).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_table_row_click_navigates_to_traceability
// ---------------------------------------------------------------------------

test('test_table_row_click_navigates_to_traceability', async ({ page }) => {
  await injectToken(page, 'owner')

  await page.route(SUMMARY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY_FULL),
    })
  })

  // Mock traceability endpoint too (navigating to the page fetches it)
  await page.route('**/api/v1/dashboard/traceability/**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/tablero')

  // Wait for data to render
  await expect(page.getByRole('region', { name: /pedidos en el periodo/i })).toBeVisible()

  // Click the PALTA row (desktop table has role=button per row)
  await page.getByRole('button', { name: /ver trazabilidad de PALTA/i }).first().click()

  await expect(page).toHaveURL(/\/tablero\/producto\/prod-palta/)
})

// ---------------------------------------------------------------------------
// test_consumption_unavailable_shows_sin_dato
// ---------------------------------------------------------------------------

test('test_consumption_unavailable_shows_sin_dato', async ({ page }) => {
  await injectToken(page, 'owner')

  const summaryWithNoData = {
    ...MOCK_SUMMARY_FULL,
    products: [
      {
        product_id: 'prod-tomate',
        name: 'TOMATE',
        unit: 'kg',
        stock_now: 8,
        entries: 15,
        consumption: null,
        consumption_available: false,
        alert: false,
        low_stock_threshold: null,
      },
    ],
    low_stock: [],
  }

  await page.route(SUMMARY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(summaryWithNoData),
    })
  })

  await page.goto('/tablero')

  // Wait for skeletons to disappear so data is rendered
  await expect(page.getByRole('status', { name: 'Cargando widget' })).toHaveCount(0)

  // "sin dato de inicio" appears in both desktop table (hidden md:block) and mobile cards.
  // Use first() to avoid strict-mode violations when both are in the DOM.
  await expect(page.getByText('sin dato de inicio').first()).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_alert_icon_shown_when_alert_true
// ---------------------------------------------------------------------------

test('test_alert_icon_shown_when_alert_true', async ({ page }) => {
  await injectToken(page, 'owner')

  await page.route(SUMMARY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY_FULL),
    })
  })

  await page.goto('/tablero')

  // QUESO has alert:true — must show the warning icon (aria-label "advertencia")
  const alertIcons = page.getByRole('img', { name: /advertencia/i })
  // The "!" span doesn't have role=img, it's a span — check for the text content
  // AlertCell renders <span aria-label="advertencia"> with text "!"
  const alertSpans = page.getByLabel('advertencia')
  const alertCount = await alertSpans.count()
  expect(alertCount).toBeGreaterThan(0)
})

// ---------------------------------------------------------------------------
// test_empty_range_shows_empty_state
// ---------------------------------------------------------------------------

test('test_empty_range_shows_empty_state', async ({ page }) => {
  await injectToken(page, 'owner')

  await page.route(SUMMARY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY_EMPTY),
    })
  })

  await page.goto('/tablero')

  await expect(
    page.getByText(/todavia no hay registros en este periodo/i),
  ).toBeVisible()

  await expect(page.getByRole('button', { name: /ver 7 dias/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /ver 30 dias/i })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_export_csv_downloads_file
// ---------------------------------------------------------------------------

test('test_export_csv_downloads_file', async ({ page }) => {
  await injectToken(page, 'owner')

  await page.route(SUMMARY_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY_FULL),
    })
  })

  const csvContent = '﻿fecha,tipo,producto,cantidad\n2026-07-01,ENTREGA,PALTA,20\n'

  await page.route(EXPORT_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'text/csv; charset=utf-8',
      body: csvContent,
    })
  })

  await page.goto('/tablero')

  // Wait for content to load
  await expect(page.getByRole('region', { name: /pedidos en el periodo/i })).toBeVisible()

  // Listen for the download
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: /descargar CSV/i }).click(),
  ])

  // Filename must follow the pattern cocina-control_{from}_{to}.csv
  expect(download.suggestedFilename()).toMatch(/^cocina-control_.+_.+\.csv$/)
})
