// MIGRATED: bandeja.spec.ts → tests for BandejaPartidas (v0.3)
// The v0.2 Bandeja (deliveries flow) has been replaced by BandejaPartidas
// (purchase-orders/pending flow). Tests now cover the new endpoint and new
// data shapes. Full coverage is in bandeja-partidas.spec.ts; this file keeps
// the historical file name so any tooling that references it still works.
//
// Tests that were impossible to migrate (they tested no_leida → en_verificacion
// state transitions and the /deliveries endpoint which no longer exists) have
// been removed with this comment as the record.

import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const PENDING_URL = '**/api/v1/purchase-orders/pending'

async function injectCociToken(page: import('@playwright/test').Page) {
  // v0.3: role is 'cocinero' — the old 'operator' role does not exist
  const token = makeTestJwt('cocinero')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

const T_OLD = '2020-01-01T12:00:00Z'

// ---------------------------------------------------------------------------
// test_bandeja_renders_pending_orders
// ---------------------------------------------------------------------------

test('test_bandeja_renders_pending_orders', async ({ page }) => {
  await injectCociToken(page)

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'ord-1',
          supplier_name: 'VERDULERIA NUNEZ',
          created_at: T_OLD,
          derived_status: 'open',
          pending_items_summary: '3 productos · todo pendiente',
        },
        {
          id: 'ord-2',
          supplier_name: 'CARNICERIA LOPEZ',
          created_at: T_OLD,
          derived_status: 'partially_received',
          pending_items_summary: 'faltan 40 kg POLLO',
        },
      ]),
    })
  })

  await page.goto('/entradas')

  await expect(page.getByText('VERDULERIA NUNEZ')).toBeVisible()
  await expect(page.getByText('CARNICERIA LOPEZ')).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_bandeja_shows_abierta_badge
// ---------------------------------------------------------------------------

test('test_bandeja_shows_abierta_badge', async ({ page }) => {
  await injectCociToken(page)

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'ord-1',
          supplier_name: 'VERDULERIA NUNEZ',
          created_at: T_OLD,
          derived_status: 'open',
          pending_items_summary: '3 productos · todo pendiente',
        },
      ]),
    })
  })

  await page.goto('/entradas')

  const badge = page.getByText('ABIERTA')
  await expect(badge).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_bandeja_shows_empty_state
// ---------------------------------------------------------------------------

test('test_bandeja_shows_empty_state', async ({ page }) => {
  await injectCociToken(page)

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/entradas')

  await expect(page.getByText(/No hay ordenes con entregas pendientes/i)).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_bandeja_shows_loading_skeletons
// ---------------------------------------------------------------------------

test('test_bandeja_shows_loading_skeletons', async ({ page }) => {
  await injectCociToken(page)

  await page.route(PENDING_URL, () => {
    // intentionally do not fulfill
  })

  await page.goto('/entradas')

  const skeletons = page.getByRole('status', { name: 'Cargando orden' })
  await expect(skeletons).toHaveCount(3)
})

// ---------------------------------------------------------------------------
// test_bandeja_shows_error_banner_on_fetch_failure
// ---------------------------------------------------------------------------

test('test_bandeja_shows_error_banner_on_fetch_failure', async ({ page }) => {
  await injectCociToken(page)

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal server error' }),
    })
  })

  await page.goto('/entradas')

  const alert = page.getByRole('alert')
  await expect(alert).toBeVisible()
  await expect(alert).toContainText(/reintentar/i)
})

// ---------------------------------------------------------------------------
// test_bandeja_row_click_navigates_to_detail
// ---------------------------------------------------------------------------

test('test_bandeja_row_click_navigates_to_detail', async ({ page }) => {
  await injectCociToken(page)

  const targetId = 'ord-2'

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: targetId,
          supplier_name: 'VERDULERIA NUNEZ',
          created_at: T_OLD,
          derived_status: 'open',
          pending_items_summary: '3 productos · todo pendiente',
        },
      ]),
    })
  })

  await page.route(`**/api/v1/purchase-orders/${targetId}/partida-draft`, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        order_id: targetId,
        supplier_name: 'VERDULERIA NUNEZ',
        partida_number: 1,
        items: [],
      }),
    })
  })

  await page.goto('/entradas')

  await page.getByRole('button', { name: /Orden de VERDULERIA NUNEZ/i }).click()

  await expect(page).toHaveURL(new RegExp(`/entradas/${targetId}`))
})

// ---------------------------------------------------------------------------
// test_bandeja_no_auth_redirects_to_login
// ---------------------------------------------------------------------------

test('test_bandeja_no_auth_redirects_to_login', async ({ page }) => {
  await page.goto('/login')
  await page.evaluate(() => sessionStorage.clear())

  await page.goto('/entradas')

  await expect(page).toHaveURL(/\/login/)
})

// ---------------------------------------------------------------------------
// test_bandeja_shows_offline_banner_when_disconnected
// ---------------------------------------------------------------------------

test('test_bandeja_shows_offline_banner_when_disconnected', async ({ page, context }) => {
  await injectCociToken(page)

  await page.route(PENDING_URL, (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await page.goto('/entradas')
  await context.setOffline(true)

  await expect(page.getByText(/sin conexi/i)).toBeVisible()

  await context.setOffline(false)
})
