/**
 * verify-base-build.mjs
 *
 * Builds the frontend with VITE_BASE_PATH=/interno/ into a temporary output
 * directory (dist-interno) so the normal dist/ is never overwritten, then
 * verifies that:
 *   1. manifest.webmanifest has start_url and scope set to /interno/
 *   2. index.html asset references are prefixed with /interno/
 *
 * Run via:  node tests/scripts/verify-base-build.mjs
 * Or:       npm run verify:base-build   (from frontend/)
 *
 * The temp directory is deleted after the check regardless of the outcome.
 * Exit code 0 = all assertions passed; non-zero = failure.
 */

import { execSync } from 'node:child_process'
import { readFileSync, rmSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(__dirname, '../../')
const outDir = resolve(frontendDir, 'dist-interno')

function fail(message) {
  console.error(`FAIL: ${message}`)
  process.exit(1)
}

function cleanup() {
  if (existsSync(outDir)) {
    rmSync(outDir, { recursive: true, force: true })
    console.log('Cleaned up dist-interno/')
  }
}

// Always clean up on exit (including errors).
process.on('exit', cleanup)
process.on('SIGINT', () => process.exit(1))
process.on('SIGTERM', () => process.exit(1))

console.log('Building with VITE_BASE_PATH=/interno/ --outDir dist-interno ...')

try {
  execSync('VITE_BASE_PATH=/interno/ npx vite build --outDir dist-interno', {
    cwd: frontendDir,
    stdio: 'inherit',
    env: { ...process.env, VITE_BASE_PATH: '/interno/' },
  })
} catch {
  fail('vite build failed')
}

// 1. Verify manifest.webmanifest
const manifestPath = resolve(outDir, 'manifest.webmanifest')
if (!existsSync(manifestPath)) {
  fail(`manifest.webmanifest not found at ${manifestPath}`)
}

let manifest
try {
  manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'))
} catch {
  fail('Could not parse manifest.webmanifest as JSON')
}

if (manifest.start_url !== '/interno/') {
  fail(`manifest start_url: expected "/interno/", got "${manifest.start_url}"`)
}
console.log('manifest.start_url = /interno/ — OK')

if (manifest.scope !== '/interno/') {
  fail(`manifest scope: expected "/interno/", got "${manifest.scope}"`)
}
console.log('manifest.scope = /interno/ — OK')

// 2. Verify index.html has /interno/ prefixed assets
const indexPath = resolve(outDir, 'index.html')
if (!existsSync(indexPath)) {
  fail(`index.html not found at ${indexPath}`)
}

const indexHtml = readFileSync(indexPath, 'utf-8')

// All script/link src and href attributes pointing to assets should include the base.
if (!indexHtml.includes('/interno/')) {
  fail('index.html does not contain any /interno/ references — assets are not prefixed')
}
console.log('index.html contains /interno/ asset references — OK')

// Double-check there are no bare /assets/ references (would indicate base is missing).
// Note: if there ARE /interno/assets/... references, they will also match /assets/ as a
// substring, so we look for a href/src="/assets/ or src="/assets/ pattern specifically.
const bareAsset = /(?:href|src)="\/assets\//
if (bareAsset.test(indexHtml)) {
  fail('index.html has bare /assets/ reference(s) without the /interno/ prefix')
}
console.log('No bare /assets/ references found — OK')

console.log('\nAll assertions passed. Build with base=/interno/ is correct.')
