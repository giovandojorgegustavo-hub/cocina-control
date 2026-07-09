/**
 * Tests for formatRelativeDate via the bandeja rendering.
 * These tests inject deliveries with specific timestamps and verify the
 * rendered output matches the expected relative date format.
 */
import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const DELIVERIES_URL = '**/api/v1/deliveries'

async function injectOperatorToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('operator')
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
  await injectOperatorToken(page)

  // Use a timestamp 2 days in the future from "now".
  // The test runs against a real browser, so we use a fixed far-future date.
  const futureIso = '2099-12-31T10:30:00Z'

  await page.route(DELIVERIES_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'del-future',
          supplier_name: 'PROVEEDOR FUTURO',
          status: 'no_leida',
          item_count: 1,
          created_at: futureIso,
        },
      ]),
    })
  })

  await page.goto('/entradas')

  // The row must be visible
  await expect(page.getByText('PROVEEDOR FUTURO')).toBeVisible()

  // The date must render as "hoy HH:mm" — specifically "hoy 07:30" (UTC-3 of 10:30Z)
  // or "hoy XX:XX" — we check the "hoy" prefix to confirm future is treated as today
  const row = page.getByRole('button', { name: /PROVEEDOR FUTURO/i })
  await expect(row).toContainText('hoy 07:30')
})
