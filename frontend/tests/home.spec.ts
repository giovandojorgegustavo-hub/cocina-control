import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const DELIVERIES_URL = '**/api/v1/deliveries'
const LOGOUT_URL = '**/api/v1/auth/logout'

async function injectToken(page: import('@playwright/test').Page, role: 'operator' | 'owner') {
  const token = makeTestJwt(role)
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
  return token
}

// ---------------------------------------------------------------------------
// test_home_renders_three_big_buttons
// ---------------------------------------------------------------------------

test('test_home_renders_three_big_buttons', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')

  // Verify the three buttons exist with the correct text
  await expect(page.getByRole('button', { name: /ENTRADA/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /INVENTARIO/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /PEDIDO/i })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_home_button_touch_target_min_48px
// ---------------------------------------------------------------------------

test('test_home_button_touch_target_min_48px', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')

  const buttons = [
    page.getByRole('button', { name: /ENTRADA/i }),
    page.getByRole('button', { name: /INVENTARIO/i }),
    page.getByRole('button', { name: /PEDIDO/i }),
  ]

  for (const button of buttons) {
    const box = await button.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.width).toBeGreaterThanOrEqual(48)
    expect(box!.height).toBeGreaterThanOrEqual(48)
  }
})

// ---------------------------------------------------------------------------
// test_entrada_button_navigates_to_bandeja
// ---------------------------------------------------------------------------

test('test_entrada_button_navigates_to_bandeja', async ({ page }) => {
  await injectToken(page, 'operator')

  // Mock GET /deliveries to return empty list so Bandeja renders without error
  await page.route(DELIVERIES_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: /ENTRADA/i }).click()

  await expect(page).toHaveURL(/\/entradas/)
})

// ---------------------------------------------------------------------------
// test_operator_home_shows_logout
// ---------------------------------------------------------------------------

test('test_operator_home_shows_logout', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')

  // The "cerrar" button must be visible
  const cerrar = page.getByRole('button', { name: 'cerrar' })
  await expect(cerrar).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_owner_visiting_home_is_redirected_to_tablero
// ---------------------------------------------------------------------------

test('test_owner_visiting_home_is_redirected_to_tablero', async ({ page }) => {
  await injectToken(page, 'owner')

  // Navigate to / as an owner — RequireRole should redirect to /tablero
  await page.goto('/')

  await expect(page).toHaveURL(/\/tablero/)
})

// ---------------------------------------------------------------------------
// Extra: logout works from home
// ---------------------------------------------------------------------------

test('home logout clears session and navigates to login', async ({ page }) => {
  await injectToken(page, 'operator')

  await page.route(LOGOUT_URL, (route) => {
    route.fulfill({ status: 204, body: '' })
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'cerrar' }).click()

  await expect(page).toHaveURL(/\/login/)
})
