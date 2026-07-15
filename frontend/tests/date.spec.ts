/**
 * Tests for formatRelativeDate via the BandejaPartidas rendering (v0.3).
 * These tests inject pending orders with specific timestamps and verify the
 * rendered output matches the expected relative date format.
 *
 * Migrated from v0.2 (used /api/v1/deliveries) to v0.3 (uses /api/v1/purchase-orders/pending).
 */
import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const PENDING_URL = '**/api/v1/purchase-orders/pending'

async function injectCociToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('cocinero')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

// ---------------------------------------------------------------------------
// test_format_relative_date_future_treats_as_today (C-6)
// A timestamp in the future (clock skew / pre-load) must render as "hoy HH:mm"
// instead of falling through to DD/MM HH:mm with no indication.
// ---------------------------------------------------------------------------

test('test_format_relative_date_future_treats_as_today', async ({ page }) => {
  await injectCociToken(page)

  // Use a timestamp 2 days in the future from "now".
  // The test runs against a real browser, so we use a fixed far-future date.
  const futureIso = '2099-12-31T10:30:00Z'

  await page.route(PENDING_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'ord-future',
          supplier_name: 'PROVEEDOR FUTURO',
          created_at: futureIso,
          derived_status: 'open',
          pending_items_summary: '1 producto · todo pendiente',
        },
      ]),
    })
  })

  await page.goto('/entradas')

  // The row must be visible
  await expect(page.getByText('PROVEEDOR FUTURO')).toBeVisible()

  // The date must render as "hoy HH:mm" — specifically "hoy 07:30" (UTC-3 of 10:30Z)
  const row = page.getByRole('button', { name: /Orden de PROVEEDOR FUTURO/i })
  await expect(row).toContainText('hoy 07:30')
})
