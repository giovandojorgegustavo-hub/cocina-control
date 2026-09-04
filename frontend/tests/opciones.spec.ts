import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// Pantalla de extras y opciones, organizada por plato. La API se mockea: lo
// que se prueba es que cada plato liste sus grupos con la regla en palabras,
// que editar una opcion desde el plato mande el PATCH, que agregar o quitar
// un grupo mande el PUT en orden, y que el POST/PATCH de grupo sigan andando
// desde la seccion GRUPOS. La regla de negocio (quien puede editar, single =>
// max 1, el duplicado) vive en tests/test_option_groups.py.

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
  {
    id: 'p-2',
    name: 'WRAP',
    unit: 'un',
    low_stock_threshold: null,
    is_purchase: false,
    is_sale: true,
    sale_price: '19.90',
    discount_percent: '10',
  },
  // Sin precio: no sale en la carta, no tiene sentido armarle opciones.
  {
    id: 'p-3',
    name: 'GASEOSA',
    unit: 'un',
    low_stock_threshold: null,
    is_purchase: false,
    is_sale: true,
    sale_price: null,
    discount_percent: null,
  },
]

const links: Record<string, Array<{ group_id: string; name: string; sort_order: number }>> = {
  'p-1': [{ group_id: 'g-1', name: 'Base', sort_order: 0 }],
  'p-2': [
    { group_id: 'g-1', name: 'Base', sort_order: 0 },
    { group_id: 'g-2', name: 'Proteína extra', sort_order: 1 },
  ],
}

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
  for (const productId of Object.keys(links)) {
    await page.route(`**/api/v1/products/${productId}/option-groups`, (route) => {
      if (route.request().method() !== 'GET') return route.fallback()
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(links[productId]),
      })
    })
  }
}

test('muestra cada plato con sus opciones y la regla en palabras', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockApi(page)
  await page.goto('/opciones')

  await expect(page.getByRole('heading', { name: /EXTRAS Y OPCIONES/ })).toBeVisible()
  await expect(page.getByText(/Lo que el cliente puede elegir o agregar en cada plato/)).toBeVisible()

  // Una tarjeta por plato con precio, con el precio final y el resumen de grupos.
  const bowl = page.getByRole('article', { name: 'Plato ARMA TU BOWL' })
  await expect(bowl).toContainText(/S\/\. 24[.,]90/)
  await expect(bowl).toContainText('Base')
  const wrap = page.getByRole('article', { name: 'Plato WRAP' })
  await expect(wrap).toContainText(/S\/\. 17[.,]91/)
  await expect(wrap).toContainText('Base · Proteína extra')
  await expect(page.getByRole('article', { name: 'Plato GASEOSA' })).toHaveCount(0)

  // Los grupos quedan plegados hasta que el dueno los pide.
  await expect(page.getByRole('article', { name: 'Grupo Base' })).toHaveCount(0)

  // Cerrado: no hay opciones. Abierto: cada grupo con su regla en palabras.
  await expect(wrap.getByLabel('Precio de Camote')).toHaveCount(0)
  await wrap.getByRole('button', { name: /WRAP/ }).click()

  const base = wrap.getByRole('region', { name: 'Base en WRAP' })
  await expect(base).toContainText('Elige 1')
  await expect(base).toContainText('Este grupo se usa en 2 platos; el cambio aplica a todos.')
  // Precio 0 se lee como incluido, no como 0.00.
  await expect(base.getByLabel('Precio de Camote')).toHaveValue('')
  await expect(base.getByLabel('Precio de Camote')).toHaveAttribute('placeholder', 'incluido')

  const extra = wrap.getByRole('region', { name: 'Proteína extra en WRAP' })
  await expect(extra).toContainText('Elige de 1 a 2')
  await expect(extra).not.toContainText('se usa en')

  // GRUPOS: mismas reglas en palabras, el apagado marcado.
  await page.getByRole('button', { name: 'Ver grupos' }).click()
  const baseGroup = page.getByRole('article', { name: 'Grupo Base' })
  await expect(baseGroup).toContainText('Elige 1')
  await expect(baseGroup).toContainText('en 2 platos')
  await expect(baseGroup.getByLabel('Activo — Base')).toBeChecked()

  const adicionales = page.getByRole('article', { name: 'Grupo Adicionales' })
  await expect(adicionales).toContainText('Opcional, hasta 6')
  await expect(adicionales).toContainText('en ningún plato')
  await expect(adicionales.getByLabel('Activo — Adicionales')).not.toBeChecked()
  await expect(adicionales).toHaveAttribute('data-inactive', 'true')
})

test('editar el precio de una opción desde el plato manda el PATCH', async ({ page }) => {
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
  const wrap = page.getByRole('article', { name: 'Plato WRAP' })
  await wrap.getByRole('button', { name: /WRAP/ }).click()
  const extra = wrap.getByRole('region', { name: 'Proteína extra en WRAP' })

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

test('agregar una opción desde el plato manda el POST al grupo', async ({ page }) => {
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
  const wrap = page.getByRole('article', { name: 'Plato WRAP' })
  await wrap.getByRole('button', { name: /WRAP/ }).click()
  const extra = wrap.getByRole('region', { name: 'Proteína extra en WRAP' })

  const add = extra.getByRole('button', { name: 'Agregar', exact: true })
  await expect(add).toBeDisabled()
  await extra.getByLabel('Nueva opción en Proteína extra', { exact: true }).fill('Tilapia')
  await extra.getByLabel('Precio de la nueva opción en Proteína extra').fill('8')
  await add.click()

  await expect(extra.getByLabel('Nueva opción en Proteína extra', { exact: true })).toHaveValue('')
  expect(sentBody).toEqual({ name: 'Tilapia', price: '8' })
})

test('agregar un grupo al plato manda el PUT con el grupo nuevo al final', async ({ page }) => {
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
  const bowl = page.getByRole('article', { name: 'Plato ARMA TU BOWL' })
  await bowl.getByRole('button', { name: /ARMA TU BOWL/ }).click()

  const select = bowl.getByLabel('Agregar grupo a ARMA TU BOWL')
  // Ya asignado y apagado no se ofrecen.
  await expect(select.locator('option', { hasText: 'Base' })).toHaveCount(0)
  await expect(select.locator('option', { hasText: 'Adicionales' })).toHaveCount(0)
  const add = bowl.getByRole('button', { name: 'Agregar grupo' })
  await expect(add).toBeDisabled()

  await select.selectOption('g-2')
  await add.click()

  await expect(select).toHaveValue('')
  expect(sentBody).toEqual({ group_ids: ['g-1', 'g-2'] })
})

test('quitar un grupo del plato manda el PUT sin ese grupo', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockApi(page)

  let sentBody: unknown = null
  await page.route('**/api/v1/products/p-2/option-groups', (route) => {
    if (route.request().method() !== 'PUT') return route.fallback()
    sentBody = route.request().postDataJSON()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ group_id: 'g-2', name: 'Proteína extra', sort_order: 0 }]),
    })
  })

  await page.goto('/opciones')
  const wrap = page.getByRole('article', { name: 'Plato WRAP' })
  await wrap.getByRole('button', { name: /WRAP/ }).click()
  await wrap
    .getByRole('region', { name: 'Base en WRAP' })
    .getByRole('button', { name: 'Quitar de este plato' })
    .click()

  await expect.poll(() => sentBody).toEqual({ group_ids: ['g-2'] })
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
  await expect(page.getByRole('form', { name: 'Nuevo grupo' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Ver grupos' }).click()

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

test('editar las reglas de un grupo manda el PATCH', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockApi(page)

  let sentBody: unknown = null
  await page.route('**/api/v1/option-groups/g-2', (route) => {
    if (route.request().method() !== 'PATCH') return route.fallback()
    sentBody = route.request().postDataJSON()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...groups[1], max_choices: 3 }),
    })
  })

  await page.goto('/opciones')
  await page.getByRole('button', { name: 'Ver grupos' }).click()
  const extra = page.getByRole('article', { name: 'Grupo Proteína extra' })
  await extra.getByRole('button', { name: 'Editar grupo Proteína extra' }).click()

  const form = extra.getByRole('form', { name: 'Editar grupo Proteína extra' })
  await expect(form).toContainText('Elige de 1 a 2')
  await form.getByLabel('Máximo del grupo Proteína extra').fill('3')
  await expect(form).toContainText('Elige de 1 a 3')
  await form.getByRole('button', { name: 'Guardar' }).click()

  await expect(form).toHaveCount(0)
  expect(sentBody).toEqual({
    name: 'Proteína extra',
    selection: 'multiple',
    required: true,
    min_choices: 1,
    max_choices: 3,
  })
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
