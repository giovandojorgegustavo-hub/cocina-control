/**
 * base-path.spec.ts
 *
 * Verifies that the current build (base '/') produces a manifest with the
 * expected start_url and scope, confirming the default behaviour is unchanged
 * after the base-path feature was added.
 *
 * The manifest is read directly from dist/ on disk rather than over HTTP,
 * because vite preview may not serve manifest.webmanifest on all platforms
 * (a pre-existing environment limitation also affecting manifest.spec.ts).
 *
 * The /interno/ base-path build is verified separately by the node script at
 * tests/scripts/verify-base-build.mjs (npm run verify:base-build).
 */
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const distDir = resolve(__dirname, '../dist')

test('manifest start_url and scope are "/" in a root build', () => {
  // Read the manifest from the dist/ directory produced by the current build.
  // This avoids HTTP-serving inconsistencies with vite preview.
  const raw = readFileSync(resolve(distDir, 'manifest.webmanifest'), 'utf-8')
  const manifest = JSON.parse(raw) as Record<string, unknown>

  // Default build: both fields must be '/'.
  expect(manifest.start_url).toBe('/')
  expect(manifest.scope).toBe('/')
})

test('index.html does not hard-code absolute /api/ references', async ({ request }) => {
  // Ensures no stray /api/ paths were baked in as absolute strings in the
  // HTML entry point (asset URLs come from JS modules, not the HTML itself,
  // so this is a quick sanity guard).
  const response = await request.get('/')
  expect(response.status()).toBe(200)

  const html = await response.text()

  // The HTML should not contain a literal href="/api/ or src="/api/ — all API
  // calls are made from JS at runtime, not referenced from the HTML directly.
  expect(html).not.toMatch(/(?:href|src)="\/api\//)
})
