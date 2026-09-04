import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// Pantalla de extras y opciones. La API se mockea: lo que se prueba es que la
// pantalla liste los grupos con sus reglas, mande el PATCH de precio, el POST
// de grupo y el PUT de asignacion correctos. La regla de negocio (quien puede
// editar, single => max 1, el duplicado) vive en tests/test_option_groups.py.

const GROUPS_URL = '**/api/v1/option-groups?all=true'
const PRODUCTS_URL = '**/api/v1/products?flow=sale'

const groups = [
  {
    id: 'g-1',
    name: 'Base',
    selection: 'single',
    required: true,
    min_choices: 1,
    max_choices: 1,
    sort_order: 0,
    is_active: true,
    updated_at: null,
    items: [
      { id: 'i-1', name: 'Camote', price: '0.00', product_id: null, sort_order: 0, is_active: true },
      { id: 'i-2', name: 'Quinua', price: '0.00', product_id: null, sort_order: 1, is_active: true },
    ],
  },
  {
    id: 'g-2',
    name: 'Proteína extra',
    selection: 'multiple',
    required: true,
    min_choices: 1,
    max_choices: 2,
    sort_order: 1,
    is_active: true,
    updated_at: null,
    items: [
      {
        id: 'i-3',
        name: 'Filete de pollo',
        price: '7.00',
        product_id: null,
        sort_order: 0,
        is_active: true,
      },
    ],
  },
  {
    id: 'g-3',
    name: 'Adicionales',
    selection: 'multiple',
    required: false,
    min_choices: 0,
    max_choices: 6,
    sort_order: 2,
    is_active: false,
    updated_at: '2026-09-01T12:00:00Z',
    items: [],
  },
]

const products = [
  {
    id: 'p-1',
    name: 'ARMA TU BOWL',
    unit: 'un',
    low_stock_threshold: null,
    is_purchase: false,
    is_sale: true,
    sale_price: '24.90',
    discount_percent: null,
  },
]

async function injectToken(page: import('@playwright/test').Page, role: 'owner' | 'admin' | 'cocinero') {
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, makeTestJwt(role))
}

async function mockApi(page: import('@playwright/test').Page) {
  await page.route(GROUPS_URL, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(groups) }),
  )
  await page.route(PRODUCTS_URL, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(products) }),
  )
  await page.route('**/api/v1/products/p-1/option-groups', (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ group_id: 'g-1', name: 'Base', sort_order: 0 }]),
    })
  })
}

test('lista los grupos con sus reglas y marca los apagados', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockApi(page)
  await page.goto('/opciones')

  await expect(page.getByRole('heading', { name: /EXTRAS Y OPCIONES/ })).toBeVisible()
  await expect(page.getByText(/Las opciones con precio se suman al plato/)).toBeVisible()

  const base = page.getByRole('article', { name: 'Grupo Base' })
  await expect(base).toContainText('Una opción')
  await expect(base).toContainText('Obligatorio')
  await expect(base).toContainText('mín 1 / máx 1')
  await expect(base.getByLabel('Activo — Base')).toBeChecked()
  await expect(base).not.toHaveAttribute('data-inactive', 'true')

  const extra = page.getByRole('article', { name: 'Grupo Proteína extra' })
  await expect(extra).toContainText('Varias')
  await expect(extra).toContainText('mín 1 / máx 2')

  const adicionales = page.getByRole('article', { name: 'Grupo Adicionales' })
  await expect(adicionales).not.toContainText('Obligatorio')
  await expect(adicionales.getByLabel('Activo — Adicionales')).not.toBeChecked()
  await expect(adicionales).toHaveAttribute('data-inactive', 'true')
})

test('abrir un grupo y guardar manda el PATCH de la opción', async ({ page }) => {
  await injectToken(page, 'admin')
  await mockApi(page)

  let sentBody: unknown = null
  await page.route('**/api/v1/option-items/i-3', (route) => {
    sentBody = route.request().postDataJSON()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...groups[1].items[0], price: '9.00' }),
    })
  })

  await page.goto('/opciones')
  const extra = page.getByRole('article', { name: 'Grupo Proteína extra' })
  // Cerrado: la tabla de opciones no esta.
  await expect(extra.getByLabel('Precio de Filete de pollo')).toHaveCount(0)
  await extra.getByRole('button', { name: /Proteína extra/ }).click()

  const priceInput = extra.getByLabel('Precio de Filete de pollo')
  await expect(priceInput).toHaveValue('7.00')
  const row = extra.getByRole('row', { name: /Filete de pollo/ })
  const save = row.getByRole('button', { name: 'Guardar' })
  await expect(save).toBeDisabled()

  await priceInput.fill('9')
  await save.click()

  await expect(row.getByText('Guardado')).toBeVisible()
  expect(sentBody).toEqual({ price: '9', is_active: true })
})

test('agregar una opción manda el POST al grupo', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockApi(page)

  let sentBody: unknown = null
  await page.route('**/api/v1/option-groups/g-2/items', (route) => {
    sentBody = route.request().postDataJSON()
    route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'i-9',
        name: 'Tilapia',
        price: '8.00',
        product_id: null,
        sort_order: 0,
        is_active: true,
      }),
    })
  })

  await page.goto('/opciones')
  const extra = page.getByRole('article', { name: 'Grupo Proteína extra' })
  await extra.getByRole('button', { name: /Proteína extra/ }).click()

  const add = extra.getByRole('button', { name: 'Agregar' })
  await expect(add).toBeDisabled()
  await extra.getByLabel('Nueva opción en Proteína extra', { exact: true }).fill('Tilapia')
  await extra.getByLabel('Precio de la nueva opción en Proteína extra').fill('8')
  await add.click()

  await expect(extra.getByLabel('Nueva opción en Proteína extra', { exact: true })).toHaveValue('')
  expect(sentBody).toEqual({ name: 'Tilapia', price: '8' })
})

test('crear un grupo manda el POST con sus reglas', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockApi(page)

  let sentBody: unknown = null
  await page.route('**/api/v1/option-groups', (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    sentBody = route.request().postDataJSON()
    return route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'g-9',
        name: 'Salsa',
        selection: 'multiple',
        required: true,
        min_choices: 1,
        max_choices: 2,
        sort_order: 0,
        is_active: true,
        updated_at: null,
        items: [],
      }),
    })
  })

  await page.goto('/opciones')
  const create = page.getByRole('button', { name: 'Crear grupo' })
  await expect(create).toBeDisabled()

  await page.getByLabel('Nombre del nuevo grupo').fill('Salsa')
  await page.getByLabel('Selección del nuevo grupo').selectOption('multiple')
  await page.getByLabel('Obligatorio', { exact: true }).check()
  await page.getByLabel('Máximo del nuevo grupo').fill('2')
  await create.click()

  await expect(page.getByLabel('Nombre del nuevo grupo')).toHaveValue('')
  expect(sentBody).toEqual({ name: 'Salsa', selection: 'multiple', required: true, max_choices: 2 })
})

test('asignar grupos a un plato manda el PUT en orden', async ({ page }) => {
  await injectToken(page, 'admin')
  await mockApi(page)

  let sentBody: unknown = null
  await page.route('**/api/v1/products/p-1/option-groups', (route) => {
    if (route.request().method() !== 'PUT') return route.fallback()
    sentBody = route.request().postDataJSON()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { group_id: 'g-1', name: 'Base', sort_order: 0 },
        { group_id: 'g-2', name: 'Proteína extra', sort_order: 1 },
      ]),
    })
  })

  await page.goto('/opciones')
  const card = page.getByRole('article', { name: 'Opciones de ARMA TU BOWL' })
  await expect(card.getByLabel('Base — ARMA TU BOWL')).toBeChecked()
  await expect(card.getByLabel('Proteína extra — ARMA TU BOWL')).not.toBeChecked()
  // Un grupo apagado no se ofrece para asignar.
  await expect(card.getByLabel('Adicionales — ARMA TU BOWL')).toHaveCount(0)

  const save = card.getByRole('button', { name: 'Guardar' })
  await expect(save).toBeDisabled()
  await card.getByLabel('Proteína extra — ARMA TU BOWL').check()
  await save.click()

  await expect(card.getByText('Guardado')).toBeVisible()
  expect(sentBody).toEqual({ group_ids: ['g-1', 'g-2'] })
})

test('el cocinero no llega a /opciones', async ({ page }) => {
  await injectToken(page, 'cocinero')
  await page.goto('/opciones')
  await expect(page).toHaveURL('/')
})

test('el home del admin lleva a extras', async ({ page }) => {
  await injectToken(page, 'admin')
  await page.goto('/')
  await expect(page.getByRole('button', { name: /^EXTRAS/ })).toContainText('(opciones y adicionales)')
  await mockApi(page)
  await page.getByRole('button', { name: /^EXTRAS/ }).click()
  await expect(page).toHaveURL('/opciones')
})
