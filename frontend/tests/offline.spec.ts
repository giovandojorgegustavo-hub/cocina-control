import { test, expect } from '@playwright/test'

test('offline banner appears when connection is lost', async ({ page, context }) => {
  await page.goto('/login')
  await context.setOffline(true)
  await expect(page.getByText(/sin conexi/i)).toBeVisible()
  await context.setOffline(false)
  await expect(page.getByText(/sin conexi/i)).toBeHidden()
})
