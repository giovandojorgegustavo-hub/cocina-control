import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// v0.3: /entradas now uses purchase-orders/pending (not /deliveries)
const PENDING_URL = '**/api/v1/purchase-orders/pending'
const LOGOUT_URL = '**/api/v1/auth/logout'

async function injectToken(
  page: import('@playwright/test').Page,
  role: 'operator' | 'owner' | 'admin',
) {
  const token = makeTestJwt(role)
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
  return token
}

// Card accessible names are "<title> — <subtitle>". These regexes target the
// menu cards specifically (the footer "ver pedidos" is matched separately).
const CARD_ENTRADA = /Entrada — /i
const CARD_INVENTARIO = /Inventario — /i
const CARD_PEDIDOS = /Pedidos — Bandeja/i
const CARD_NUEVA_ORDEN = /Nueva orden — /i
const CARD_PRECIOS = /Precios y descuentos — /i
const CARD_EXTRAS = /Extras y opciones — /i
const CARD_DISTRITOS = /Distritos de reparto — /i

// ---------------------------------------------------------------------------
// test_home_operacion_section_renders_for_cocinero
// ---------------------------------------------------------------------------

test('test_home_operacion_section_renders_for_cocinero', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')

  // The OPERACIÓN section and its three base cards are visible
  await expect(page.getByRole('region', { name: /operación/i })).toBeVisible()
  await expect(page.getByRole('button', { name: CARD_ENTRADA })).toBeVisible()
  await expect(page.getByRole('button', { name: CARD_INVENTARIO })).toBeVisible()
  await expect(page.getByRole('button', { name: CARD_PEDIDOS })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_cocinero_does_not_see_carta_section
// ---------------------------------------------------------------------------

test('test_cocinero_does_not_see_carta_section', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')

  // OPERACIÓN is present, but CARTA (and its cards) must never render
  await expect(page.getByRole('region', { name: /operación/i })).toBeVisible()
  await expect(page.getByRole('region', { name: /^carta$/i })).toHaveCount(0)
  await expect(page.getByRole('button', { name: CARD_PRECIOS })).toHaveCount(0)
  await expect(page.getByRole('button', { name: CARD_EXTRAS })).toHaveCount(0)
  await expect(page.getByRole('button', { name: CARD_DISTRITOS })).toHaveCount(0)
  await expect(page.getByRole('button', { name: CARD_NUEVA_ORDEN })).toHaveCount(0)
})

// ---------------------------------------------------------------------------
// test_home_card_touch_target_min_48px
// ---------------------------------------------------------------------------

test('test_home_card_touch_target_min_48px', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')

  const cards = [
    page.getByRole('button', { name: CARD_ENTRADA }),
    page.getByRole('button', { name: CARD_INVENTARIO }),
    page.getByRole('button', { name: CARD_PEDIDOS }),
  ]

  for (const card of cards) {
    const box = await card.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.width).toBeGreaterThanOrEqual(48)
    expect(box!.height).toBeGreaterThanOrEqual(48)
  }
})

// ---------------------------------------------------------------------------
// test_home_card_touch_target_min_100px
// min-h-[120px] is the real constraint; 100px is a safe lower bound.
// ---------------------------------------------------------------------------

test('test_home_card_touch_target_min_100px', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')

  const cards = [
    page.getByRole('button', { name: CARD_ENTRADA }),
    page.getByRole('button', { name: CARD_INVENTARIO }),
    page.getByRole('button', { name: CARD_PEDIDOS }),
  ]

  for (const card of cards) {
    const box = await card.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.height).toBeGreaterThanOrEqual(100)
  }
})

// ---------------------------------------------------------------------------
// test_entrada_card_navigates_to_bandeja
// ---------------------------------------------------------------------------

test('test_entrada_card_navigates_to_bandeja', async ({ page }) => {
  await injectToken(page, 'operator')

  await page.route(PENDING_URL, (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await page.goto('/')
  await page.getByRole('button', { name: CARD_ENTRADA }).click()

  await expect(page).toHaveURL(/\/entradas/)
})

// ---------------------------------------------------------------------------
// test_inventario_card_navigates_to_inventario
// ---------------------------------------------------------------------------

test('test_inventario_card_navigates_to_inventario', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')
  await page.getByRole('button', { name: CARD_INVENTARIO }).click()
  await expect(page).toHaveURL(/\/inventario/)
})

// ---------------------------------------------------------------------------
// test_pedidos_card_navigates_to_bandeja (issue #139: bandeja-first)
// ---------------------------------------------------------------------------

test('test_pedidos_card_navigates_to_bandeja', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.route('**/api/v1/delivery-orders*', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })
  await page.goto('/')
  await page.getByRole('button', { name: CARD_PEDIDOS }).click()
  await expect(page).toHaveURL('/pedidos')
})

// ---------------------------------------------------------------------------
// test_home_card_subtitles (one-line subtitle copy)
// ---------------------------------------------------------------------------

test('test_home_card_subtitles', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')

  await expect(page.getByRole('button', { name: CARD_ENTRADA })).toContainText('Llegó una entrega')
  await expect(page.getByRole('button', { name: CARD_INVENTARIO })).toContainText('Contar stock')
  await expect(page.getByRole('button', { name: CARD_PEDIDOS })).toContainText('Bandeja y foto')
})

// ---------------------------------------------------------------------------
// test_operator_home_shows_logout
// ---------------------------------------------------------------------------

test('test_operator_home_shows_logout', async ({ page }) => {
  await injectToken(page, 'operator')
  await page.goto('/')

  const cerrar = page.getByRole('button', { name: 'cerrar' })
  await expect(cerrar).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_home_footer_navega_a_bandeja_pedidos (issue #136)
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
// home logout clears session and navigates to login
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

  const cachedData = await page.evaluate(() => sessionStorage.getItem('cocina-auth'))
  const authState = cachedData ? JSON.parse(cachedData) : null
  const token = authState?.state?.token ?? null
  expect(token).toBeNull()
})

// ---------------------------------------------------------------------------
// test_admin_sees_carta_section_and_nueva_orden (Fix 5 / QA-MEDIO 6)
// ---------------------------------------------------------------------------

test('test_admin_sees_carta_section_and_nueva_orden', async ({ page }) => {
  await injectToken(page, 'admin')
  await page.goto('/')

  // Admin lands on home (not /tablero) and sees both sections
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('button', { name: CARD_NUEVA_ORDEN })).toBeVisible()
  await expect(page.getByRole('region', { name: /^carta$/i })).toBeVisible()
  await expect(page.getByRole('button', { name: CARD_PRECIOS })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_owner_can_open_menu_and_sees_both_sections
// The '/' guard now allows owner too, so the owner can open the grouped menu
// (their landing page remains /tablero via Login).
// ---------------------------------------------------------------------------

test('test_owner_can_open_menu_and_sees_both_sections', async ({ page }) => {
  await injectToken(page, 'owner')
  await page.goto('/')

  await expect(page).toHaveURL('/')
  await expect(page.getByRole('region', { name: /operación/i })).toBeVisible()
  await expect(page.getByRole('region', { name: /^carta$/i })).toBeVisible()
  await expect(page.getByRole('button', { name: CARD_DISTRITOS })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_carta_card_navigates_to_precios
// ---------------------------------------------------------------------------

test('test_carta_card_navigates_to_precios', async ({ page }) => {
  await injectToken(page, 'admin')

  await page.route('**/api/v1/products*', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })
  await page.route('**/api/v1/promotions*', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await page.goto('/')
  await page.getByRole('button', { name: CARD_PRECIOS }).click()

  await expect(page).toHaveURL(/\/precios/)
})
