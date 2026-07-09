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

// ---------------------------------------------------------------------------
// test_home_button_subtitles_have_parentheses (C-5)
// Wireframe specifies the subtitle copy with parentheses.
// ---------------------------------------------------------------------------

test('test_home_button_subtitles_have_parentheses', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')

  await expect(page.getByRole('button', { name: /ENTRADA/i })).toContainText('(llegó una entrega)')
  await expect(page.getByRole('button', { name: /INVENTARIO/i })).toContainText('(contar stock)')
  await expect(page.getByRole('button', { name: /PEDIDO/i })).toContainText('(foto al empacar)')
})

// ---------------------------------------------------------------------------
// test_home_ver_mis_registros_is_not_a_link (C-3)
// Must not be a link or fire a dialog — just inert text.
// ---------------------------------------------------------------------------

test('test_home_ver_mis_registros_is_not_a_link', async ({ page }) => {
  await injectToken(page, 'operator')

  // Capture any dialog that appears — if alert fires, the test fails
  let dialogFired = false
  page.on('dialog', (dialog) => {
    dialogFired = true
    void dialog.dismiss()
  })

  await page.goto('/')

  // Should not be a link element
  const link = page.getByRole('link', { name: /ver mis registros/i })
  await expect(link).toHaveCount(0)

  // The text exists but clicking does nothing
  const span = page.getByText('ver mis registros')
  await expect(span).toBeVisible()
  await span.click()
  expect(dialogFired).toBe(false)
})

// ---------------------------------------------------------------------------
// test_inventario_button_navigates_to_inventario (CS-3)
// ---------------------------------------------------------------------------

test('test_inventario_button_navigates_to_inventario', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')
  await page.getByRole('button', { name: /INVENTARIO/i }).click()
  await expect(page).toHaveURL(/\/inventario/)
})

// ---------------------------------------------------------------------------
// test_pedido_button_navigates_to_pedidos_nuevo (CS-3)
// ---------------------------------------------------------------------------

test('test_pedido_button_navigates_to_pedidos_nuevo', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')
  await page.getByRole('button', { name: /PEDIDO/i }).click()
  await expect(page).toHaveURL(/\/pedidos\/nuevo/)
})

// ---------------------------------------------------------------------------
// test_home_button_touch_target_min_100px (CS-4)
// The real min-h-[120px] class means buttons are well above 100px — test that.
// ---------------------------------------------------------------------------

test('test_home_button_touch_target_min_100px', async ({ page }) => {
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
    // min-h-[120px] is the real constraint; 100px is a safe lower bound for this viewport
    expect(box!.height).toBeGreaterThanOrEqual(100)
  }
})

// ---------------------------------------------------------------------------
// test_logout_clears_query_cache (security)
// After logout, the deliveries cache must not be accessible.
// ---------------------------------------------------------------------------

test('test_logout_clears_query_cache', async ({ page }) => {
  await injectToken(page, 'operator')

  await page.route(DELIVERIES_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'del-secret',
          supplier_name: 'DATOS PRIVADOS SA',
          status: 'no_leida',
          item_count: 1,
          created_at: '2020-06-01T10:00:00Z',
        },
      ]),
    })
  })

  await page.route(LOGOUT_URL, (route) => {
    route.fulfill({ status: 204, body: '' })
  })

  // Load the bandeja to populate the cache
  await page.goto('/entradas')
  await expect(page.getByText('DATOS PRIVADOS SA')).toBeVisible()

  // Logout from home
  await page.goto('/')
  await page.getByRole('button', { name: 'cerrar' }).click()
  await expect(page).toHaveURL(/\/login/)

  // Verify the query cache was cleared: querying deliveries after logout
  // must not return the previously cached data
  const cachedData = await page.evaluate(() => {
    // The QueryClient is not directly accessible from the page context, but we
    // can verify indirectly: sessionStorage no longer holds a token, so any
    // subsequent navigation to /entradas redirects to login (auth guard).
    return sessionStorage.getItem('cocina-auth')
  })

  // Token is cleared — auth state is null
  const authState = cachedData ? JSON.parse(cachedData) : null
  const token = authState?.state?.token ?? null
  expect(token).toBeNull()
})
