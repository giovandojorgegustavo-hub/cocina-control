import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// Pantalla del asistente del panel. La API se mockea: lo que se prueba es que
// la pantalla muestre la propuesta, que al confirmar dispare el PATCH de negocio
// que YA existe (nunca una ruta nueva), y que un `none` no muestre tarjeta. La
// regla de negocio (que el backend solo lee y valida) vive en
// tests/test_assistant.py.

const PROPOSE_URL = '**/api/v1/assistant/propose'

async function injectToken(page: import('@playwright/test').Page, role: 'owner' | 'admin' | 'cocinero') {
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, makeTestJwt(role))
}

test('propone un precio, confirma y dispara el PATCH de negocio', async ({ page }) => {
  await injectToken(page, 'owner')

  await page.route(PROPOSE_URL, (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reply: 'Voy a subir el precio del Focus Bowl a S/ 35.00.',
        summary: 'Subir FOCUS BOWL a S/ 35.00',
        proposal: { type: 'set_price', product_id: 'p-1', product_name: 'FOCUS BOWL', sale_price: '35.00' },
      }),
    })
  })

  let patchBody: unknown = null
  await page.route('**/api/v1/products/p-1/pricing', (route) => {
    patchBody = route.request().postDataJSON()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'p-1',
        name: 'FOCUS BOWL',
        unit: 'un',
        low_stock_threshold: null,
        is_active: true,
        is_purchase: false,
        is_sale: true,
        sale_price: '35.00',
        discount_percent: null,
      }),
    })
  })

  await page.goto('/asistente')

  await page.getByLabel('Mensaje para el asistente').fill('sube el Focus Bowl a 35')
  await page.getByRole('button', { name: 'Enviar' }).click()

  // La propuesta aparece con su resumen.
  const card = page.getByRole('region', { name: 'Propuesta del asistente' })
  await expect(card).toBeVisible()
  await expect(card).toContainText('Subir FOCUS BOWL a S/ 35.00')

  // Confirmar dispara el PATCH del endpoint de negocio con el precio.
  await card.getByRole('button', { name: 'Confirmar' }).click()

  await expect(page.getByText(/Listo:/)).toBeVisible()
  expect(patchBody).toEqual({ sale_price: '35.00' })
  // La tarjeta desaparece tras confirmar.
  await expect(card).not.toBeVisible()
})

test('un `none` no muestra tarjeta de propuesta', async ({ page }) => {
  await injectToken(page, 'admin')

  await page.route(PROPOSE_URL, (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reply: 'Eso no lo puedo hacer. Los cambios de código pasan por un desarrollador.',
        summary: null,
        proposal: null,
      }),
    })
  })

  await page.goto('/asistente')
  await page.getByLabel('Mensaje para el asistente').fill('borra todos los pedidos')
  await page.getByRole('button', { name: 'Enviar' }).click()

  await expect(page.getByText(/no lo puedo hacer/)).toBeVisible()
  await expect(page.getByRole('region', { name: 'Propuesta del asistente' })).toHaveCount(0)
})

test('el cocinero no llega a /asistente', async ({ page }) => {
  await injectToken(page, 'cocinero')
  await page.goto('/asistente')
  await expect(page).toHaveURL('/')
})
