/**
 * Tests para la casilla "completar despues" de /pedidos/nuevo.
 *
 * La casilla nace marcada a proposito: el camino por defecto sigue siendo
 * sacar la foto y seguir, que es el unico que aguanta la hora punta. Si un dia
 * alguien la deja desmarcada por defecto, la cocina empieza a esperar al
 * servidor en cada pedido — por eso el primer test existe.
 */
import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const CREATE_URL = '**/api/v1/delivery-orders'
const PHOTO_URL = '**/api/v1/delivery-orders/*/photo'
const DETAIL_URL = '**/api/v1/delivery-orders/*'
const PRODUCTS_URL = '**/api/v1/products*'

const SERVER_ID = 'order-desde-camara'

type Page = import('@playwright/test').Page

async function injectOperatorToken(page: Page) {
  const token = makeTestJwt('operator')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

async function injectFakeCamera(page: Page) {
  await page.context().grantPermissions(['camera'], { origin: 'http://localhost:5173' })
}

// ---------------------------------------------------------------------------

test('la casilla completar despues nace marcada', async ({ page }) => {
  await injectFakeCamera(page)
  await injectOperatorToken(page)
  await page.goto('/pedidos/nuevo')

  const casilla = page.getByTestId('completar-despues')
  await expect(casilla).toBeVisible()
  await expect(casilla).toBeChecked()
})

test('la casilla tiene area tactil usable en tablet', async ({ page }) => {
  await injectFakeCamera(page)
  await injectOperatorToken(page)
  await page.goto('/pedidos/nuevo')

  const box = await page.getByTestId('completar-despues-label').boundingBox()
  expect(box).not.toBeNull()
  expect(box!.height).toBeGreaterThanOrEqual(44)
})

test('desmarcarla lleva al detalle del pedido cuando la foto termina de subir', async ({
  page,
}) => {
  await injectFakeCamera(page)
  await injectOperatorToken(page)

  await page.route(PHOTO_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: SERVER_ID, photo_at: '2020-01-01T23:42:00Z' }),
    })
  })
  await page.route(PRODUCTS_URL, (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })
  await page.route(DETAIL_URL, (route) => {
    const url = route.request().url()
    if (url.endsWith(SERVER_ID)) {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: SERVER_ID,
          status: 'pending',
          photo_at: '2020-01-01T23:42:00Z',
          photo_by: 'user-1',
          completed_at: null,
          completed_by: null,
          items: [],
        }),
      })
    } else {
      route.continue()
    }
  })
  await page.route(CREATE_URL, (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({ id: SERVER_ID }),
    })
  })

  await page.goto('/pedidos/nuevo')
  await expect(page.getByTestId('shutter-button')).toBeVisible()

  await page.getByTestId('completar-despues').uncheck()
  await page.getByTestId('shutter-button').click()

  // El confirmatorio aparece igual de inmediato — nunca se bloquea el disparo.
  await expect(page.getByTestId('confirmed-view')).toBeVisible({ timeout: 2000 })
  await expect(page.getByText('abriendo el detalle')).toBeVisible()

  // Y cuando la subida resuelve, cae en completar en vez de la bandeja.
  await expect(page).toHaveURL(new RegExp(`/pedidos/${SERVER_ID}/completar$`), {
    timeout: 10_000,
  })
})

test('si la subida nunca resuelve, el operario cae en la bandeja y no queda colgado', async ({
  page,
}) => {
  await injectFakeCamera(page)
  await injectOperatorToken(page)

  // La creacion del pedido cuelga: simula estar sin senal util.
  await page.route(CREATE_URL, () => {})
  await page.route(PHOTO_URL, () => {})

  await page.goto('/pedidos/nuevo')
  await expect(page.getByTestId('shutter-button')).toBeVisible()

  await page.getByTestId('completar-despues').uncheck()
  await page.getByTestId('shutter-button').click()

  await expect(page.getByTestId('confirmed-view')).toBeVisible({ timeout: 2000 })
  await expect(page).toHaveURL(/\/pedidos$/, { timeout: 15_000 })
})
