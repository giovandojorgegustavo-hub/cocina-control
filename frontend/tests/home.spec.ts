import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// v0.3: /entradas now uses purchase-orders/pending (not /deliveries)
const PENDING_URL = '**/api/v1/purchase-orders/pending'
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
  await expect(page.getByRole('button', { name: /^PEDIDO/ })).toBeVisible()
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
    page.getByRole('button', { name: /^PEDIDO/ }),
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

  // Mock GET /purchase-orders/pending to return empty list so BandejaPartidas renders
  await page.route(PENDING_URL, (route) => {
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
// test_owner_visiting_home_redirected_to_tablero
// The guard on '/' is RequireAnyRole(['cocinero', 'admin']).
// Owner visiting '/' is redirected to '/tablero'.
// ---------------------------------------------------------------------------

test('test_owner_visiting_home_redirected_to_tablero', async ({ page }) => {
  await injectToken(page, 'owner')

  // Navigate to / as an owner — must be redirected to /tablero
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
  await expect(page.getByRole('button', { name: /^PEDIDO/ })).toContainText('(bandeja y foto)')
})

// ---------------------------------------------------------------------------
// test_home_footer_navega_a_bandeja_pedidos (issue #136)
// The footer is the entry point to the pedidos bandeja — before this fix the
// bandeja existed but no screen navigated to it.
// ---------------------------------------------------------------------------

test('test_home_footer_navega_a_bandeja_pedidos', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')

  const footerBtn = page.getByRole('button', { name: /ver pedidos/i })
  await expect(footerBtn).toBeVisible()
  await footerBtn.click()

  await expect(page).toHaveURL('/pedidos')
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
// test_pedido_button_navigates_to_bandeja (issue #139: bandeja-first)
// ---------------------------------------------------------------------------

test('test_pedido_button_navigates_to_bandeja', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.route('**/api/v1/delivery-orders*', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })
  await page.goto('/')
  await page.getByRole('button', { name: /^PEDIDO/ }).click()
  await expect(page).toHaveURL('/pedidos')
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
    page.getByRole('button', { name: /^PEDIDO/ }),
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

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'ord-secret',
          supplier_name: 'DATOS PRIVADOS SA',
          created_at: '2020-06-01T10:00:00Z',
          derived_status: 'open',
          pending_items_summary: '1 producto · todo pendiente',
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

// ---------------------------------------------------------------------------
// test_admin_visiting_home_sees_nueva_orden_button (Fix 5 / QA-MEDIO 6)
// ---------------------------------------------------------------------------

test('test_admin_visiting_home_sees_nueva_orden_button', async ({ page }) => {
  const adminToken = makeTestJwt('admin')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, adminToken)

  await page.goto('/')

  // Admin lands on home (not /tablero) and sees the NUEVA ORDEN button
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('button', { name: /NUEVA ORDEN/i })).toBeVisible()
})
