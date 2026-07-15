import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ORDER_ID = 'order-abc'
const ITEM_PALTA = 'item-palta-id'
const ITEM_CEBOLLA = 'item-cebolla-id'

const DRAFT_URL = `**/api/v1/purchase-orders/${ORDER_ID}/partida-draft`
const PARTIDAS_URL = `**/api/v1/purchase-orders/${ORDER_ID}/partidas`

function makeDraft(itemOverrides?: Partial<{
  paltaPendingQty: string
  cebollaPendingQty: string
}>) {
  return {
    order_id: ORDER_ID,
    supplier_name: 'VERDULERIA NUNEZ',
    partida_number: 2,
    items: [
      {
        purchase_order_item_id: ITEM_PALTA,
        product_id: 'prod-palta',
        product_name: 'PALTA',
        unit: 'un',
        pending_qty: itemOverrides?.paltaPendingQty ?? '12',
        already_received: '0',
      },
      {
        purchase_order_item_id: ITEM_CEBOLLA,
        product_id: 'prod-cebolla',
        product_name: 'CEBOLLA',
        unit: 'kg',
        pending_qty: itemOverrides?.cebollaPendingQty ?? '10',
        already_received: '5',
      },
    ],
  }
}

async function injectCociToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('cocinero')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

async function goToDraft(page: import('@playwright/test').Page) {
  await page.goto(`/entradas/${ORDER_ID}`)
}

// ---------------------------------------------------------------------------
// test_verificacion_partida_happy_path
// Confirm all items via "OK — llego asi" and validate — overlay appears.
// ---------------------------------------------------------------------------

test('test_verificacion_partida_happy_path', async ({ page }) => {
  await injectCociToken(page)

  await page.route(DRAFT_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeDraft()),
    })
  })

  const validateBodies: string[] = []
  await page.route(PARTIDAS_URL, (route) => {
    validateBodies.push(route.request().postData() ?? '')
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        delivery_id: 'del-1',
        partida_number: 2,
        order_id: ORDER_ID,
        order_status: 'partially_received',
      }),
    })
  })

  await goToDraft(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Validate button disabled initially
  const validateBtn = page.getByRole('button', { name: /validar partida/i })
  await expect(validateBtn).toBeDisabled()
  await expect(validateBtn).toContainText('0/2')

  // Confirm PALTA
  await page.getByRole('button', { name: /Confirmar PALTA/i }).click()
  await expect(page.getByLabel('Confirmado').first()).toBeVisible()

  // Still disabled (CEBOLLA pending)
  await expect(validateBtn).toBeDisabled()

  // Confirm CEBOLLA
  await page.getByRole('button', { name: /Confirmar CEBOLLA/i }).click()

  // Now enabled
  await expect(validateBtn).toBeEnabled()
  await validateBtn.click()

  // Overlay appears — PARTIDA REGISTRADA (not closed)
  await expect(page.getByText('PARTIDA REGISTRADA')).toBeVisible()
  await expect(page.getByText(/VERDULERIA NUNEZ/)).toBeVisible()
  await expect(page.getByText(/stock actualizado/i)).toBeVisible()

  // Dismiss
  await page.getByRole('button', { name: /listo/i }).click()
  await expect(page).toHaveURL('/entradas')

  // Verify the POST body contains both items
  expect(validateBodies.length).toBeGreaterThan(0)
  const body = JSON.parse(validateBodies[0]) as { items: Array<{ purchase_order_item_id: string; received_qty: number }> }
  expect(body.items).toHaveLength(2)
  const pallaItem = body.items.find((i) => i.purchase_order_item_id === ITEM_PALTA)
  expect(pallaItem?.received_qty).toBe(12)
})

// ---------------------------------------------------------------------------
// test_verificacion_partida_edit_qty
// Open edit modal, type different qty, submit — POST sends the new value.
// ---------------------------------------------------------------------------

test('test_verificacion_partida_edit_qty', async ({ page }) => {
  await injectCociToken(page)

  await page.route(DRAFT_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeDraft()),
    })
  })

  const validateBodies: string[] = []
  await page.route(PARTIDAS_URL, (route) => {
    validateBodies.push(route.request().postData() ?? '')
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        delivery_id: 'del-1',
        partida_number: 2,
        order_id: ORDER_ID,
        order_status: 'open',
      }),
    })
  })

  await goToDraft(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Open edit modal for PALTA
  await page.getByRole('button', { name: /Editar cantidad de PALTA/i }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  // Change quantity to 8
  await page.getByLabel('Cantidad recibida').fill('8')
  await page.getByRole('button', { name: /OK y siguiente/i }).click()

  // Modal closes, PALTA is confirmed with 8 un
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByLabel('Confirmado').first()).toBeVisible()

  // Confirm CEBOLLA
  await page.getByRole('button', { name: /Confirmar CEBOLLA/i }).click()

  // Validate
  const validateBtn = page.getByRole('button', { name: /validar partida/i })
  await expect(validateBtn).toBeEnabled()
  await validateBtn.click()

  expect(validateBodies.length).toBeGreaterThan(0)
  const body = JSON.parse(validateBodies[0]) as { items: Array<{ purchase_order_item_id: string; received_qty: number }> }
  const pallaItem = body.items.find((i) => i.purchase_order_item_id === ITEM_PALTA)
  expect(pallaItem?.received_qty).toBe(8)
})

// ---------------------------------------------------------------------------
// test_verificacion_partida_order_closed_overlay
// When order_status is 'closed', overlay says ORDEN COMPLETA.
// ---------------------------------------------------------------------------

test('test_verificacion_partida_order_closed_overlay', async ({ page }) => {
  await injectCociToken(page)

  await page.route(DRAFT_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeDraft()),
    })
  })

  await page.route(PARTIDAS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        delivery_id: 'del-1',
        partida_number: 1,
        order_id: ORDER_ID,
        order_status: 'closed',
      }),
    })
  })

  await goToDraft(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Confirm both
  await page.getByRole('button', { name: /Confirmar PALTA/i }).click()
  await page.getByRole('button', { name: /Confirmar CEBOLLA/i }).click()

  await page.getByRole('button', { name: /validar partida/i }).click()

  // Overlay must say ORDEN COMPLETA
  await expect(page.getByText('ORDEN COMPLETA')).toBeVisible()
  await expect(page.getByText(/todo llego/i)).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_verificacion_partida_server_error_shows_toast_and_keeps_state
// When POST /partidas returns 500, toast appears and confirmations are NOT lost.
// ---------------------------------------------------------------------------

test('test_verificacion_partida_server_error_shows_toast_and_keeps_state', async ({ page }) => {
  await injectCociToken(page)

  await page.route(DRAFT_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeDraft()),
    })
  })

  await page.route(PARTIDAS_URL, (route) => {
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal server error' }),
    })
  })

  await goToDraft(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Confirm both
  await page.getByRole('button', { name: /Confirmar PALTA/i }).click()
  await page.getByRole('button', { name: /Confirmar CEBOLLA/i }).click()

  // Validate — will fail
  await page.getByRole('button', { name: /validar partida/i }).click()

  // Toast must appear
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByRole('alert')).toContainText(/No se pudo registrar/i)

  // Items must still be confirmed (local state preserved)
  const confirmed = page.getByLabel('Confirmado')
  await expect(confirmed).toHaveCount(2)
})

// ---------------------------------------------------------------------------
// test_verificacion_partida_no_monetary_fields — CRITICAL rule-of-gold
// ---------------------------------------------------------------------------

test('test_verificacion_partida_no_monetary_fields', async ({ page }) => {
  await injectCociToken(page)

  await page.route(DRAFT_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeDraft()),
    })
  })

  await goToDraft(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Must NOT show any monetary amount
  await expect(page.locator('body')).not.toContainText('S/.')
})

// ---------------------------------------------------------------------------
// test_verificacion_partida_409_on_draft_shows_toast_and_redirects
// If draft returns 409 (order no longer accepts partidas), show toast and go back.
// ---------------------------------------------------------------------------

test('test_verificacion_partida_409_on_draft_shows_toast_and_redirects', async ({ page }) => {
  await injectCociToken(page)

  await page.route(DRAFT_URL, (route) => {
    route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Order is closed' }),
    })
  })

  // Mock pending to avoid crash when redirecting back
  await page.route('**/api/v1/purchase-orders/pending', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await goToDraft(page)

  // Toast must appear
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByRole('alert')).toContainText(/ya no acepta partidas/i)

  // Must redirect to /entradas
  await expect(page).toHaveURL('/entradas', { timeout: 3000 })
})

// ---------------------------------------------------------------------------
// test_verificacion_partida_double_tap_validate_single_request
// Double tap on "validar partida" fires only one POST.
// ---------------------------------------------------------------------------

test('test_verificacion_partida_double_tap_validate_single_request', async ({ page }) => {
  await injectCociToken(page)

  await page.route(DRAFT_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeDraft()),
    })
  })

  const validateRequests: string[] = []
  await page.route(PARTIDAS_URL, async (route) => {
    validateRequests.push(route.request().method())
    await new Promise((r) => setTimeout(r, 200))
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        delivery_id: 'del-1',
        partida_number: 2,
        order_id: ORDER_ID,
        order_status: 'partially_received',
      }),
    })
  })

  await goToDraft(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Confirm both items
  await page.getByRole('button', { name: /Confirmar PALTA/i }).click()
  await page.getByRole('button', { name: /Confirmar CEBOLLA/i }).click()

  const validateBtn = page.getByRole('button', { name: /validar partida/i })
  await expect(validateBtn).toBeEnabled()

  // Double-tap in the same JS tick
  await page.evaluate(() => {
    const el = document.querySelector('[aria-label*="Validar partida"]') as HTMLButtonElement | null
    if (el) { el.click(); el.click() }
  })

  await expect(page.getByText('PARTIDA REGISTRADA')).toBeVisible({ timeout: 3000 })

  // Only one request must have fired
  expect(validateRequests.length).toBe(1)
})
