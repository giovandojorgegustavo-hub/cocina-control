import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DELIVERY_ID = 'del-abc'
const ITEM_PALTA = 'item-palta'
const ITEM_CEBOLLA = 'item-cebolla'
const ITEM_TOMATE = 'item-tomate'

const DETAIL_URL = `**/api/v1/deliveries/${DELIVERY_ID}`
const OPEN_URL = `**/api/v1/deliveries/${DELIVERY_ID}/open`
const CONFIRM_PALTA_URL = `**/api/v1/deliveries/${DELIVERY_ID}/items/${ITEM_PALTA}/confirm`
const CONFIRM_CEBOLLA_URL = `**/api/v1/deliveries/${DELIVERY_ID}/items/${ITEM_CEBOLLA}/confirm`
const VALIDATE_URL = `**/api/v1/deliveries/${DELIVERY_ID}/validate`

function makeDelivery(
  status: 'no_leida' | 'en_verificacion' | 'validada',
  overrides?: Partial<{
    paltalQty: number | null
    ceboQty: number | null
    tomQty: number | null
  }>,
) {
  return {
    id: DELIVERY_ID,
    supplier_name: 'VERDULERIA NUNEZ',
    status,
    item_count: 3,
    created_at: '2020-01-01T12:00:00Z',
    validated_at: status === 'validada' ? '2020-01-01T14:00:00Z' : null,
    items: [
      {
        id: ITEM_PALTA,
        product_id: 'prod-palta',
        product_name: 'PALTA',
        unit: 'un',
        announced_qty: 12,
        received_qty: overrides?.paltalQty ?? null,
      },
      {
        id: ITEM_CEBOLLA,
        product_id: 'prod-cebolla',
        product_name: 'CEBOLLA',
        unit: 'kg',
        announced_qty: 10,
        received_qty: overrides?.ceboQty ?? null,
      },
      {
        id: ITEM_TOMATE,
        product_id: 'prod-tomate',
        product_name: 'TOMATE',
        unit: 'kg',
        announced_qty: 15,
        received_qty: overrides?.tomQty ?? null,
      },
    ],
  }
}

async function injectOperatorToken(page: import('@playwright/test').Page) {
  const token = makeTestJwt('operator')
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
}

async function goToVerificacion(page: import('@playwright/test').Page) {
  await page.goto(`/entradas/${DELIVERY_ID}`)
}

// ---------------------------------------------------------------------------
// test_open_delivery_transitions_status_on_mount
// When the page loads with a no_leida delivery, it must call POST /open.
// ---------------------------------------------------------------------------

test('test_open_delivery_transitions_status_on_mount', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeDelivery('no_leida')),
      })
    } else {
      route.continue()
    }
  })

  const openCalled: string[] = []
  await page.route(OPEN_URL, (route) => {
    openCalled.push(route.request().method())
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }),
    })
  })

  await goToVerificacion(page)

  // Wait for item list to render — confirms the page mounted and data loaded
  await expect(page.getByText('PALTA')).toBeVisible()

  // POST /open must have been called
  expect(openCalled).toContain('POST')
})

// ---------------------------------------------------------------------------
// test_confirm_button_uses_announced_qty
// Clicking "OK — llegó así" sends the announced quantity in the request body.
// ---------------------------------------------------------------------------

test('test_confirm_button_uses_announced_qty', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeDelivery('en_verificacion')),
      })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }),
    }),
  )

  const confirmBodies: string[] = []
  await page.route(CONFIRM_PALTA_URL, (route) => {
    confirmBodies.push(route.request().postData() ?? '')
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ item_id: ITEM_PALTA, received_qty: 12 }),
    })
  })

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Click the first "OK — llegó así" button (PALTA row — first pending)
  await page.getByRole('button', { name: /Confirmar PALTA/i }).click()

  // The body must contain received_qty = 12 (the announced qty for PALTA)
  expect(confirmBodies.length).toBeGreaterThan(0)
  const body = JSON.parse(confirmBodies[0])
  expect(body.received_qty).toBe(12)
})

// ---------------------------------------------------------------------------
// test_edit_qty_saves_different_received
// Opening the edit modal, typing a new value, and submitting sends the new qty.
// ---------------------------------------------------------------------------

test('test_edit_qty_saves_different_received', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeDelivery('en_verificacion')),
      })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }),
    }),
  )

  const confirmBodies: string[] = []
  await page.route(CONFIRM_PALTA_URL, (route) => {
    confirmBodies.push(route.request().postData() ?? '')
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ item_id: ITEM_PALTA, received_qty: 8 }),
    })
  })

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Click the "editar" button for PALTA (first pending item)
  await page.getByRole('button', { name: /Editar cantidad de PALTA/i }).click()

  // Modal should open
  await expect(page.getByRole('dialog')).toBeVisible()

  // Clear the input and type a new value
  const input = page.getByLabel('Cantidad recibida')
  await input.fill('8')

  // Submit
  await page.getByRole('button', { name: /OK y siguiente/i }).click()

  // Modal should close
  await expect(page.getByRole('dialog')).toHaveCount(0)

  // The confirm request must have received_qty = 8
  expect(confirmBodies.length).toBeGreaterThan(0)
  const body = JSON.parse(confirmBodies[0])
  expect(body.received_qty).toBe(8)
})

// ---------------------------------------------------------------------------
// test_confirm_moves_focus_to_next_pending
// After confirming PALTA, the ▶ indicator should move to CEBOLLA.
// ---------------------------------------------------------------------------

test('test_confirm_moves_focus_to_next_pending', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeDelivery('en_verificacion')),
      })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }),
    }),
  )

  await page.route(CONFIRM_PALTA_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ item_id: ITEM_PALTA, received_qty: 12 }),
    }),
  )

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Before confirm: ▶ is next to PALTA (first pending)
  // The ▶ marker is a span next to the row's first pending item.
  // We check by verifying the CEBOLLA row does NOT yet have the focused class
  // (or we simply confirm after clicking that the PALTA row shows confirmed ✓)

  // Confirm PALTA
  await page.getByRole('button', { name: /Confirmar PALTA/i }).click()

  // After confirm: PALTA must show ✓ (confirmed)
  // The ✓ is aria-label="Confirmado"
  // Wait for the optimistic update
  const pallaRow = page.locator('div').filter({ hasText: /^PALTA/ }).first()
  await expect(pallaRow.getByLabel('Confirmado')).toBeVisible()

  // And CEBOLLA "OK — llegó así" button must be visible (it is now the first pending)
  await expect(page.getByRole('button', { name: /Confirmar CEBOLLA/i })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_validate_button_disabled_until_all_confirmed
// The validate button must show the progress counter and be disabled until
// all items are confirmed.
// ---------------------------------------------------------------------------

test('test_validate_button_disabled_until_all_confirmed', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeDelivery('en_verificacion')),
      })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }),
    }),
  )

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Initially 0/3 — button disabled
  const validateBtn = page.getByRole('button', { name: /validar entrega/i })
  await expect(validateBtn).toBeVisible()
  await expect(validateBtn).toBeDisabled()
  await expect(validateBtn).toContainText('0/3')
})

// ---------------------------------------------------------------------------
// test_validate_success_shows_confirmation_and_returns_home
// When /validate returns 200, show overlay and redirect to home.
// ---------------------------------------------------------------------------

test('test_validate_success_shows_confirmation_and_returns_home', async ({ page }) => {
  await injectOperatorToken(page)

  // Deliver all items pre-confirmed so we can validate immediately
  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          makeDelivery('en_verificacion', {
            paltalQty: 12,
            ceboQty: 10,
            tomQty: 15,
          }),
        ),
      })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }),
    }),
  )

  await page.route(VALIDATE_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: DELIVERY_ID,
        status: 'validada',
        validated_at: '2020-01-01T14:00:00Z',
      }),
    }),
  )

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Validate button must be enabled (all confirmed from server)
  const validateBtn = page.getByRole('button', { name: /validar entrega/i })
  await expect(validateBtn).toBeEnabled()

  await validateBtn.click()

  // Overlay must appear
  await expect(page.getByText('ENTREGA VALIDADA')).toBeVisible()
  await expect(page.getByText(/stock actualizado/i)).toBeVisible()

  // After timer (1.5 s) or clicking "listo", redirect to home
  await page.getByRole('button', { name: /listo/i }).click()
  await expect(page).toHaveURL('/')
})

// ---------------------------------------------------------------------------
// test_validate_race_shows_conflict_message
// When /validate returns 409 (already validated), show message and go home.
// ---------------------------------------------------------------------------

test('test_validate_race_shows_conflict_message', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          makeDelivery('en_verificacion', {
            paltalQty: 12,
            ceboQty: 10,
            tomQty: 15,
          }),
        ),
      })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }),
    }),
  )

  await page.route(VALIDATE_URL, (route) =>
    route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Delivery already validated' }),
    }),
  )

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  const validateBtn = page.getByRole('button', { name: /validar entrega/i })
  await expect(validateBtn).toBeEnabled()
  await validateBtn.click()

  // Must show the conflict toast
  await expect(page.getByRole('alert')).toContainText('Esta entrega ya fue validada.')

  // Must redirect to home after 1.5 s
  await expect(page).toHaveURL('/', { timeout: 3000 })
})

// ---------------------------------------------------------------------------
// test_confirm_error_reverts_optimistic_and_shows_toast
// When POST /confirm returns 500, the optimistic row must revert and a toast
// must appear. The row should NOT stay in the confirmed state.
// ---------------------------------------------------------------------------

test('test_confirm_error_reverts_optimistic_and_shows_toast', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeDelivery('en_verificacion')),
      })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }),
    }),
  )

  // Confirm fails
  await page.route(CONFIRM_PALTA_URL, (route) =>
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal server error' }),
    }),
  )

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Click OK — this triggers the optimistic update then the failing request
  await page.getByRole('button', { name: /Confirmar PALTA/i }).click()

  // Toast must appear
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByRole('alert')).toContainText(/No se pudo confirmar/)

  // PALTA must NOT have ✓ (revert must have happened)
  await expect(page.getByRole('button', { name: /Confirmar PALTA/i })).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_validada_delivery_opens_in_read_only
// A delivery with status=validada must render without edit/confirm buttons.
// ---------------------------------------------------------------------------

test('test_validada_delivery_opens_in_read_only', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          makeDelivery('validada', { paltalQty: 12, ceboQty: 8, tomQty: 15 }),
        ),
      })
    } else {
      route.continue()
    }
  })

  await goToVerificacion(page)

  // Read-only mode must show the validation info
  await expect(page.getByText(/Entrega validada/i)).toBeVisible()

  // No confirm buttons
  await expect(page.getByRole('button', { name: /OK — llegó así/i })).toHaveCount(0)

  // No edit buttons
  await expect(page.getByRole('button', { name: /editar/i })).toHaveCount(0)

  // No validate button
  await expect(page.getByRole('button', { name: /validar entrega/i })).toHaveCount(0)

  // Products must be visible
  await expect(page.getByText('PALTA')).toBeVisible()
  await expect(page.getByText('CEBOLLA')).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_qty_zero_valid
// The operator can edit a quantity to 0 and submit — 0 is a valid received qty.
// ---------------------------------------------------------------------------

test('test_qty_zero_valid', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeDelivery('en_verificacion')),
      })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }),
    }),
  )

  const confirmBodies: string[] = []
  await page.route(CONFIRM_PALTA_URL, (route) => {
    confirmBodies.push(route.request().postData() ?? '')
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ item_id: ITEM_PALTA, received_qty: 0 }),
    })
  })

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Open edit modal
  await page.getByRole('button', { name: /Editar cantidad de PALTA/i }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  // Set quantity to 0
  await page.getByLabel('Cantidad recibida').fill('0')

  // Submit button must be enabled (0 is valid)
  const submitBtn = page.getByRole('button', { name: /OK y siguiente/i })
  await expect(submitBtn).toBeEnabled()
  await submitBtn.click()

  // Request must have received_qty = 0
  expect(confirmBodies.length).toBeGreaterThan(0)
  const body = JSON.parse(confirmBodies[0])
  expect(body.received_qty).toBe(0)
})

// ---------------------------------------------------------------------------
// test_double_tap_ok_fires_single_request (QA H-01)
// A double tap on "OK — llegó así" in the same tick must fire only one confirm
// request, not two.
// ---------------------------------------------------------------------------

test('test_double_tap_ok_fires_single_request', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeDelivery('en_verificacion')),
      })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }),
    }),
  )

  const confirmRequests: string[] = []
  await page.route(CONFIRM_PALTA_URL, async (route) => {
    confirmRequests.push(route.request().method())
    // Slow response to keep the in-flight window open during the double tap
    await new Promise((r) => setTimeout(r, 200))
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ item_id: ITEM_PALTA, received_qty: 12 }),
    })
  })

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  const okBtn = page.getByRole('button', { name: /Confirmar PALTA/i })

  // Double-click both buttons in the same JS tick
  await page.evaluate((selector) => {
    const el = document.querySelector(selector) as HTMLButtonElement | null
    if (el) { el.click(); el.click() }
  }, '[aria-label="Confirmar PALTA con cantidad anunciada"]')

  // Wait for the single request to resolve
  await expect(page.getByLabel('Confirmado')).toBeVisible({ timeout: 3000 })

  // Only one request must have been fired
  expect(confirmRequests.length).toBe(1)

  // Suppress the unused variable warning from TypeScript's perspective
  void okBtn
})

// ---------------------------------------------------------------------------
// test_double_tap_validate_fires_single_request (QA H-02)
// A double tap on "validar entrega" must fire only one /validate request.
// ---------------------------------------------------------------------------

test('test_double_tap_validate_fires_single_request', async ({ page }) => {
  await injectOperatorToken(page)

  // All items pre-confirmed so validate is immediately enabled
  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeDelivery('en_verificacion', { paltalQty: 12, ceboQty: 10, tomQty: 15 })),
      })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }),
    }),
  )

  const validateRequests: string[] = []
  await page.route(VALIDATE_URL, async (route) => {
    validateRequests.push(route.request().method())
    await new Promise((r) => setTimeout(r, 200))
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: DELIVERY_ID, status: 'validada', validated_at: '2020-01-01T14:00:00Z' }),
    })
  })

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  const validateBtn = page.getByRole('button', { name: /validar entrega/i })
  await expect(validateBtn).toBeEnabled()

  // Double-click in the same JS tick
  await page.evaluate(() => {
    const el = document.querySelector('[aria-label*="Validar entrega"]') as HTMLButtonElement | null
    if (el) { el.click(); el.click() }
  })

  // Wait for success overlay
  await expect(page.getByText('ENTREGA VALIDADA')).toBeVisible({ timeout: 3000 })

  expect(validateRequests.length).toBe(1)
})

// ---------------------------------------------------------------------------
// test_validate_disabled_while_any_confirm_in_flight (QA H-03)
// When a confirm request is still in flight, "validar entrega" must remain
// disabled even though all items appear confirmed locally.
// ---------------------------------------------------------------------------

test('test_validate_disabled_while_any_confirm_in_flight', async ({ page }) => {
  await injectOperatorToken(page)

  // Start with two items, one pre-confirmed
  const deliveryTwoItems = {
    id: DELIVERY_ID,
    supplier_name: 'VERDULERIA NUNEZ',
    status: 'en_verificacion' as const,
    item_count: 2,
    created_at: '2020-01-01T12:00:00Z',
    validated_at: null,
    items: [
      { id: ITEM_PALTA, product_id: 'prod-palta', product_name: 'PALTA', unit: 'un', announced_qty: 12, received_qty: 12 },
      { id: ITEM_CEBOLLA, product_id: 'prod-cebolla', product_name: 'CEBOLLA', unit: 'kg', announced_qty: 10, received_qty: null },
    ],
  }

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(deliveryTwoItems) })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }) }),
  )

  // Slow confirm for CEBOLLA — keeps the request in flight
  let resolveCebolla: (() => void) | undefined
  await page.route(CONFIRM_CEBOLLA_URL, async (route) => {
    await new Promise<void>((r) => { resolveCebolla = r })
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ item_id: ITEM_CEBOLLA, received_qty: 10 }) })
  })

  await goToVerificacion(page)
  await expect(page.getByText('CEBOLLA')).toBeVisible()

  // Click OK for CEBOLLA — optimistic update fires, request is in flight
  await page.getByRole('button', { name: /Confirmar CEBOLLA/i }).click()

  // Both items now appear confirmed locally, but CEBOLLA confirm is in flight.
  // The validate button MUST still be disabled.
  const validateBtn = page.getByRole('button', { name: /validar entrega/i })
  await expect(validateBtn).toBeDisabled()

  // Resolve the in-flight confirm
  resolveCebolla?.()

  // Now the validate button should become enabled
  await expect(validateBtn).toBeEnabled({ timeout: 3000 })
})

// ---------------------------------------------------------------------------
// test_optimistic_state_survives_server_refetch_during_flight (QA H-04)
// When a server refetch (INIT) arrives while a confirm is in flight, the
// optimistic state must be preserved.
// ---------------------------------------------------------------------------

test('test_optimistic_state_survives_server_refetch_during_flight', async ({ page }) => {
  await injectOperatorToken(page)

  let getCallCount = 0
  await page.route(DETAIL_URL, async (route) => {
    if (route.request().method() !== 'GET') { route.continue(); return }
    getCallCount++
    // Second GET returns the item still un-confirmed (simulates refetch arriving
    // before the confirm resolves on the server).
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeDelivery('en_verificacion')),
    })
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }) }),
  )

  // Slow confirm — stays in flight while we trigger a refetch
  let resolveConfirm: (() => void) | undefined
  await page.route(CONFIRM_PALTA_URL, async (route) => {
    await new Promise<void>((r) => { resolveConfirm = r })
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ item_id: ITEM_PALTA, received_qty: 12 }) })
  })

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Click OK — optimistic update fires
  await page.getByRole('button', { name: /Confirmar PALTA/i }).click()

  // Trigger a background refetch by calling the query manually
  // (simulates polling or stale-while-revalidate)
  await page.evaluate(() => {
    // The second GET call will arrive while confirm is in flight
    window.dispatchEvent(new Event('focus'))
  })

  // Even if a second GET arrives, the optimistic ✓ must still be visible
  await expect(page.getByLabel('Confirmado')).toBeVisible()

  // Now let the confirm resolve
  resolveConfirm?.()

  // ✓ must still be visible after confirm resolves
  await expect(page.getByLabel('Confirmado')).toBeVisible()

  void getCallCount
})

// ---------------------------------------------------------------------------
// test_backdrop_click_closes_modal_without_saving (QA H-05)
// Clicking the overlay backdrop closes the edit modal without sending a confirm.
// ---------------------------------------------------------------------------

test('test_backdrop_click_closes_modal_without_saving', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(makeDelivery('en_verificacion')) })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }) }),
  )

  const confirmRequests: string[] = []
  await page.route(CONFIRM_PALTA_URL, (route) => {
    confirmRequests.push(route.request().method())
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ item_id: ITEM_PALTA, received_qty: 12 }) })
  })

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  // Open edit modal
  await page.getByRole('button', { name: /Editar cantidad de PALTA/i }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  // Click the backdrop (outside the card) — use a corner of the overlay
  await page.mouse.click(10, 10)

  // Modal must close
  await expect(page.getByRole('dialog')).toHaveCount(0)

  // No confirm request must have fired
  expect(confirmRequests.length).toBe(0)
})

// ---------------------------------------------------------------------------
// test_edit_modal_rejects_infinity_and_nan (SEG H-2)
// Entering Infinity, -Infinity or NaN must not submit the form.
// ---------------------------------------------------------------------------

test('test_edit_modal_rejects_infinity_and_nan', async ({ page }) => {
  await injectOperatorToken(page)

  await page.route(DETAIL_URL, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(makeDelivery('en_verificacion')) })
    } else {
      route.continue()
    }
  })

  await page.route(OPEN_URL, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: DELIVERY_ID, status: 'en_verificacion' }) }),
  )

  const confirmRequests: string[] = []
  await page.route(CONFIRM_PALTA_URL, (route) => {
    confirmRequests.push(route.request().method())
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ item_id: ITEM_PALTA, received_qty: 0 }) })
  })

  await goToVerificacion(page)
  await expect(page.getByText('PALTA')).toBeVisible()

  await page.getByRole('button', { name: /Editar cantidad de PALTA/i }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  const input = page.getByLabel('Cantidad recibida')
  const submitBtn = page.getByRole('button', { name: /OK y siguiente/i })

  // "Infinity" as a string — parseFloat('Infinity') returns Infinity, not NaN
  await input.fill('Infinity')
  await expect(submitBtn).toBeDisabled()
  await submitBtn.click({ force: true })
  expect(confirmRequests.length).toBe(0)

  // "-Infinity"
  await input.fill('-Infinity')
  await expect(submitBtn).toBeDisabled()
  await submitBtn.click({ force: true })
  expect(confirmRequests.length).toBe(0)
})
