import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// Pantalla de precios y descuentos (migracion 0022). La API se mockea: lo que
// se prueba es que la pantalla muestre lista/descuento/final y mande el PATCH
// correcto, no la cuenta del servidor (eso vive en tests/test_pricing_discounts.py).

const PRODUCTS_URL = '**/api/v1/products?flow=sale'
const PROMOTIONS_URL = '**/api/v1/promotions'

const products = [
  {
    id: 'p-1',
    name: 'ENERGY BOWL',
    unit: 'un',
    low_stock_threshold: null,
    is_purchase: false,
    is_sale: true,
    sale_price: '33.00',
    discount_percent: '10.00',
  },
  {
    id: 'p-2',
    name: 'FOCUS BOWL',
    unit: 'un',
    low_stock_threshold: null,
    is_purchase: false,
    is_sale: true,
    sale_price: null,
    discount_percent: null,
  },
]

const promotions = [
  {
    code: 'primera_compra',
    name: 'Descuento de primera compra',
    percent: '15.00',
    first_order_only: true,
    is_active: true,
    updated_at: null,
  },
]

async function injectToken(page: import('@playwright/test').Page, role: 'owner' | 'admin' | 'cocinero') {
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, makeTestJwt(role))
}

async function mockCatalog(page: import('@playwright/test').Page) {
  await page.route(PRODUCTS_URL, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(products) }),
  )
  await page.route(PROMOTIONS_URL, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(promotions),
      })
    }
    return route.continue()
  })
}

test('muestra precio de lista, descuento y precio final por plato', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockCatalog(page)
  await page.goto('/precios')

  await expect(page.getByRole('heading', { name: /PRECIOS Y DESCUENTOS/ })).toBeVisible()
  const row = page.getByRole('row', { name: /ENERGY BOWL/ })
  await expect(row.getByLabel('Precio de ENERGY BOWL')).toHaveValue('33.00')
  await expect(row.getByLabel('Descuento de ENERGY BOWL')).toHaveValue('10.00')
  // 33 - 10 % = 29.70
  await expect(row).toContainText(/29[.,]70/)

  // Sin precio cargado: no hay precio final que mostrar.
  const mudo = page.getByRole('row', { name: /FOCUS BOWL/ })
  await expect(mudo.getByLabel('Precio de FOCUS BOWL')).toHaveValue('')
  await expect(mudo).toContainText('—')
})

test('guardar manda el PATCH de pricing con lo editado', async ({ page }) => {
  await injectToken(page, 'admin')
  await mockCatalog(page)

  let sentBody: unknown = null
  await page.route('**/api/v1/products/p-1/pricing', (route) => {
    sentBody = route.request().postDataJSON()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...products[0], sale_price: '35.00', discount_percent: '20.00' }),
    })
  })

  await page.goto('/precios')
  const row = page.getByRole('row', { name: /ENERGY BOWL/ })
  const save = row.getByRole('button', { name: 'Guardar' })
  // Sin cambios, no hay nada que guardar.
  await expect(save).toBeDisabled()

  await row.getByLabel('Precio de ENERGY BOWL').fill('35')
  await row.getByLabel('Descuento de ENERGY BOWL').fill('20')
  await expect(row).toContainText(/28[.,]00/)
  await save.click()

  await expect(row.getByText('Guardado')).toBeVisible()
  expect(sentBody).toEqual({ sale_price: '35', discount_percent: '20' })
})

test('la promocion se edita y manda el PATCH a /promotions/{code}', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockCatalog(page)

  let sentBody: unknown = null
  await page.route('**/api/v1/promotions/primera_compra', (route) => {
    sentBody = route.request().postDataJSON()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...promotions[0], percent: '20.00', is_active: false }),
    })
  })

  await page.goto('/precios')
  const row = page.getByRole('row', { name: /primera compra/ })
  await expect(row.getByLabel(/Solo primera compra/)).toBeChecked()

  await row.getByLabel(/Porcentaje de/).fill('20')
  await row.getByLabel(/^Activa/).uncheck()
  await row.getByRole('button', { name: 'Guardar' }).click()

  await expect(row.getByText('Guardado')).toBeVisible()
  expect(sentBody).toEqual({ percent: '20', first_order_only: true, is_active: false })
})

test('un error del servidor se muestra en el banner', async ({ page }) => {
  await injectToken(page, 'owner')
  await mockCatalog(page)
  await page.route('**/api/v1/products/p-1/pricing', (route) =>
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({ detail: "Product 'ENERGY BOWL' is not a sale product" }),
    }),
  )

  await page.goto('/precios')
  const row = page.getByRole('row', { name: /ENERGY BOWL/ })
  await row.getByLabel('Descuento de ENERGY BOWL').fill('5')
  await row.getByRole('button', { name: 'Guardar' }).click()

  await expect(page.getByRole('alert')).toContainText('is not a sale product')
})

test('el cocinero no llega a /precios', async ({ page }) => {
  await injectToken(page, 'cocinero')
  await page.goto('/precios')
  await expect(page).toHaveURL('/')
})

test('el tablero del owner y el home del admin llevan a precios', async ({ page }) => {
  await injectToken(page, 'admin')
  await page.goto('/')
  await expect(page.getByRole('button', { name: /^PRECIOS/ })).toContainText('(carta y descuentos)')
  await mockCatalog(page)
  await page.getByRole('button', { name: /^PRECIOS/ }).click()
  await expect(page).toHaveURL('/precios')
})
