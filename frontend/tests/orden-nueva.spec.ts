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

// Combobox helper: click the product input and pick an option from the list
async function pickProduct(
  page: import('@playwright/test').Page,
  name: string | RegExp,
  nth = 0,
) {
  await page.getByLabel('Elegir producto').nth(nth).click()
  await page.getByRole('option', { name }).click()
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

  // Select product PALTA via combobox
  await pickProduct(page, /PALTA/)

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
  await pickProduct(page, /PALTA/)
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
  await pickProduct(page, /PALTA/)
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

  // Now there should be 2 product comboboxes
  const combos = page.getByLabel('Elegir producto')
  await expect(combos).toHaveCount(2)
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
  await pickProduct(page, /PALTA/, 0)
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
  await pickProduct(page, /POLLO/)
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

// ---------------------------------------------------------------------------
// test_enter_crea_producto_directo (issue #130)
// Typing a new name and pressing Enter triggers the create option without
// the mouse, and focus jumps to the unit selector.
// ---------------------------------------------------------------------------

test('test_enter_crea_producto_directo', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')

  const combo = page.getByLabel('Elegir producto')
  await combo.fill('papas fritas')
  await combo.press('Enter')

  // Row switched to NEW product and focus is on the unit selector
  await expect(page.getByText('nuevo', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Unidad del producto')).toBeFocused()
})

// ---------------------------------------------------------------------------
// test_enter_selecciona_primer_match (issue #130)
// Enter with matches picks the highlighted (first) product.
// ---------------------------------------------------------------------------

test('test_enter_selecciona_primer_match', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')

  const combo = page.getByLabel('Elegir producto')
  await combo.fill('pal')
  await combo.press('Enter')

  await expect(combo).toHaveValue('PALTA')
  await expect(page.getByLabel('Unidad')).toHaveValue('un')
})

// ---------------------------------------------------------------------------
// test_flechas_navegan_opciones (issue #130)
// ArrowDown moves the highlight; Enter picks the highlighted option.
// ---------------------------------------------------------------------------

test('test_flechas_navegan_opciones', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')

  const combo = page.getByLabel('Elegir producto')
  await combo.click()
  // dropdown open with all products: PALTA, TOMATE, CEBOLLA
  await combo.press('ArrowDown')
  await combo.press('Enter')

  await expect(combo).toHaveValue('TOMATE')
})

// ---------------------------------------------------------------------------
// test_escape_cierra_dropdown (issue #130)
// ---------------------------------------------------------------------------

test('test_escape_cierra_dropdown', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')

  const combo = page.getByLabel('Elegir producto')
  await combo.fill('pal')
  await expect(page.getByRole('listbox')).toBeVisible()
  await combo.press('Escape')
  await expect(page.getByRole('listbox')).toHaveCount(0)
})

// ---------------------------------------------------------------------------
// test_costo_total_deriva_unitario (issue #131)
// The user can type the line TOTAL; the unit cost is derived (total / qty)
// and the order still posts unit_cost.
// ---------------------------------------------------------------------------

test('test_costo_total_deriva_unitario', async ({ page }) => {
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
          supplier_name: 'Test',
          created_at: new Date().toISOString(),
          created_by_name: 'Test',
          derived_status: 'open',
          items: [],
          total_ordered: '10.00',
          total_received: '0',
          pending_amount: '10.00',
          partida_count: 0,
        }),
      })
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
  })

  await page.goto('/ordenes/nueva')

  await page.getByLabel('Proveedor').fill('Test')
  await pickProduct(page, /PALTA/)
  await page.getByLabel('Cantidad').fill('4')

  // Type the TOTAL — the unit cost is derived
  await page.getByLabel('Costo total').fill('10')
  await expect(page.getByLabel('Costo unitario')).toHaveValue('2.50')

  await page.getByRole('button', { name: /guardar orden/i }).click()
  await expect(page).toHaveURL('/ordenes', { timeout: 5000 })

  const body = JSON.parse(postBodies[0]) as {
    items: Array<{ expected_qty: number; unit_cost: number }>
  }
  expect(body.items[0].unit_cost).toBe(2.5)
  expect(body.items[0].expected_qty).toBe(4)
})

// ---------------------------------------------------------------------------
// test_costo_unitario_deriva_total (issue #131)
// Typing the unit cost fills the total (qty x unit), as before but visible.
// ---------------------------------------------------------------------------

test('test_costo_unitario_deriva_total', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')

  await pickProduct(page, /PALTA/)
  await page.getByLabel('Cantidad').fill('3')
  await page.getByLabel('Costo unitario').fill('1.20')

  await expect(page.getByLabel('Costo total')).toHaveValue('3.60')
})

// ---------------------------------------------------------------------------
// test_cambio_cantidad_respeta_ultimo_costo_editado (issue #131)
// If the total was the last edited field, changing qty re-derives the UNIT
// cost (total stays); if the unit was last edited, the total re-derives.
// ---------------------------------------------------------------------------

test('test_cambio_cantidad_respeta_ultimo_costo_editado', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')
  await pickProduct(page, /PALTA/)

  // Last edited: TOTAL (10) with qty 4 -> unit 2.50
  await page.getByLabel('Cantidad').fill('4')
  await page.getByLabel('Costo total').fill('10')
  await expect(page.getByLabel('Costo unitario')).toHaveValue('2.50')

  // Change qty to 5 -> total is the source: unit re-derives to 2.00
  await page.getByLabel('Cantidad').fill('5')
  await expect(page.getByLabel('Costo unitario')).toHaveValue('2.00')
  await expect(page.getByLabel('Costo total')).toHaveValue('10')

  // Now edit the UNIT cost (3) -> total re-derives to 15.00
  await page.getByLabel('Costo unitario').fill('3')
  await expect(page.getByLabel('Costo total')).toHaveValue('15.00')

  // Change qty to 2 -> unit is the source now: total re-derives to 6.00
  await page.getByLabel('Cantidad').fill('2')
  await expect(page.getByLabel('Costo total')).toHaveValue('6.00')
})

// ---------------------------------------------------------------------------
// test_combobox_sugiere_parecidos_antes_de_crear (issue #126)
// Typing a partial name shows catalog matches AND the create option.
// ---------------------------------------------------------------------------

test('test_combobox_sugiere_parecidos_antes_de_crear', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')

  await page.getByLabel('Elegir producto').fill('pal')

  // Similar existing product is suggested first
  await expect(page.getByRole('option', { name: /PALTA/ })).toBeVisible()
  // Create option appears (no exact match for "pal")
  await expect(page.getByRole('option', { name: /crear "pal"/ })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_combobox_no_ofrece_crear_con_match_exacto (issue #126)
// If the typed name matches an existing product exactly (case-insensitive),
// the create option must NOT appear — anti-duplicados.
// ---------------------------------------------------------------------------

test('test_combobox_no_ofrece_crear_con_match_exacto', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  await page.goto('/ordenes/nueva')

  await page.getByLabel('Elegir producto').fill('palta')

  await expect(page.getByRole('option', { name: /PALTA/ })).toBeVisible()
  await expect(page.getByRole('option', { name: /crear/ })).toHaveCount(0)
})

// ---------------------------------------------------------------------------
// test_crear_producto_inline_happy_path (issue #126)
// Owner types a new product, picks "crear", chooses the unit, and on submit
// the product is created first (POST /products) and the order references it.
// ---------------------------------------------------------------------------

test('test_crear_producto_inline_happy_path', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  const productPostBodies: string[] = []
  await page.route(PRODUCTS_URL, (route) => {
    if (route.request().method() === 'POST') {
      productPostBodies.push(route.request().postData() ?? '')
      route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'prod-papas-fritas',
          name: 'PAPAS FRITAS',
          unit: 'kg',
          low_stock_threshold: null,
          is_active: true,
        }),
      })
    } else {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PRODUCTS),
      })
    }
  })

  const orderPostBodies: string[] = []
  await page.route(ORDERS_URL, (route) => {
    if (route.request().method() === 'POST') {
      orderPostBodies.push(route.request().postData() ?? '')
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
          total_ordered: '13.50',
          total_received: '0',
          pending_amount: '13.50',
          partida_count: 0,
        }),
      })
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
  })

  await page.goto('/ordenes/nueva')

  await page.getByLabel('Proveedor').fill('Verduleria Test')

  // Type a product that does not exist and pick the create option
  await page.getByLabel('Elegir producto').fill('papas fritas')
  await page.getByRole('option', { name: /crear "papas fritas"/ }).click()

  // The row shows the NUEVO badge and the unit selector
  await expect(page.getByText('nuevo', { exact: true })).toBeVisible()
  const unitSelect = page.getByLabel('Unidad del producto')
  await expect(unitSelect).toBeVisible()

  // Without unit the submit stays disabled
  await page.getByLabel('Cantidad').fill('3')
  await page.getByLabel('Costo unitario').fill('4.50')
  const submitBtn = page.getByRole('button', { name: /guardar orden/i })
  await expect(submitBtn).toBeDisabled()

  // Choose the unit — the product's catalog unit
  await unitSelect.selectOption('kg')
  await expect(submitBtn).toBeEnabled()

  await submitBtn.click()

  await expect(page).toHaveURL('/ordenes', { timeout: 5000 })

  // POST /products was called with the typed name + chosen unit
  expect(productPostBodies).toHaveLength(1)
  const productBody = JSON.parse(productPostBodies[0]) as { name: string; unit: string }
  expect(productBody.name).toBe('papas fritas')
  expect(productBody.unit).toBe('kg')

  // The order references the freshly created product id
  expect(orderPostBodies).toHaveLength(1)
  const orderBody = JSON.parse(orderPostBodies[0]) as {
    items: Array<{ product_id: string; expected_qty: number; unit_cost: number }>
  }
  expect(orderBody.items).toHaveLength(1)
  expect(orderBody.items[0].product_id).toBe('prod-papas-fritas')
  expect(orderBody.items[0].expected_qty).toBe(3)
  expect(orderBody.items[0].unit_cost).toBe(4.5)
})

// ---------------------------------------------------------------------------
// test_crear_producto_409_recupera_existente (issue #126)
// If another user created the same product concurrently (POST returns 409),
// the flow recovers the existing product by name and the order uses ITS id
// and ITS unit (la unidad la define quien creo el producto primero).
// ---------------------------------------------------------------------------

test('test_crear_producto_409_recupera_existente', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  const PRODUCTS_AFTER_CONFLICT = [
    ...MOCK_PRODUCTS,
    { id: 'prod-papas-ajeno', name: 'PAPAS FRITAS', unit: 'un', low_stock_threshold: null },
  ]

  let productsPosted = 0
  let productsFetches = 0
  await page.route(PRODUCTS_URL, (route) => {
    if (route.request().method() === 'POST') {
      productsPosted += 1
      route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Product name already exists' }),
      })
    } else {
      productsFetches += 1
      // first fetch: catalog without the product; later fetches include it
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(productsFetches === 1 ? MOCK_PRODUCTS : PRODUCTS_AFTER_CONFLICT),
      })
    }
  })

  const orderPostBodies: string[] = []
  await page.route(ORDERS_URL, (route) => {
    if (route.request().method() === 'POST') {
      orderPostBodies.push(route.request().postData() ?? '')
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
          total_ordered: '13.50',
          total_received: '0',
          pending_amount: '13.50',
          partida_count: 0,
        }),
      })
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
  })

  await page.goto('/ordenes/nueva')

  await page.getByLabel('Proveedor').fill('Test')
  await page.getByLabel('Elegir producto').fill('papas fritas')
  await page.getByRole('option', { name: /crear "papas fritas"/ }).click()
  await page.getByLabel('Unidad del producto').selectOption('kg')
  await page.getByLabel('Cantidad').fill('3')
  await page.getByLabel('Costo unitario').fill('4.50')

  await page.getByRole('button', { name: /guardar orden/i }).click()

  // The flow recovers: order is created with the EXISTING product id
  await expect(page).toHaveURL('/ordenes', { timeout: 5000 })
  expect(productsPosted).toBe(1)
  expect(orderPostBodies).toHaveLength(1)
  const orderBody = JSON.parse(orderPostBodies[0]) as {
    items: Array<{ product_id: string }>
  }
  expect(orderBody.items[0].product_id).toBe('prod-papas-ajeno')
})

// ---------------------------------------------------------------------------
// test_crear_producto_error_preserva_datos (issue #126)
// If POST /products fails, the order is NOT sent and the data is preserved.
// ---------------------------------------------------------------------------

test('test_crear_producto_error_preserva_datos', async ({ page }) => {
  await injectOwnerToken(page)
  await setupMocks(page)

  let orderPosted = false
  await page.route(ORDERS_URL, (route) => {
    if (route.request().method() === 'POST') {
      orderPosted = true
      route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
  })

  await page.route(PRODUCTS_URL, (route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal server error' }),
      })
    } else {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PRODUCTS),
      })
    }
  })

  await page.goto('/ordenes/nueva')

  await page.getByLabel('Proveedor').fill('Proveedor Error')
  await page.getByLabel('Elegir producto').fill('papas fritas')
  await page.getByRole('option', { name: /crear "papas fritas"/ }).click()
  await page.getByLabel('Unidad del producto').selectOption('kg')
  await page.getByLabel('Cantidad').fill('3')
  await page.getByLabel('Costo unitario').fill('4.50')

  await page.getByRole('button', { name: /guardar orden/i }).click()

  // Toast about the failed product creation
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByRole('alert')).toContainText(/No se pudo crear un producto/i)

  // The order must NOT have been posted
  expect(orderPosted).toBe(false)

  // Data preserved: still on the page, supplier intact, NUEVO row intact
  await expect(page).toHaveURL('/ordenes/nueva')
  await expect(page.getByLabel('Proveedor')).toHaveValue('Proveedor Error')
  await expect(page.getByText('nuevo', { exact: true })).toBeVisible()
})
