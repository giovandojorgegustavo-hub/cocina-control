/**
 * Photo queue — offline-first local store backed by IndexedDB.
 *
 * Invariant: the camera flow is NON-BLOCKING. The operator never waits for
 * the server. Photos are captured, stored locally, and uploaded when the
 * network is available. The operator sees a success confirmation regardless.
 *
 * Upload flow for each queued entry:
 *  1. POST /delivery-orders            → get server id
 *  2. POST /delivery-orders/{id}/photo → upload blob as multipart
 *  3. On success: mark entry as 'done', store serverId
 *  4. On failure: exponential backoff (5 s → 30 s → 5 min), status = 'queued'
 */

import { apiClient } from './api'
import type { PhotoQueueEntry } from './types'

const DB_NAME = 'cocina-photo-queue'
const DB_VERSION = 1
const STORE_NAME = 'queue'

// ---------------------------------------------------------------------------
// Backoff schedule: 5 s, 30 s, 5 min, then 5 min indefinitely
// ---------------------------------------------------------------------------

const BACKOFF_MS = [5_000, 30_000, 5 * 60_000]

function nextBackoffMs(retries: number): number {
  const idx = Math.min(retries, BACKOFF_MS.length - 1)
  return BACKOFF_MS[idx]
}

// ---------------------------------------------------------------------------
// IndexedDB helpers
// ---------------------------------------------------------------------------

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)

    req.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'localId' })
      }
    }

    req.onsuccess = (event) => resolve((event.target as IDBOpenDBRequest).result)
    req.onerror = (event) => reject((event.target as IDBOpenDBRequest).error)
  })
}

function txStore(
  db: IDBDatabase,
  mode: IDBTransactionMode,
): IDBObjectStore {
  return db.transaction(STORE_NAME, mode).objectStore(STORE_NAME)
}

function idbGet(store: IDBObjectStore, key: string): Promise<PhotoQueueEntry | undefined> {
  return new Promise((resolve, reject) => {
    const req = store.get(key)
    req.onsuccess = () => resolve(req.result as PhotoQueueEntry | undefined)
    req.onerror = () => reject(req.error)
  })
}

function idbPut(store: IDBObjectStore, value: PhotoQueueEntry): Promise<void> {
  return new Promise((resolve, reject) => {
    const req = store.put(value)
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error)
  })
}

function idbGetAll(store: IDBObjectStore): Promise<PhotoQueueEntry[]> {
  return new Promise((resolve, reject) => {
    const req = store.getAll()
    req.onsuccess = () => resolve(req.result as PhotoQueueEntry[])
    req.onerror = () => reject(req.error)
  })
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Add a photo blob to the local queue.
 * Returns the localId that identifies this entry.
 */
export async function enqueuePhoto(blob: Blob, localId: string): Promise<string> {
  const db = await openDb()
  const entry: PhotoQueueEntry = {
    localId,
    blob,
    timestamp: new Date().toISOString(),
    status: 'queued',
    retries: 0,
  }
  const store = txStore(db, 'readwrite')
  await idbPut(store, entry)
  db.close()
  return localId
}

/**
 * Return the count of entries not yet successfully uploaded.
 */
export async function getQueueStatus(): Promise<{ pending: number }> {
  try {
    const db = await openDb()
    const store = txStore(db, 'readonly')
    const all = await idbGetAll(store)
    db.close()
    const pending = all.filter((e) => e.status !== 'done').length
    return { pending }
  } catch {
    return { pending: 0 }
  }
}

/**
 * Attempt to upload all queued (or failed) entries that are ready to retry.
 * Called at app boot and on the 'online' event.
 *
 * @param uploadFn - injectable for testing; defaults to the real API calls
 */
export async function flushQueue(
  uploadFn?: (entry: PhotoQueueEntry) => Promise<string>,
): Promise<void> {
  if (!navigator.onLine) return

  const db = await openDb()
  const readStore = txStore(db, 'readonly')
  const all = await idbGetAll(readStore)
  db.close()

  const now = Date.now()
  const ready = all.filter(
    (e) =>
      e.status !== 'done' &&
      e.status !== 'uploading' &&
      (e.nextRetryAt === undefined || e.nextRetryAt <= now),
  )

  for (const entry of ready) {
    await uploadEntry(entry, uploadFn)
  }
}

async function uploadEntry(
  entry: PhotoQueueEntry,
  uploadFn?: (entry: PhotoQueueEntry) => Promise<string>,
): Promise<void> {
  // Mark as uploading
  await updateEntry(entry.localId, { status: 'uploading' })

  try {
    let serverId: string
    if (uploadFn) {
      serverId = await uploadFn(entry)
    } else {
      serverId = await defaultUpload(entry)
    }
    await updateEntry(entry.localId, { status: 'done', serverId })
  } catch {
    const newRetries = entry.retries + 1
    await updateEntry(entry.localId, {
      status: 'queued',
      retries: newRetries,
      nextRetryAt: Date.now() + nextBackoffMs(newRetries),
    })
  }
}

async function defaultUpload(entry: PhotoQueueEntry): Promise<string> {
  // Step 1: create the order record
  const createRes = await apiClient.post<{ id: string }>('/delivery-orders')
  const serverId: string = createRes.data.id

  // Step 2: upload the photo as multipart
  const formData = new FormData()
  formData.append('file', entry.blob, 'photo.jpg')
  await apiClient.post(`/delivery-orders/${serverId}/photo`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

  return serverId
}

async function updateEntry(
  localId: string,
  patch: Partial<PhotoQueueEntry>,
): Promise<void> {
  try {
    const db = await openDb()
    const store = txStore(db, 'readwrite')
    const existing = await idbGet(store, localId)
    if (existing) {
      // Re-open the store in a new transaction after the get (IDB transactions
      // auto-commit after the last request completes)
      const db2 = await openDb()
      const store2 = txStore(db2, 'readwrite')
      await idbPut(store2, { ...existing, ...patch })
      db2.close()
    }
    db.close()
  } catch {
    // Best-effort: if IDB fails, the entry will just retry on next flush
  }
}

/**
 * Read all entries — used by the bandeja to show local-only photos.
 */
export async function getAllQueueEntries(): Promise<PhotoQueueEntry[]> {
  try {
    const db = await openDb()
    const store = txStore(db, 'readonly')
    const all = await idbGetAll(store)
    db.close()
    return all
  } catch {
    return []
  }
}
