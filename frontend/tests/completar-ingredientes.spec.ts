/**
 * Tests para la captura de ingredientes en /pedidos/:id/completar.
 *
 * Lo que estos tests protegen es el cuerpo que sale hacia el backend: es el
 * mismo endpoint que usa el asistente de WhatsApp, asi que una regresion aca
 * rompe los dos caminos a la vez.
 */
import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const PRODUCTS_URL = '**/api/v1/products*'
const ORDER_URL = '**/api/v1/delivery-orders/*'
const COMPLETE_URL = '**/api/v1/delivery-orders/*/complete'
const PHOTO_URL = '**/api/v1/delivery-orders/*/photo'

const ORDER_ID = 'order-ingredientes-1'

const MOCK_ORDER = {
  id: ORDER_ID,
  status: 'pending',
  photo_at: '2020-01-01T23:42:00Z',
  photo_by: 'user-1',
  completed_at: null,
  completed_by: null,
  items: [],
}

const BOWL = {
  id: 'prod-bowl',
  name: 'ARMA TU BOWL',
  unit: 'un',
  low_stock_threshold: null,
  is_purchase: false,
  is_sale: true,
}
const LECHUGA = {
  id: 'prod-lechuga',
  name: 'LECHUGA CRESPA',
  unit: 'un',
  low_stock_threshold: null,
  is_purchase: true,
  is_sale: false,
}
const PALTA = {
  id: 'prod-palta',
  name: 'PALTA',
  unit: 'kg',
  low_stock_threshold: null,
  is_purchase: true,
  is_sale: false,
}

const MOCK_PRODUCTS = [BOWL, LECHUGA, PALTA]

type Page = import('@playwright/test').Page

async function injectOperatorToken(page: Page) {
  const token = makeTestJwt('operator')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

/** Devuelve un getter del ultimo cuerpo POSTeado a /complete. */
async function setupMocks(page: Page): Promise<() => unknown> {
  let lastBody: unknown = null

  await page.route(COMPLETE_URL, (route) => {
    lastBody = route.request().postDataJSON()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...MOCK_ORDER, status: 'completed' }),
    })
  })
  await page.route(ORDER_URL, (route) => {
    const url = route.request().url()
    if (url.endsWith(ORDER_ID)) {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_ORDER),
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
  await page.route(PHOTO_URL, (route) => {
    route.fulfill({ status: 404, body: '' })
  })

  return () => lastBody
}

async function abrirYSeleccionarBowl(page: Page) {
  await page.goto(`/pedidos/${ORDER_ID}/completar`)
  await page.getByRole('button', { name: /ARMA TU BOWL/ }).first().click()
}

// ---------------------------------------------------------------------------

test('el panel de ingredientes aparece recien al seleccionar un plato', async ({ page }) => {
  await injectOperatorToken(page)
  await setupMocks(page)
  await page.goto(`/pedidos/${ORDER_ID}/completar`)

  await expect(page.getByTestId(`ingredientes-${BOWL.id}`)).toHaveCount(0)

  await page.getByRole('button', { name: /ARMA TU BOWL/ }).first().click()

  await expect(page.getByTestId(`ingredientes-${BOWL.id}`)).toBeVisible()
})

test('los ingredientes elegidos viajan en el cuerpo del complete', async ({ page }) => {
  await injectOperatorToken(page)
  const getBody = await setupMocks(page)
  await abrirYSeleccionarBowl(page)

  const panel = page.getByTestId(`ingredientes-${BOWL.id}`)
  await panel.getByRole('button', { name: /LECHUGA CRESPA/ }).click()
  await panel.getByRole('button', { name: /^PALTA/ }).click()

  await page.getByTestId('terminar-pedido').click()
  await expect(page.getByTestId('terminado-view')).toBeVisible()

  const body = getBody() as { items: Array<{ ingredients?: Array<Record<string, string>> }> }
  expect(body.items).toHaveLength(1)
  const enviados = body.items[0].ingredients ?? []
  expect(enviados.map((i) => i.ingredient_id).sort()).toEqual(
    [LECHUGA.id, PALTA.id].sort(),
  )
  // La tablet nunca manda cantidad: la cocina todavia no midio gramajes.
  expect(enviados.every((i) => !('quantity' in i))).toBe(true)
  expect(enviados.every((i) => i.status === 'included')).toBe(true)
})

test('marcar que no habia lo manda como out_of_stock', async ({ page }) => {
  await injectOperatorToken(page)
  const getBody = await setupMocks(page)
  await abrirYSeleccionarBowl(page)

  const panel = page.getByTestId(`ingredientes-${BOWL.id}`)
  await panel.getByRole('button', { name: /^PALTA/ }).click()
  await panel.getByTestId(`agotado-${PALTA.id}`).click()

  await page.getByTestId('terminar-pedido').click()
  await expect(page.getByTestId('terminado-view')).toBeVisible()

  const body = getBody() as { items: Array<{ ingredients?: Array<Record<string, string>> }> }
  expect(body.items[0].ingredients).toEqual([
    { ingredient_id: PALTA.id, status: 'out_of_stock' },
  ])
})

test('sin ingredientes declarados el cuerpo no lleva la clave', async ({ page }) => {
  await injectOperatorToken(page)
  const getBody = await setupMocks(page)
  await abrirYSeleccionarBowl(page)

  await page.getByTestId('terminar-pedido').click()
  await expect(page.getByTestId('terminado-view')).toBeVisible()

  const body = getBody() as { items: Array<Record<string, unknown>> }
  expect('ingredients' in body.items[0]).toBe(false)
})

test('deseleccionar el plato descarta sus ingredientes', async ({ page }) => {
  await injectOperatorToken(page)
  const getBody = await setupMocks(page)
  await abrirYSeleccionarBowl(page)

  const panel = page.getByTestId(`ingredientes-${BOWL.id}`)
  await panel.getByRole('button', { name: /LECHUGA CRESPA/ }).click()

  // Quitar la unica unidad deselecciona el plato y se lleva el panel.
  await page.getByRole('button', { name: /Quitar una unidad de ARMA TU BOWL/ }).click()
  await expect(page.getByTestId(`ingredientes-${BOWL.id}`)).toHaveCount(0)

  // Volver a elegirlo no debe revivir la lechuga.
  await page.getByRole('button', { name: /ARMA TU BOWL/ }).first().click()
  await page.getByTestId('terminar-pedido').click()
  await expect(page.getByTestId('terminado-view')).toBeVisible()

  const body = getBody() as { items: Array<Record<string, unknown>> }
  expect('ingredients' in body.items[0]).toBe(false)
})

test('el filtro acota la lista de ingredientes', async ({ page }) => {
  await injectOperatorToken(page)
  await setupMocks(page)
  await abrirYSeleccionarBowl(page)

  const panel = page.getByTestId(`ingredientes-${BOWL.id}`)
  await expect(panel.getByRole('button', { name: /LECHUGA CRESPA/ })).toBeVisible()

  await panel.getByTestId(`filtro-ingredientes-${BOWL.id}`).fill('palta')

  await expect(panel.getByRole('button', { name: /LECHUGA CRESPA/ })).toHaveCount(0)
  await expect(panel.getByRole('button', { name: /^PALTA/ })).toBeVisible()
})

test('el plato no se ofrece como ingrediente de si mismo', async ({ page }) => {
  await injectOperatorToken(page)
  await setupMocks(page)
  await abrirYSeleccionarBowl(page)

  const panel = page.getByTestId(`ingredientes-${BOWL.id}`)
  await expect(panel.getByRole('button', { name: /ARMA TU BOWL/ })).toHaveCount(0)
})
