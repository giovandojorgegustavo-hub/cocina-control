import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// Pantalla de distritos de reparto. La API se mockea: lo que se prueba es que
// la pantalla liste las zonas (activas y apagadas), mande el PATCH y el POST
// correctos y muestre el 409 en la fila de alta. La regla de negocio (quien
// puede editar, el duplicado por tilde) vive en tests/test_delivery_zones.py.

const ZONES_URL = '**/api/v1/delivery-zones?all=true'

const zones = [
  {
    id: 'z-1',
    district: 'Pueblo Libre',
    fee: '5.00',
    is_active: true,
    updated_at: null,
  },
  {
    id: 'z-2',
    district: 'Barranco',
    fee: '10.00',
    is_active: false,
    updated_at: '2026-09-01T12:00:00Z',
  },
]

async function injectToken(page: import('@playwright/test').Page, role: 'owner' | 'admin' | 'cocinero') {
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, makeTestJwt(role))
}

async function mockZones(page: import('@playwright/test').Page) {
  await page.route(ZONES_URL, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(zones) }),
  )
}

test('lista los distritos con tarifa y marca los apagados', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockZones(page)
  await page.goto('/zonas')

  await expect(page.getByRole('heading', { name: /DISTRITOS DE REPARTO/ })).toBeVisible()
  await expect(page.getByText(/solo cotiza y toma pedidos en los distritos activos/)).toBeVisible()

  const activa = page.getByRole('row', { name: /Pueblo Libre/ })
  await expect(activa.getByLabel('Tarifa de Pueblo Libre')).toHaveValue('5.00')
  await expect(activa.getByLabel(/^Activa/)).toBeChecked()
  await expect(activa).not.toHaveAttribute('data-inactive', 'true')

  const apagada = page.getByRole('row', { name: /Barranco/ })
  await expect(apagada.getByLabel('Tarifa de Barranco')).toHaveValue('10.00')
  await expect(apagada.getByLabel(/^Activa/)).not.toBeChecked()
  await expect(apagada).toHaveAttribute('data-inactive', 'true')
})

test('guardar manda el PATCH con tarifa y estado', async ({ page }) => {
  await injectToken(page, 'admin')
  await mockZones(page)

  let sentBody: unknown = null
  await page.route('**/api/v1/delivery-zones/z-1', (route) => {
    sentBody = route.request().postDataJSON()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...zones[0], fee: '6.50', is_active: false }),
    })
  })

  await page.goto('/zonas')
  const row = page.getByRole('row', { name: /Pueblo Libre/ })
  const save = row.getByRole('button', { name: 'Guardar' })
  // Sin cambios, no hay nada que guardar.
  await expect(save).toBeDisabled()

  await row.getByLabel('Tarifa de Pueblo Libre').fill('6.5')
  await row.getByLabel(/^Activa/).uncheck()
  await save.click()

  await expect(row.getByText('Guardado')).toBeVisible()
  expect(sentBody).toEqual({ fee: '6.5', is_active: false })
})

test('agregar manda el POST y limpia la fila', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockZones(page)

  let sentBody: unknown = null
  await page.route('**/api/v1/delivery-zones', (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    sentBody = route.request().postDataJSON()
    return route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'z-3',
        district: 'Lince',
        fee: '7.00',
        is_active: true,
        updated_at: null,
      }),
    })
  })

  await page.goto('/zonas')
  const add = page.getByRole('button', { name: 'Agregar' })
  await expect(add).toBeDisabled()

  await page.getByLabel('Nuevo distrito', { exact: true }).fill('Lince')
  await page.getByLabel('Tarifa del nuevo distrito').fill('7')
  await add.click()

  await expect(page.getByLabel('Nuevo distrito', { exact: true })).toHaveValue('')
  expect(sentBody).toEqual({ district: 'Lince', fee: '7' })
})

test('un distrito repetido muestra el error en la fila de alta', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockZones(page)
  await page.route('**/api/v1/delivery-zones', (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    return route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({ detail: "Delivery zone for 'Pueblo Libre' already exists" }),
    })
  })

  await page.goto('/zonas')
  await page.getByLabel('Nuevo distrito', { exact: true }).fill('pueblo libre')
  await page.getByLabel('Tarifa del nuevo distrito').fill('5')
  await page.getByRole('button', { name: 'Agregar' }).click()

  await expect(page.getByRole('alert')).toContainText('Ese distrito ya existe')
  // Lo escrito no se pierde: el dueno corrige en lugar de volver a tipear.
  await expect(page.getByLabel('Nuevo distrito', { exact: true })).toHaveValue('pueblo libre')
})

test('el cocinero no llega a /zonas', async ({ page }) => {
  await injectToken(page, 'cocinero')
  await page.goto('/zonas')
  await expect(page).toHaveURL('/')
})

test('el home del admin lleva a distritos', async ({ page }) => {
  await injectToken(page, 'admin')
  await page.goto('/')
  await expect(page.getByRole('button', { name: /^DISTRITOS/ })).toContainText('(reparto y tarifas)')
  await mockZones(page)
  await page.getByRole('button', { name: /^DISTRITOS/ }).click()
  await expect(page).toHaveURL('/zonas')
})
