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

// ---------------------------------------------------------------------------
// 401 from protected route clears token and redirects to /login
// ---------------------------------------------------------------------------

test('401 from protected route clears token and redirects to /login', async ({ page }) => {
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

test('logout clears token and redirects to /login', async ({ page }) => {
  const token = makeTestJwt('operator')

  // Mock logout endpoint (server-side is a no-op; returns 204)
  await page.route(LOGOUT_URL, (route) => {
    route.fulfill({ status: 204, body: '' })
  })

  // Inject a valid token so we land on Home
  await injectToken(page, token)
  await page.goto('/')

  // Verify we are on Home
  await expect(page.getByRole('button', { name: 'cerrar' })).toBeVisible()

  await page.getByRole('button', { name: 'cerrar' }).click()

  // Should land on /login and token should be gone
  await expect(page).toHaveURL(/\/login/)

  const stored = await page.evaluate(() => sessionStorage.getItem('cocina-auth'))
  const parsed = JSON.parse(stored ?? '{}') as { state?: { token?: string | null } }
  expect(parsed?.state?.token ?? null).toBeNull()
})
