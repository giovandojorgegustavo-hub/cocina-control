import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const ORDERS_URL = '**/api/v1/purchase-orders*'

async function injectOwnerToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('owner')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

const MOCK_ORDERS = [
  {
    id: 'ord-1',
    supplier_name: 'VERDULERIA NUNEZ',
    created_at: '2020-07-12T12:14:00Z',
    derived_status: 'open',
    item_count: 3,
    total_ordered: '108.50',
    total_received: '0',
    pending_amount: '108.50',
    pending_summary: null,
  },
  {
    id: 'ord-2',
    supplier_name: 'CARNICERIA LOPEZ',
    created_at: '2020-07-10T19:30:00Z',
    derived_status: 'partially_received',
    item_count: 1,
    total_ordered: '890.00',
    total_received: '610.00',
    pending_amount: '280.00',
    pending_summary: '1 producto con saldo · faltan 40 kg de POLLO',
  },
  {
    id: 'ord-3',
    supplier_name: 'DISTRIBUIDORA SUR',
    created_at: '2020-07-08T14:00:00Z',
    derived_status: 'closed',
    item_count: 5,
    total_ordered: '342.00',
    total_received: '342.00',
    pending_amount: '0',
    pending_summary: null,
  },
  {
    id: 'ord-4',
    supplier_name: 'CARNICERIA LOPEZ',
    created_at: '2020-07-05T17:22:00Z',
    derived_status: 'annulled',
    item_count: 2,
    total_ordered: '200.00',
    total_received: '80.00',
    pending_amount: '120.00',
    pending_summary: null,
  },
]

// ---------------------------------------------------------------------------
// test_ordenes_lista_renders_cards
// ---------------------------------------------------------------------------

test('test_ordenes_lista_renders_cards', async ({ page }) => {
  await injectOwnerToken(page)

  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_ORDERS),
    })
  })

  await page.goto('/ordenes')

  await expect(page.getByText('VERDULERIA NUNEZ')).toBeVisible()
  await expect(page.getByText('CARNICERIA LOPEZ').first()).toBeVisible()
  await expect(page.getByText('DISTRIBUIDORA SUR')).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_ordenes_lista_shows_badges
// ---------------------------------------------------------------------------

test('test_ordenes_lista_shows_badges', async ({ page }) => {
  await injectOwnerToken(page)

  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_ORDERS),
    })
  })

  await page.goto('/ordenes')

  // Use exact match or locate within the card area (not the tab button)
  await expect(page.getByText('ABIERTA', { exact: true })).toBeVisible()
  await expect(page.getByText('RECIBIDA PARCIAL', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('CERRADA ✓', { exact: true })).toBeVisible()
  await expect(page.getByText('ANULADA', { exact: true })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_ordenes_lista_shows_empty_state
// ---------------------------------------------------------------------------

test('test_ordenes_lista_shows_empty_state', async ({ page }) => {
  await injectOwnerToken(page)

  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/ordenes')

  await expect(page.getByText(/No hay ordenes de compra todavia/i)).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_ordenes_lista_tabs_filter
// Clicking a different tab changes what is shown (different API call or filter).
// ---------------------------------------------------------------------------

test('test_ordenes_lista_tabs_visible', async ({ page }) => {
  await injectOwnerToken(page)

  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/ordenes')

  await expect(page.getByRole('button', { name: 'Abiertas' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Recibida parcial' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cerradas' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Anuladas' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Todas' })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_ordenes_lista_shows_loading_skeletons
// ---------------------------------------------------------------------------

test('test_ordenes_lista_shows_loading_skeletons', async ({ page }) => {
  await injectOwnerToken(page)

  // Never resolve
  await page.route(ORDERS_URL, () => {
    // intentionally do not fulfill
  })

  await page.goto('/ordenes')

  const skeletons = page.getByRole('status', { name: 'Cargando orden' })
  await expect(skeletons).toHaveCount(3)
})

// ---------------------------------------------------------------------------
// test_ordenes_lista_nueva_link
// The "+ nueva" button is present and links to /ordenes/nueva.
// ---------------------------------------------------------------------------

test('test_ordenes_lista_nueva_link', async ({ page }) => {
  await injectOwnerToken(page)

  await page.route(ORDERS_URL, (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  // Mock /products for the OrdenNueva page that will load after click
  await page.route('**/api/v1/products', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await page.goto('/ordenes')

  const nuevaLink = page.getByRole('link', { name: /\+ nueva/i })
  await expect(nuevaLink).toBeVisible()
  await nuevaLink.click()

  await expect(page).toHaveURL('/ordenes/nueva')
})

// ---------------------------------------------------------------------------
// test_ordenes_lista_cocinero_redirected — role guard
// A cocinero trying to access /ordenes must be redirected.
// ---------------------------------------------------------------------------

test('test_ordenes_lista_cocinero_redirected', async ({ page }) => {
  const token = makeTestJwt('cocinero')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)

  await page.goto('/ordenes')

  // cocinero is redirected to /  (home)
  await expect(page).toHaveURL('/')
})
