import { test, expect } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const LOGIN_URL = '**/api/v1/auth/login'
const LOGOUT_URL = '**/api/v1/auth/logout'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Injects a token into sessionStorage so the app considers the user
 * authenticated without going through the login form.
 */
async function injectToken(page: import('@playwright/test').Page, token: string) {
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem(
      'cocina-auth',
      JSON.stringify({ state: { token: t }, version: 0 }),
    )
  }, token)
}

// ---------------------------------------------------------------------------
// Login form — success paths
// ---------------------------------------------------------------------------

test('login success redirects owner to /tablero', async ({ page }) => {
  const token = makeTestJwt('owner')

  await page.route(LOGIN_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ token, role: 'owner', user_id: 'test-user-id' }),
    })
  })

  await page.goto('/login')
  await page.getByLabel('Email').fill('dueno@cocina.com')
  await page.getByLabel('Contraseña').fill('password123')
  await page.getByRole('button', { name: 'Entrar' }).click()

  await expect(page).toHaveURL(/\/tablero/)
})

test('login success redirects operator to home /', async ({ page }) => {
  const token = makeTestJwt('operator')

  await page.route(LOGIN_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ token, role: 'operator', user_id: 'test-user-id' }),
    })
  })

  await page.goto('/login')
  await page.getByLabel('Email').fill('operario@cocina.com')
  await page.getByLabel('Contraseña').fill('password123')
  await page.getByRole('button', { name: 'Entrar' }).click()

  await expect(page).toHaveURL(/\/$/)
})

// ---------------------------------------------------------------------------
// Login form — error paths
// ---------------------------------------------------------------------------

test('login 401 shows generic credentials error', async ({ page }) => {
  await page.route(LOGIN_URL, (route) => {
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Invalid credentials' }),
    })
  })

  await page.goto('/login')
  await page.getByLabel('Email').fill('x@x.com')
  await page.getByLabel('Contraseña').fill('wrong')
  await page.getByRole('button', { name: 'Entrar' }).click()

  await expect(page.getByRole('alert')).toHaveText('Email o contraseña incorrectos')
})

test('login 429 shows rate limit message', async ({ page }) => {
  await page.route(LOGIN_URL, (route) => {
    route.fulfill({
      status: 429,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Too many requests' }),
    })
  })

  await page.goto('/login')
  await page.getByLabel('Email').fill('x@x.com')
  await page.getByLabel('Contraseña').fill('password')
  await page.getByRole('button', { name: 'Entrar' }).click()

  await expect(page.getByRole('alert')).toHaveText('Demasiados intentos, esperá un minuto')
})

// qa H-06 — unknown role from server shows error and clears token
test('login unknown role shows error and does not navigate', async ({ page }) => {
  const token = makeTestJwt('operator')

  await page.route(LOGIN_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      // 'admin' is not a valid role in this app
      body: JSON.stringify({ token, role: 'admin', user_id: 'test-user-id' }),
    })
  })

  await page.goto('/login')
  await page.getByLabel('Email').fill('admin@cocina.com')
  await page.getByLabel('Contraseña').fill('password123')
  await page.getByRole('button', { name: 'Entrar' }).click()

  // Should stay on /login and show error
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByRole('alert')).toBeVisible()

  // Token must be cleared from sessionStorage
  const stored = await page.evaluate(() => sessionStorage.getItem('cocina-auth'))
  const parsed = JSON.parse(stored ?? '{}') as { state?: { token?: string | null } }
  expect(parsed?.state?.token ?? null).toBeNull()
})

// qa H-07 — error clears when user modifies email or password
test('error banner clears when user edits email', async ({ page }) => {
  await page.route(LOGIN_URL, (route) => {
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Invalid credentials' }),
    })
  })

  await page.goto('/login')
  await page.getByLabel('Email').fill('x@x.com')
  await page.getByLabel('Contraseña').fill('wrong')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('alert')).toBeVisible()

  // Typing in email should clear the error
  await page.getByLabel('Email').pressSequentially('a')
  await expect(page.getByRole('alert')).not.toBeVisible()
})

// qa H-03 — email normalized before sending
test('login trims and lowercases email before sending', async ({ page }) => {
  const token = makeTestJwt('operator')
  let capturedBody: Record<string, unknown> | null = null

  await page.route(LOGIN_URL, async (route) => {
    capturedBody = JSON.parse(route.request().postData() ?? '{}') as Record<string, unknown>
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ token, role: 'operator', user_id: 'test-user-id' }),
    })
  })

  await page.goto('/login')
  await page.getByLabel('Email').fill('  Owner@Test.COM  ')
  await page.getByLabel('Contraseña').fill('password123')
  await page.getByRole('button', { name: 'Entrar' }).click()

  await expect(page).toHaveURL(/\/$/)
  expect(capturedBody?.email).toBe('owner@test.com')
})

// qa H-02 — double submit fires only one request
// Strategy: inject a slow response and use dispatchEvent to fire two submit
// events synchronously before any re-render. The ref guard (submitting.current)
// blocks the second call synchronously, before React can set loading=true.
// We verify that exactly one HTTP request was intercepted.
test('double submit only fires one request', async ({ page }) => {
  const token = makeTestJwt('operator')
  let requestCount = 0

  await page.route(LOGIN_URL, async (route) => {
    requestCount++
    // Keep the first request in flight long enough for the second dispatch to fire
    await new Promise((r) => setTimeout(r, 400))
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ token, role: 'operator', user_id: 'test-user-id' }),
    })
  })

  await page.goto('/login')
  await page.getByLabel('Email').fill('operario@cocina.com')
  await page.getByLabel('Contraseña').fill('password123')

  // Dispatch two submit events on the form synchronously from the browser.
  // This fires before any React re-render so loading state cannot block the second call —
  // only the ref guard can.
  await page.evaluate(() => {
    const form = document.querySelector('form')
    if (!form) throw new Error('form not found')
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  })

  await expect(page).toHaveURL(/\/$/)
  expect(requestCount).toBe(1)
})

// ---------------------------------------------------------------------------
// Token persistence
// ---------------------------------------------------------------------------

test('token survives reload (sessionStorage persists within same tab)', async ({ page }) => {
  const token = makeTestJwt('operator')

  await page.route(LOGIN_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ token, role: 'operator', user_id: 'test-user-id' }),
    })
  })

  await page.goto('/login')
  await page.getByLabel('Email').fill('operario@cocina.com')
  await page.getByLabel('Contraseña').fill('password123')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL(/\/$/)

  await page.reload()

  await expect(page).toHaveURL(/\/$/)
})

// qa H-01 — expired token is cleared and user redirected to /login
test('expired token in sessionStorage is cleared and user redirected to /login', async ({ page }) => {
  // Build a token already expired (exp = 1 second in the past)
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = btoa(
    JSON.stringify({
      sub: 'test-user-id',
      role: 'operator',
      exp: Math.floor(Date.now() / 1000) - 1,
      iat: Math.floor(Date.now() / 1000) - 3601,
    }),
  )
  const expiredToken = `${header}.${payload}.test-signature`

  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem(
      'cocina-auth',
      JSON.stringify({ state: { token: t }, version: 0 }),
    )
  }, expiredToken)

  await page.goto('/')

  // RequireAuth must detect expiry, clear it, and redirect
  await expect(page).toHaveURL(/\/login/)

  const stored = await page.evaluate(() => sessionStorage.getItem('cocina-auth'))
  const parsed = JSON.parse(stored ?? '{}') as { state?: { token?: string | null } }
  expect(parsed?.state?.token ?? null).toBeNull()
})

// ---------------------------------------------------------------------------
// 401 from protected route clears token and redirects to /login
// ---------------------------------------------------------------------------

// qa H-09 — renamed to be honest: tests the guard via store manipulation,
// not the axios interceptor itself.
test('clear token state redirects to /login via guard', async ({ page }) => {
  // Start with a valid token injected directly into sessionStorage
  const token = makeTestJwt('operator')
  await injectToken(page, token)

  // Simulate the axios 401 interceptor behavior: clear the token
  // (in a real app this fires when any protected request returns 401).
  // We replicate the effect by clearing the store from the browser context
  // and then navigating — RequireAuth will redirect to /login.
  await page.evaluate(() => {
    const stored = sessionStorage.getItem('cocina-auth')
    if (stored) {
      const parsed = JSON.parse(stored) as { state: { token: string | null }; version: number }
      parsed.state.token = null
      sessionStorage.setItem('cocina-auth', JSON.stringify(parsed))
    }
  })

  await page.goto('/')

  await expect(page).toHaveURL(/\/login/)
})

// ---------------------------------------------------------------------------
// Logout
// ---------------------------------------------------------------------------

// qa H-05 — logout sends Authorization header
test('logout clears token and redirects to /login', async ({ page }) => {
  const testToken = makeTestJwt('operator')
  let logoutAuthHeader: string | undefined

  await page.route(LOGOUT_URL, (route) => {
    logoutAuthHeader = route.request().headers()['authorization']
    return route.fulfill({ status: 204, body: '' })
  })

  // Inject a valid token so we land on Home
  await injectToken(page, testToken)
  await page.goto('/')

  // Verify we are on Home
  await expect(page.getByRole('button', { name: 'cerrar' })).toBeVisible()

  await page.getByRole('button', { name: 'cerrar' }).click()

  // Should land on /login and token should be gone
  await expect(page).toHaveURL(/\/login/)

  const stored = await page.evaluate(() => sessionStorage.getItem('cocina-auth'))
  const parsed = JSON.parse(stored ?? '{}') as { state?: { token?: string | null } }
  expect(parsed?.state?.token ?? null).toBeNull()

  // Authorization header must have been sent with the logout request
  expect(logoutAuthHeader).toBe(`Bearer ${testToken}`)
})

// ---------------------------------------------------------------------------
// Session isolation — new browser context
// ---------------------------------------------------------------------------

// qa H-10 — token in sessionStorage does not leak to a new browser context
test('token does not leak to a new browser context', async ({ browser, page }) => {
  const token = makeTestJwt('operator')

  await page.route('**/api/v1/auth/login', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ token, role: 'operator', user_id: 'test-user-id' }),
    })
  })

  // Log in within the current page context
  await page.goto('/login')
  await page.getByLabel('Email').fill('operario@cocina.com')
  await page.getByLabel('Contraseña').fill('password123')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL(/\/$/)

  // Open a completely new browser context (different sessionStorage)
  const newContext = await browser.newContext()
  const newPage = await newContext.newPage()
  await newPage.goto('/')

  // Must redirect to /login — no token leaked
  await expect(newPage).toHaveURL(/\/login/)

  await newContext.close()
})

// ---------------------------------------------------------------------------
// Offline before submit
// ---------------------------------------------------------------------------

test('offline before submit disables button', async ({ page, context }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('operario@cocina.com')
  await page.getByLabel('Contraseña').fill('password123')

  await context.setOffline(true)

  // Wait for the offline event to propagate
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeDisabled()

  await context.setOffline(false)
})
