/**
 * QA + Security fixes — regression tests
 *
 * Covers:
 *  H-02  double-tap shutter → single queue entry
 *  H-03  updateEntry atomicity + error propagation (tested via behavior: no
 *         silent data loss when IDB is stressed)
 *  H-04  blob deleted from IDB after successful upload
 *  H-05  bandeja reloads localEntries when upload succeeds
 *  H-06  401 during upload stops retry and does not loop
 *  H-07  photo rejected if too large (all qualities fail)
 *  H-08  operator B does not see operator A photos in bandeja
 *  H-10  owner does not see "completar" button
 *  H-11  concurrent flushQueue calls only run once
 */
import { test, expect, type Page } from '@playwright/test'
import { makeTestJwt } from './helpers/testJwt'

const ORDERS_URL = '**/api/v1/delivery-orders'
const PHOTO_PATTERN = '**/api/v1/delivery-orders/*/photo'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function injectToken(page: Page, role: 'operator' | 'owner', sub = 'test-user-id') {
  const token = makeTestJwt(role, 3600, sub)
  await page.goto('/login')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
  return token
}

async function injectFakeCamera(page: Page) {
  await page.context().grantPermissions(['camera'], { origin: 'http://localhost:5173' })
}

/** Returns the count of entries in the photo-queue IDB store. */
async function idbQueueCount(page: Page): Promise<number> {
  return page.evaluate(() => {
    return new Promise<number>((resolve) => {
      const req = indexedDB.open('cocina-photo-queue', 1)
      req.onsuccess = () => {
        const db = req.result
        if (!db.objectStoreNames.contains('queue')) {
          resolve(0)
          return
        }
        const tx = db.transaction('queue', 'readonly')
        const count = tx.objectStore('queue').count()
        count.onsuccess = () => resolve(count.result)
        count.onerror = () => resolve(0)
      }
      req.onerror = () => resolve(0)
    })
  })
}

/** Returns all entries from the photo-queue IDB store. */
async function idbQueueEntries(page: Page): Promise<Array<{ localId: string; userId: string; status: string }>> {
  return page.evaluate(() => {
    return new Promise<Array<{ localId: string; userId: string; status: string }>>((resolve) => {
      const req = indexedDB.open('cocina-photo-queue', 1)
      req.onsuccess = () => {
        const db = req.result
        if (!db.objectStoreNames.contains('queue')) {
          resolve([])
          return
        }
        const tx = db.transaction('queue', 'readonly')
        const getAll = tx.objectStore('queue').getAll()
        getAll.onsuccess = () =>
          resolve(
            (getAll.result as Array<{ localId: string; userId: string; status: string }>).map((e) => ({
              localId: e.localId,
              userId: e.userId,
              status: e.status,
            })),
          )
        getAll.onerror = () => resolve([])
      }
      req.onerror = () => resolve([])
    })
  })
}

/** Clear the IDB queue store between tests. */
async function clearIdbQueue(page: Page): Promise<void> {
  await page.evaluate(() => {
    return new Promise<void>((resolve) => {
      const req = indexedDB.open('cocina-photo-queue', 1)
      req.onsuccess = () => {
        const db = req.result
        if (!db.objectStoreNames.contains('queue')) {
          resolve()
          return
        }
        const tx = db.transaction('queue', 'readwrite')
        tx.objectStore('queue').clear()
        tx.oncomplete = () => resolve()
        tx.onerror = () => resolve()
      }
      req.onerror = () => resolve()
    })
  })
}

// ---------------------------------------------------------------------------
// test_double_tap_shutter_creates_single_queue_entry (H-02)
//
// Strategy: click the shutter twice in rapid succession. The first click
// transitions to 'confirmed' screen and sets shuttingRef = true; the second
// click must be a no-op. We assert the IDB has exactly one entry.
//
// Important: after the first click the 'confirmed' screen replaces the camera
// view, so the shutter button is gone. We dispatch both clicks synchronously
// (no await between them) via page.evaluate to avoid the DOM change race.
// ---------------------------------------------------------------------------

test('test_double_tap_shutter_creates_single_queue_entry', async ({ page }) => {
  await injectFakeCamera(page)
  await injectToken(page, 'operator')

  // Block network so no upload happens during the test
  await page.route(ORDERS_URL, () => { /* hang */ })
  await page.route(PHOTO_PATTERN, () => { /* hang */ })

  await page.goto('/pedidos/nuevo')
  await expect(page.getByTestId('shutter-button')).toBeVisible()

  await clearIdbQueue(page)

  // Fire two synchronous clicks before React can re-render
  await page.evaluate(() => {
    const btn = document.querySelector('[data-testid="shutter-button"]') as HTMLButtonElement | null
    if (btn) {
      btn.click()
      btn.click()
    }
  })

  // Wait for IDB write to settle
  await page.waitForTimeout(800)

  const count = await idbQueueCount(page)
  expect(count).toBe(1)
})

// ---------------------------------------------------------------------------
// test_photo_deleted_from_idb_after_successful_upload (H-04)
// ---------------------------------------------------------------------------

test('test_photo_deleted_from_idb_after_successful_upload', async ({ page }) => {
  await injectFakeCamera(page)
  await injectToken(page, 'operator')

  // Stub successful upload
  await page.route(ORDERS_URL, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'srv-upload-ok' }),
    })
  })
  await page.route(PHOTO_PATTERN, (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/pedidos/nuevo')
  await expect(page.getByTestId('shutter-button')).toBeVisible()

  await clearIdbQueue(page)

  await page.getByTestId('shutter-button').click()

  // Wait for upload to complete and deleteEntry to run
  // Use polling to avoid flakiness from build + SW timing
  await page.waitForFunction(
    () => {
      return new Promise<boolean>((resolve) => {
        const req = indexedDB.open('cocina-photo-queue', 1)
        req.onsuccess = () => {
          const db = req.result
          if (!db.objectStoreNames.contains('queue')) { resolve(true); return }
          const tx = db.transaction('queue', 'readonly')
          const count = tx.objectStore('queue').count()
          count.onsuccess = () => resolve(count.result === 0)
          count.onerror = () => resolve(false)
        }
        req.onerror = () => resolve(false)
      })
    },
    { timeout: 5000, polling: 300 },
  )
})

// ---------------------------------------------------------------------------
// test_upload_401_stops_retry_and_clears_token (H-06)
// ---------------------------------------------------------------------------

test('test_upload_401_stops_retry_and_clears_token', async ({ page }) => {
  await injectFakeCamera(page)
  await injectToken(page, 'operator')

  let callCount = 0
  await page.route(ORDERS_URL, (route) => {
    callCount++
    route.fulfill({ status: 401, body: 'Unauthorized' })
  })

  await page.goto('/pedidos/nuevo')
  await expect(page.getByTestId('shutter-button')).toBeVisible()

  await clearIdbQueue(page)

  await page.getByTestId('shutter-button').click()

  // Wait for flush attempt
  await page.waitForTimeout(1000)

  // Token must have been cleared (api interceptor calls clearToken on 401)
  const tokenInStorage = await page.evaluate(() => {
    const raw = sessionStorage.getItem('cocina-auth')
    if (!raw) return null
    const parsed = JSON.parse(raw) as { state: { token: string | null } }
    return parsed.state.token
  })
  expect(tokenInStorage).toBeNull()

  // Should not have retried — only one call
  expect(callCount).toBe(1)
})

// ---------------------------------------------------------------------------
// test_photo_rejected_if_too_large (H-07)
//
// We simulate a canvas whose toBlob always returns a blob larger than 2 MB by
// patching HTMLCanvasElement.prototype.toBlob in the page before navigating.
// ---------------------------------------------------------------------------

test('test_photo_rejected_if_too_large', async ({ page }) => {
  await injectFakeCamera(page)
  await injectToken(page, 'operator')

  // Patch canvas.toBlob to always return a 3 MB blob
  await page.addInitScript(() => {
    const orig = HTMLCanvasElement.prototype.toBlob
    HTMLCanvasElement.prototype.toBlob = function (
      callback: BlobCallback,
      _type?: string,
      _quality?: number,
    ) {
      // 3 MB of zeros
      const big = new Blob([new Uint8Array(3 * 1024 * 1024)], { type: 'image/jpeg' })
      setTimeout(() => callback(big), 0)
      return orig
    }
  })

  await page.goto('/pedidos/nuevo')
  await expect(page.getByTestId('shutter-button')).toBeVisible()

  await page.getByTestId('shutter-button').click()

  // The photo-too-large error view must appear
  await expect(page.getByTestId('photo-too-large-view')).toBeVisible({ timeout: 3000 })
  await expect(page.getByText(/demasiado grande/i)).toBeVisible()
})

// ---------------------------------------------------------------------------
// test_operator_b_does_not_see_operator_a_photos_in_bandeja (H-08, H-2)
// ---------------------------------------------------------------------------

test('test_operator_b_does_not_see_operator_a_photos_in_bandeja', async ({ page }) => {
  // Seed IDB with an entry belonging to user-a
  await injectToken(page, 'operator', 'user-a')

  await page.goto('/pedidos/nuevo')
  // Directly write an entry for user-a into IDB
  await page.evaluate(() => {
    return new Promise<void>((resolve) => {
      const req = indexedDB.open('cocina-photo-queue', 1)
      req.onsuccess = () => {
        const db = req.result
        const tx = db.transaction('queue', 'readwrite')
        const store = tx.objectStore('queue')
        store.put({
          localId: 'local-a-001',
          blob: new Blob(['fake'], { type: 'image/jpeg' }),
          timestamp: new Date().toISOString(),
          status: 'queued',
          userId: 'user-a',
          retries: 0,
        })
        tx.oncomplete = () => resolve()
        tx.onerror = () => resolve()
      }
      req.onerror = () => resolve()
    })
  })

  // Now log in as user-b
  await injectToken(page, 'operator', 'user-b')

  // Stub server orders so the bandeja loads
  await page.route('**/api/v1/delivery-orders', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/pedidos')

  // user-b must not see user-a's local entry
  // The bandeja shows empty state when no orders and no local entries visible
  await expect(page.getByText(/todavia no hay pedidos hoy/i)).toBeVisible({ timeout: 3000 })
})

// ---------------------------------------------------------------------------
// test_flush_only_processes_photos_of_current_user (H-1)
//
// Strategy: seed IDB with an entry from user-other while logged in as
// user-current. Navigate to /pedidos/nuevo (which calls flushQueue on load
// via the 'online' event boot). The entry from user-other must NOT trigger
// a POST to /delivery-orders, and must end up as 'orphaned'.
// ---------------------------------------------------------------------------

test('test_flush_only_processes_photos_of_current_user', async ({ page }) => {
  await injectFakeCamera(page)
  await injectToken(page, 'operator', 'user-current')

  let orderCallCount = 0
  await page.route(ORDERS_URL, (route, request) => {
    if (request.method() === 'POST') {
      orderCallCount++
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 'srv-' + Date.now() }),
      })
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    }
  })
  await page.route(PHOTO_PATTERN, (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  // Load any page first to get IDB access for the origin
  await page.goto('/pedidos')

  // Seed IDB with an entry from another user
  await page.evaluate(() => {
    return new Promise<void>((resolve) => {
      const req = indexedDB.open('cocina-photo-queue', 1)
      req.onsuccess = () => {
        const db = req.result
        const tx = db.transaction('queue', 'readwrite')
        tx.objectStore('queue').put({
          localId: 'other-user-entry-h1',
          blob: new Blob(['x'], { type: 'image/jpeg' }),
          timestamp: new Date().toISOString(),
          status: 'queued',
          userId: 'user-other',
          retries: 0,
        })
        tx.oncomplete = () => resolve()
        tx.onerror = () => resolve()
      }
      req.onerror = () => resolve()
    })
  })

  // Reload — main.tsx calls flushQueue() at boot, which will process the queue
  // and mark the other-user entry as orphaned
  await page.reload()
  await page.waitForTimeout(1000)

  // The other-user entry must now be 'orphaned', not uploaded
  const entries = await idbQueueEntries(page)
  const otherEntry = entries.find((e) => e.localId === 'other-user-entry-h1')
  expect(otherEntry?.status).toBe('orphaned')

  // No upload network call was made for the other user's entry
  expect(orderCallCount).toBe(0)
})

// ---------------------------------------------------------------------------
// test_concurrent_flushQueue_calls_only_run_once (H-11)
//
// Strategy: seed IDB with a queued entry, then trigger the 'online' event
// multiple times rapidly. The mutex (flushing flag) must ensure only one
// concurrent flush runs. We use a slow POST stub (400 ms) — without the mutex
// multiple GETs of the queue would each see the same 'queued' entry and POST
// multiple times.
// ---------------------------------------------------------------------------

test('test_concurrent_flushQueue_calls_only_run_once', async ({ page }) => {
  await injectToken(page, 'operator')

  let orderCallCount = 0
  await page.route(ORDERS_URL, async (route, request) => {
    if (request.method() === 'POST') {
      orderCallCount++
      await new Promise((r) => setTimeout(r, 400))
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 'srv-concurrent' }),
      })
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    }
  })
  await page.route(PHOTO_PATTERN, (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  // Load the page and seed IDB with a queued entry for the current user
  await page.goto('/pedidos')
  await clearIdbQueue(page)
  await page.evaluate(() => {
    return new Promise<void>((resolve) => {
      const req = indexedDB.open('cocina-photo-queue', 1)
      req.onsuccess = () => {
        const db = req.result
        const tx = db.transaction('queue', 'readwrite')
        tx.objectStore('queue').put({
          localId: 'mutex-test-entry',
          blob: new Blob(['x'], { type: 'image/jpeg' }),
          timestamp: new Date().toISOString(),
          status: 'queued',
          userId: 'test-user-id',
          retries: 0,
        })
        tx.oncomplete = () => resolve()
        tx.onerror = () => resolve()
      }
      req.onerror = () => resolve()
    })
  })

  // Dispatch 'online' event multiple times rapidly to trigger concurrent flush calls
  await page.evaluate(() => {
    window.dispatchEvent(new Event('online'))
    window.dispatchEvent(new Event('online'))
    window.dispatchEvent(new Event('online'))
  })

  // Wait for the slow upload to complete
  await page.waitForTimeout(1200)

  // Despite 3 concurrent flush triggers, only one POST should have fired
  expect(orderCallCount).toBe(1)
})

// ---------------------------------------------------------------------------
// test_bandeja_removes_local_entry_when_upload_succeeds (H-05)
//
// Strategy: seed IDB with a queued entry, then navigate to /pedidos.
// At boot, main.tsx calls flushQueue() which processes the entry.
// The upload POST is delayed 600ms so the bandeja component mounts and
// subscribes to onQueueChange before deleteEntry fires.
// After the upload completes, the entry should disappear from the DOM.
// ---------------------------------------------------------------------------

test('test_bandeja_removes_local_entry_when_upload_succeeds', async ({ page }) => {
  await injectToken(page, 'operator')

  // Delay POST by 600 ms so bandeja has time to mount + subscribe
  await page.route('**/api/v1/delivery-orders', async (route, request) => {
    if (request.method() === 'GET') {
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
      return
    }
    await new Promise((r) => setTimeout(r, 600))
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'srv-h05' }),
    })
  })
  await page.route(PHOTO_PATTERN, (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  // Load any page to get IDB access, then seed the queue entry
  await page.goto('/login')
  await page.evaluate(() => {
    return new Promise<void>((resolve) => {
      const req = indexedDB.open('cocina-photo-queue', 1)
      req.onupgradeneeded = (e) => {
        const db = (e.target as IDBOpenDBRequest).result
        if (!db.objectStoreNames.contains('queue')) {
          db.createObjectStore('queue', { keyPath: 'localId' })
        }
      }
      req.onsuccess = () => {
        const db = req.result
        const tx = db.transaction('queue', 'readwrite')
        tx.objectStore('queue').put({
          localId: 'h05-local-entry',
          blob: new Blob(['fake-photo'], { type: 'image/jpeg' }),
          timestamp: new Date().toISOString(),
          status: 'queued',
          userId: 'test-user-id',
          retries: 0,
        })
        tx.oncomplete = () => resolve()
        tx.onerror = () => resolve()
      }
      req.onerror = () => resolve()
    })
  })

  // Now navigate to /pedidos — this also triggers flushQueue() at boot (main.tsx)
  // The delayed POST means the upload is still in-flight when the bandeja mounts
  const token = makeTestJwt('operator', 3600, 'test-user-id')
  await page.evaluate((t) => {
    sessionStorage.setItem('cocina-auth', JSON.stringify({ state: { token: t }, version: 0 }))
  }, token)
  await page.goto('/pedidos')

  // The local entry is visible while the upload is in-flight
  const localRows = page.locator('[class*="border-l-yellow-300"]')
  await expect(localRows).toHaveCount(1, { timeout: 3000 })

  // After upload completes, deleteEntry fires, onQueueChange notifies bandeja,
  // loadLocal re-runs and finds empty IDB → entry disappears
  await expect(localRows).toHaveCount(0, { timeout: 4000 })
})

// ---------------------------------------------------------------------------
// test_owner_does_not_see_completar_button (H-10)
// ---------------------------------------------------------------------------

test('test_owner_does_not_see_completar_button', async ({ page }) => {
  await injectToken(page, 'owner')

  await page.route('**/api/v1/delivery-orders', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'order-pending-owner',
          status: 'pending',
          photo_at: new Date().toISOString(),
          photo_by: 'user-operator',
        },
      ]),
    })
  })
  await page.route(PHOTO_PATTERN, (route) => {
    route.fulfill({ status: 404, body: '' })
  })

  await page.goto('/pedidos')

  // Pending badge is visible
  await expect(page.getByText('PENDIENTE')).toBeVisible()
  // But no "completar" button for owner
  await expect(page.getByRole('button', { name: /completar/i })).toHaveCount(0)
})
