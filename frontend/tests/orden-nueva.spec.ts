import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const ORDERS_URL = '**/api/v1/purchase-orders'
const PRODUCTS_URL = '**/api/v1/products'

const MOCK_PRODUCTS = [
  { id: 'prod-palta', name: 'PALTA', unit: 'un', low_stock_threshold: null },
  { id: 'prod-tomate', name: 'TOMATE', unit: 'kg', low_stock_threshold: null },
  { id: 'prod-cebolla', name: 'CEBOLLA', unit: 'kg', low_stock_threshold: null },
]

async function injectOwnerToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('owner')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

async function injectAdminToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('admin')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

async function setupMocks(page: import('@playwright/test').Page) {
  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS),
    })
  })
  // purchase-orders GET for datalist (existing orders)
  await page.route('**/api/v1/purchase-orders?*', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })
  await page.route(ORDERS_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    } else {
      route.continue()
    }
  })
}

// ---------------------------------------------------------------------------
// test_orden_nueva_happy_path — owner creates order and navigates to /ordenes
// ---------------------------------------------------------------------------

test('test_orden_nueva_happy_path', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  const postBodies: string[] = []
  await page.route(ORDERS_URL, (route) => {
    if (route.request().method() === 'POST') {
      postBodies.push(route.request().postData() ?? '')
      route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'new-order-id',
          supplier_name: 'Verduleria Test',
          created_at: new Date().toISOString(),
          created_by_name: 'Test User',
          derived_status: 'open',
          items: [],
          total_ordered: '36.00',
          total_received: '0',
          pending_amount: '36.00',
          partida_count: 0,
        }),
      })
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
  })

  // Mock /ordenes page (after redirect)
  await page.goto('/ordenes/nueva')

  // Fill supplier
  await page.getByLabel('Proveedor').fill('Verduleria Test')

  // Select product PALTA
  await page.getByLabel('Elegir producto').selectOption('prod-palta')

  // Fill qty and cost
  await page.getByLabel('Cantidad').fill('30')
  await page.getByLabel('Costo unitario').fill('1.20')

  // Submit button should be enabled
  const submitBtn = page.getByRole('button', { name: /guardar orden/i })
  await expect(submitBtn).toBeEnabled()
  await submitBtn.click()

  // Should navigate to /ordenes
  await expect(page).toHaveURL('/ordenes', { timeout: 5000 })

  // Verify the POST body
  expect(postBodies.length).toBeGreaterThan(0)
  const body = JSON.parse(postBodies[0]) as {
    supplier_name: string
    items: Array<{ product_id: string; expected_qty: number; unit_cost: number }>
  }
  expect(body.supplier_name).toBe('Verduleria Test')
  expect(body.items).toHaveLength(1)
  expect(body.items[0].product_id).toBe('prod-palta')
  expect(body.items[0].expected_qty).toBe(30)
  expect(body.items[0].unit_cost).toBe(1.2)
})

// ---------------------------------------------------------------------------
// test_orden_nueva_submit_disabled_without_supplier
// ---------------------------------------------------------------------------

test('test_orden_nueva_submit_disabled_without_supplier', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')

  // Select product but no supplier
  await page.getByLabel('Elegir producto').selectOption('prod-palta')
  await page.getByLabel('Cantidad').fill('10')
  await page.getByLabel('Costo unitario').fill('2.50')

  const submitBtn = page.getByRole('button', { name: /guardar orden/i })
  await expect(submitBtn).toBeDisabled()
})

// ---------------------------------------------------------------------------
// test_orden_nueva_submit_disabled_without_items
// ---------------------------------------------------------------------------

test('test_orden_nueva_submit_disabled_without_items', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')

  // Supplier filled but item row is empty
  await page.getByLabel('Proveedor').fill('Proveedor Test')

  const submitBtn = page.getByRole('button', { name: /guardar orden/i })
  await expect(submitBtn).toBeDisabled()
})

// ---------------------------------------------------------------------------
// test_orden_nueva_server_error_shows_toast_and_preserves_data
// ---------------------------------------------------------------------------

test('test_orden_nueva_server_error_shows_toast_and_preserves_data', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.route(ORDERS_URL, (route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal server error' }),
      })
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
  })

  await page.goto('/ordenes/nueva')

  await page.getByLabel('Proveedor').fill('Proveedor Error')
  await page.getByLabel('Elegir producto').selectOption('prod-palta')
  await page.getByLabel('Cantidad').fill('5')
  await page.getByLabel('Costo unitario').fill('3.00')

  const submitBtn = page.getByRole('button', { name: /guardar orden/i })
  await submitBtn.click()

  // Toast must appear
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByRole('alert')).toContainText(/No se pudo guardar la orden/i)

  // Data must be preserved — supplier name still visible
  await expect(page.getByLabel('Proveedor')).toHaveValue('Proveedor Error')

  // Still on same page
  await expect(page).toHaveURL('/ordenes/nueva')
})

// ---------------------------------------------------------------------------
// test_orden_nueva_cocinero_redirected — role guard
// A cocinero cannot access /ordenes/nueva.
// ---------------------------------------------------------------------------

test('test_orden_nueva_cocinero_redirected', async ({ page }) => {
  const token = makeTestJwt('cocinero')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)

  await page.goto('/ordenes/nueva')

  // cocinero is redirected to / (home)
  await expect(page).toHaveURL('/')
})

// ---------------------------------------------------------------------------
// test_orden_nueva_admin_can_access — admin has access
// ---------------------------------------------------------------------------

test('test_orden_nueva_admin_can_access', async ({ page }) => {
  await injectAdminToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')

  // Must render the form, not redirect
  await expect(page.getByRole('button', { name: /guardar orden/i })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_orden_nueva_add_product_row
// Clicking "+ agregar producto" adds a second row.
// ---------------------------------------------------------------------------

test('test_orden_nueva_add_product_row', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')

  const addBtn = page.getByRole('button', { name: /agregar producto/i })
  await addBtn.click()

  // Now there should be 2 product selects
  const selects = page.getByLabel('Elegir producto')
  await expect(selects).toHaveCount(2)
})

// ---------------------------------------------------------------------------
// test_add_remove_add_does_not_collide_localids (Fix 2 / QA-ALTO 1)
// Adding, removing, and re-adding must not produce key collisions.
// ---------------------------------------------------------------------------

test('test_add_remove_add_does_not_collide_localids', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  const MOCK_PRODUCTS_WITH_POLLO = [
    { id: 'prod-palta', name: 'PALTA', unit: 'un', low_stock_threshold: null },
    { id: 'prod-pollo', name: 'POLLO', unit: 'kg', low_stock_threshold: null },
  ]

  await page.route('**/api/v1/products', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PRODUCTS_WITH_POLLO),
    })
  })

  let capturedBody: string | null = null
  await page.route('**/api/v1/purchase-orders', (route) => {
    if (route.request().method() === 'POST') {
      capturedBody = route.request().postData()
      route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'new-order-id',
          supplier_name: 'Test',
          created_at: new Date().toISOString(),
          created_by_name: 'Test',
          derived_status: 'open',
          items: [],
          total_ordered: '42.50',
          total_received: '0',
          pending_amount: '42.50',
          partida_count: 0,
        }),
      })
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
  })

  await page.goto('/ordenes/nueva')

  // Step 1: fill in PALTA on the first (pre-existing) row
  await page.getByLabel('Elegir producto').first().selectOption('prod-palta')
  await page.getByLabel('Cantidad').fill('10')
  await page.getByLabel('Costo unitario').fill('1.20')

  // Step 2: remove the first row
  const removeBtn = page.getByRole('button', { name: /Eliminar fila/i })
  // Need a second row first so remove is enabled — add one
  await page.getByRole('button', { name: /agregar producto/i }).click()
  // Now remove the first row (PALTA)
  await removeBtn.first().click()

  // Step 3: only one row remains (the empty one added in step 2)
  await expect(page.getByLabel('Elegir producto')).toHaveCount(1)

  // Step 4: fill in POLLO on the remaining row
  await page.getByLabel('Elegir producto').selectOption('prod-pollo')
  await page.getByLabel('Cantidad').fill('5')
  await page.getByLabel('Costo unitario').fill('8.50')

  // Step 5: fill supplier and submit
  await page.getByLabel('Proveedor').fill('Test')
  await page.getByRole('button', { name: /guardar orden/i }).click()

  await expect(page).toHaveURL('/ordenes', { timeout: 5000 })

  // Step 6: verify POST body includes only POLLO
  expect(capturedBody).not.toBeNull()
  const body = JSON.parse(capturedBody!) as {
    items: Array<{ product_id: string }>
  }
  expect(body.items).toHaveLength(1)
  expect(body.items[0].product_id).toBe('prod-pollo')
})
