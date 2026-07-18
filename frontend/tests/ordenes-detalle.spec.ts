import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const ORDER_ID = 'order-detalle-1'

function detailBody(overrides: Record<string, unknown> = {}) {
  return JSON.stringify({
    id: ORDER_ID,
    supplier_name: 'VERDULERIA NUÑEZ',
    created_at: new Date().toISOString(),
    created_by_name: 'Giovando',
    derived_status: 'open',
    items: [
      {
        id: 'line-1',
        product_id: 'prod-palta',
        product_name: 'PALTA',
        unit: 'kg',
        expected_qty: '10',
        unit_cost: '2.00',
        received_qty: '0',
        pending_qty: '10',
        line_total: '20.00',
      },
      {
        id: 'line-2',
        product_id: 'prod-tomate',
        product_name: 'TOMATE',
        unit: 'kg',
        expected_qty: '5',
        unit_cost: '1.00',
        received_qty: '0',
        pending_qty: '5',
        line_total: '5.00',
      },
    ],
    total_ordered: '25.00',
    total_received: '0',
    pending_amount: '25.00',
    partida_count: 0,
    ...overrides,
  })
}

async function injectOwnerToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('owner')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

async function mockDetail(
  page: import('@playwright/test').Page,
  overrides: Record<string, unknown> = {},
) {
  await page.route(`**/api/v1/purchase-orders/${ORDER_ID}`, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({ status: 200, contentType: 'application/json', body: detailBody(overrides) })
    } else {
      route.continue()
    }
  })
  // list (para el redirect post-anular) y pending
  await page.route('**/api/v1/purchase-orders?*', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })
}

// ---------------------------------------------------------------------------
// test_detalle_editable_muestra_acciones (issue #101)
// ---------------------------------------------------------------------------

test('test_detalle_editable_muestra_acciones', async ({ page }) => {
  await injectOwnerToken(page)
  await mockDetail(page)

  await page.goto(`/ordenes/${ORDER_ID}`)

  await expect(page.getByText('VERDULERIA NUÑEZ')).toBeVisible()
  await expect(page.getByText('ABIERTA')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Editar PALTA' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Quitar PALTA' })).toBeVisible()
  await expect(page.getByRole('button', { name: /anular orden/i })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_editar_linea_manda_patch (issue #101)
// ---------------------------------------------------------------------------

test('test_editar_linea_manda_patch', async ({ page }) => {
  await injectOwnerToken(page)
  await mockDetail(page)

  const patched: string[] = []
  await page.route(`**/api/v1/purchase-orders/${ORDER_ID}/items/line-1`, (route) => {
    patched.push(route.request().postData() ?? '')
    route.fulfill({ status: 200, contentType: 'application/json', body: detailBody() })
  })

  await page.goto(`/ordenes/${ORDER_ID}`)

  await page.getByRole('button', { name: 'Editar PALTA' }).click()
  await page.getByLabel('Cantidad de PALTA').fill('8')
  await page.getByLabel('Costo de PALTA').fill('3')
  await page.getByLabel('Motivo del cambio de PALTA').fill('factura real')
  await page.getByRole('button', { name: /guardar cambio/i }).click()

  await expect.poll(() => patched.length).toBe(1)
  const body = JSON.parse(patched[0]) as {
    expected_qty: number
    unit_cost: number
    reason: string
  }
  expect(body.expected_qty).toBe(8)
  expect(body.unit_cost).toBe(3)
  expect(body.reason).toBe('factura real')
})

// ---------------------------------------------------------------------------
// test_quitar_linea_con_confirmacion (issue #101)
// ---------------------------------------------------------------------------

test('test_quitar_linea_con_confirmacion', async ({ page }) => {
  await injectOwnerToken(page)
  await mockDetail(page)

  let removed = 0
  await page.route(`**/api/v1/purchase-orders/${ORDER_ID}/items/line-2/remove`, (route) => {
    removed += 1
    route.fulfill({ status: 200, contentType: 'application/json', body: detailBody() })
  })

  await page.goto(`/ordenes/${ORDER_ID}`)

  await page.getByRole('button', { name: 'Quitar TOMATE' }).click()
  await page.getByRole('button', { name: 'Confirmar quitar TOMATE' }).click()

  await expect.poll(() => removed).toBe(1)
})

// ---------------------------------------------------------------------------
// test_anular_exige_motivo_y_navega (issue #101)
// ---------------------------------------------------------------------------

test('test_anular_exige_motivo_y_navega', async ({ page }) => {
  await injectOwnerToken(page)
  await mockDetail(page)

  const annulBodies: string[] = []
  await page.route(`**/api/v1/purchase-orders/${ORDER_ID}/annul`, (route) => {
    annulBodies.push(route.request().postData() ?? '')
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: detailBody({ derived_status: 'annulled' }),
    })
  })

  await page.goto(`/ordenes/${ORDER_ID}`)

  await page.getByRole('button', { name: /anular orden/i }).click()
  // sin motivo el boton queda deshabilitado
  const confirmBtn = page.getByRole('button', { name: /^anular orden$/i }).last()
  await expect(confirmBtn).toBeDisabled()

  await page.getByLabel('Motivo de anulacion').fill('el proveedor cancelo')
  await confirmBtn.click()

  await expect(page).toHaveURL('/ordenes', { timeout: 5000 })
  expect(JSON.parse(annulBodies[0]).reason).toBe('el proveedor cancelo')
})

// ---------------------------------------------------------------------------
// test_con_partidas_no_se_edita (issue #101 — regla del dueño)
// ---------------------------------------------------------------------------

test('test_con_partidas_no_se_edita', async ({ page }) => {
  await injectOwnerToken(page)
  await mockDetail(page, { partida_count: 2 })

  await page.goto(`/ordenes/${ORDER_ID}`)

  await expect(page.getByText('VERDULERIA NUÑEZ')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Editar PALTA' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Quitar PALTA' })).toHaveCount(0)
  await expect(page.getByText(/ya tiene recepciones/i)).toBeVisible()
  // anular sigue disponible
  await expect(page.getByRole('button', { name: /anular orden/i })).toBeVisible()
})
