/**
 * Tests for /inventario — Pantalla 1: Lista de productos a contar
 */
import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PRODUCTS_URL = '**/api/v1/products'
const COUNTS_URL = '**/api/v1/inventory-counts'
const COUNT_URL = '**/api/v1/inventory-counts/*'

const COUNT_ID = 'count-abc'
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

async function clearInventoryLS(page: import('@playwright/test').Page) {
  await page.evaluate((key) => localStorage.removeItem(key), LS_KEY)
}

// ---------------------------------------------------------------------------
// test_lista_starts_new_count_when_none_in_localStorage
// ---------------------------------------------------------------------------

test('test_lista_starts_new_count_when_none_in_localStorage', async ({ page }) => {
  await injectOperatorToken(page)

  let postCalled = false

  await page.route(COUNTS_URL, (route) => {
    if (route.request().method() === 'POST') {
      postCalled = true
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: COUNT_ID, status: 'in_progress', started_at: '2026-07-09T12:00:00Z' }),
      })
    } else {
      route.continue()
    }
  })

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
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

  // Ensure localStorage is clear
  await clearInventoryLS(page)
  await page.goto('/inventario')

  // Wait for products to appear
  await expect(page.getByText('PALTA')).toBeVisible()

  expect(postCalled).toBe(true)
})

// ---------------------------------------------------------------------------
// test_lista_resumes_existing_count_from_localStorage
// ---------------------------------------------------------------------------

test('test_lista_resumes_existing_count_from_localStorage', async ({ page }) => {
  await injectOperatorToken(page)

  let postCalled = false

  await page.route(COUNTS_URL, (route) => {
    if (route.request().method() === 'POST') {
      postCalled = true
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'new-count', status: 'in_progress', started_at: '2026-07-09T13:00:00Z' }) })
    } else {
      route.continue()
    }
  })

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
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

  // Pre-seed localStorage with a count id
  await page.evaluate(
    ([key, id]) => localStorage.setItem(key, id),
    [LS_KEY, COUNT_ID],
  )

  await page.goto('/inventario')
  await expect(page.getByText('PALTA')).toBeVisible()

  // POST should NOT have been called — resumed from localStorage
  expect(postCalled).toBe(false)
})

// ---------------------------------------------------------------------------
// test_lista_resumes_but_404_starts_new
// Server responds 404 for the saved count → clear localStorage + POST new
// ---------------------------------------------------------------------------

test('test_lista_resumes_but_404_starts_new', async ({ page }) => {
  await injectOperatorToken(page)

  let postCalled = false
  let getCallCount = 0

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.includes('/complete')) return route.continue()

    if (route.request().method() === 'GET') {
      getCallCount++
      if (getCallCount === 1) {
        // First GET (the saved count) → 404
        route.fulfill({ status: 404, body: '' })
      } else {
        // Second GET (after POST creates new count) → ok
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(makeCount()),
        })
      }
    } else {
      route.continue()
    }
  })

  await page.route(COUNTS_URL, (route) => {
    if (route.request().method() === 'POST') {
      postCalled = true
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 'new-count-after-404', status: 'in_progress', started_at: '2026-07-09T12:00:00Z' }),
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

  // Pre-seed with a stale count id
  await page.evaluate(
    ([key, id]) => localStorage.setItem(key, id),
    [LS_KEY, 'stale-count-id'],
  )

  await page.goto('/inventario')
  await expect(page.getByText('PALTA')).toBeVisible()

  expect(postCalled).toBe(true)

  // localStorage should no longer contain the stale id
  const storedId = await page.evaluate((key) => localStorage.getItem(key), LS_KEY)
  expect(storedId).not.toBe('stale-count-id')
})

// ---------------------------------------------------------------------------
// test_lista_hides_expected_values
// The DOM must not contain any hint of expected stock, averages, or comparisons.
// ---------------------------------------------------------------------------

test('test_lista_hides_expected_values', async ({ page }) => {
  await injectOperatorToken(page)

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

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
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

  await clearInventoryLS(page)
  await page.goto('/inventario')
  await expect(page.getByText('PALTA')).toBeVisible()

  const bodyText = await page.locator('body').innerText()

  const forbidden = ['esperado', 'stock previo', 'promedio', 'diferencia', 'anunciado', 'debería']
  for (const term of forbidden) {
    expect(bodyText.toLowerCase()).not.toContain(term)
  }
})

// ---------------------------------------------------------------------------
// test_lista_pending_first_ordered_alphabetically
// Pending products appear before counted ones, sorted A→Z within each group.
// ---------------------------------------------------------------------------

test('test_lista_pending_first_ordered_alphabetically', async ({ page }) => {
  await injectOperatorToken(page)

  // PALTA is already counted; CEBOLLA and TOMATE are pending
  const countWithPalta = makeCount([
    { id: 'item-1', product_id: 'prod-palta', quantity: 4 },
  ])

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

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.includes('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(countWithPalta),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  await clearInventoryLS(page)
  await page.goto('/inventario')
  await expect(page.getByText('CEBOLLA')).toBeVisible()

  // Get all product name elements in DOM order
  const names = await page.locator('[aria-label*="Contar"], [aria-label*="Cambiar"]').all()
  const labels = await Promise.all(names.map((n) => n.getAttribute('aria-label')))

  // Pending buttons come first (Contar), then counted (Cambiar)
  const contar = labels.filter((l) => l?.startsWith('Contar'))
  const cambiar = labels.filter((l) => l?.startsWith('Cambiar'))

  // All "contar" entries should appear before "cambiar" in the DOM
  const firstCambiarIndex = labels.findIndex((l) => l?.startsWith('Cambiar'))
  const lastContarIndex = labels.findLastIndex((l) => l?.startsWith('Contar'))

  expect(lastContarIndex).toBeLessThan(firstCambiarIndex)

  // Pending products should be sorted alphabetically: CEBOLLA before TOMATE
  expect(contar[0]).toContain('CEBOLLA')
  expect(contar[1]).toContain('TOMATE')

  // PALTA counted
  expect(cambiar[0]).toContain('PALTA')
})

// ---------------------------------------------------------------------------
// test_lista_terminar_disabled_until_all_counted
// ---------------------------------------------------------------------------

test('test_lista_terminar_disabled_until_all_counted', async ({ page }) => {
  await injectOperatorToken(page)

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

  // Only 1 of 3 products counted
  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.includes('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCount([{ id: 'item-1', product_id: 'prod-palta', quantity: 3 }])),
    })
  })

  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })

  await clearInventoryLS(page)
  await page.goto('/inventario')
  await expect(page.getByText('PALTA')).toBeVisible()

  const btn = page.getByTestId('terminar-conteo')
  await expect(btn).toBeDisabled()
  await expect(btn).toContainText('1/3')
})

// ---------------------------------------------------------------------------
// test_lista_no_products_shows_empty_state
// ---------------------------------------------------------------------------

test('test_lista_no_products_shows_empty_state', async ({ page }) => {
  await injectOperatorToken(page)

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

  await page.route(COUNT_URL, (route) => {
    const url = route.request().url()
    if (url.includes('/complete')) return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeCount()),
    })
  })

  // Empty catalogue
  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await clearInventoryLS(page)
  await page.goto('/inventario')

  await expect(page.getByTestId('empty-catalogue')).toBeVisible()
  await expect(page.getByText(/pedile al dueño/i)).toBeVisible()
})
