import { test, expect } from '@playwright/test'

test('login page renders', async ({ page }) => {
  await page.goto('/login')
  await expect(page.locator('h1')).toHaveText('Cocina Control')
})

test('home redirects to login without token', async ({ page }) => {
  // Navigate to origin first so sessionStorage is accessible, then clear it
  await page.goto('/login')
  await page.evaluate(() => sessionStorage.clear())

  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)
})
