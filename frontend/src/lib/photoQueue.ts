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
 *  3. On success: delete entry from IDB (it served its purpose)
 *  4. On failure: exponential backoff (5 s → 30 s → 5 min), status = 'queued'
 *
 * Security: each entry carries the userId of the capturing operator.
 * flushQueue only processes entries belonging to the currently logged-in user.
 * Entries from other users are left as 'orphaned'.
 */

import { apiClient } from './api'
import { useAuth, decodeToken } from './auth'
import type { PhotoQueueEntry } from './types'

const DB_NAME = 'cocina-photo-queue'
const DB_VERSION = 1
const STORE = 'queue'

// ---------------------------------------------------------------------------
// Backoff schedule: 5 s, 30 s, 5 min, then 5 min indefinitely
// ---------------------------------------------------------------------------

const BACKOFF_MS = [5_000, 30_000, 5 * 60_000]

function nextBackoffMs(retries: number): number {
  const idx = Math.min(retries, BACKOFF_MS.length - 1)
  return BACKOFF_MS[idx]
}

// ---------------------------------------------------------------------------
// Queue-change listener bus — used by BandejaPedidos to react to uploads
// ---------------------------------------------------------------------------

const listeners = new Set<() => void>()

export function onQueueChange(cb: () => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

function notify(): void {
  listeners.forEach((cb) => cb())
}

// ---------------------------------------------------------------------------
// IndexedDB helpers
// ---------------------------------------------------------------------------

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)

    req.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'localId' })
      }
    }

    req.onsuccess = (event) => resolve((event.target as IDBOpenDBRequest).result)
    req.onerror = (event) => reject((event.target as IDBOpenDBRequest).error)
  })
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Add a photo blob to the local queue.
 * The userId is read from the current auth state at capture time.
 * Returns the localId that identifies this entry.
 */
export async function enqueuePhoto(blob: Blob, localId: string): Promise<string> {
  const token = useAuth.getState().token
  const payload = token ? decodeToken(token) : null
  const userId = payload?.sub ?? 'unknown'

  const db = await openDb()
  const entry: PhotoQueueEntry = {
    localId,
    blob,
    timestamp: new Date().toISOString(),
    status: 'queued',
    userId,
    retries: 0,
  }

  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    const store = tx.objectStore(STORE)
    const req = store.put(entry)
    req.onerror = () => reject(req.error)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })

  db.close()
  notify()
  return localId
}

/**
 * Delete an entry by localId. Called after successful upload.
 */
export async function deleteEntry(localId: string): Promise<void> {
  const db = await openDb()

  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    const store = tx.objectStore(STORE)
    const req = store.delete(localId)
    req.onerror = () => reject(req.error)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })

  db.close()
  notify()
}

/**
 * Atomically patch an existing entry. get + put in the same transaction.
 * Throws if the IDB operation fails (no silent swallowing).
 */
export async function updateEntry(
  localId: string,
  patch: Partial<PhotoQueueEntry>,
): Promise<void> {
  const db = await openDb()

  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    const store = tx.objectStore(STORE)
    const getReq = store.get(localId)
    getReq.onsuccess = () => {
      const existing = getReq.result as PhotoQueueEntry | undefined
      if (!existing) {
        // Entry was already deleted — treat as a no-op
        return
      }
      const putReq = store.put({ ...existing, ...patch })
      putReq.onerror = () => reject(putReq.error)
    }
    getReq.onerror = () => reject(getReq.error)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })

  db.close()
}

/**
 * Return the count of entries not yet successfully uploaded.
 * 'done' and 'orphaned' entries are excluded from the pending count.
 */
export async function getQueueStatus(): Promise<{ pending: number }> {
  try {
    const db = await openDb()
    const all = await idbGetAll(db)
    db.close()
    const pending = all.filter(
      (e) => e.status !== 'done' && e.status !== 'orphaned',
    ).length
    return { pending }
  } catch {
    return { pending: 0 }
  }
}

// ---------------------------------------------------------------------------
// Flush — mutex-guarded, user-scoped
// ---------------------------------------------------------------------------

let flushing = false

/**
 * Attempt to upload all queued (or failed) entries that are ready to retry
 * and belong to the currently logged-in user.
 * Called at app boot and on the 'online' event.
 *
 * @param uploadFn - injectable for testing; defaults to the real API calls
 */
export async function flushQueue(
  uploadFn?: (entry: PhotoQueueEntry) => Promise<string>,
): Promise<void> {
  if (flushing) return
  if (!navigator.onLine) return

  const token = useAuth.getState().token
  if (!token) return

  const currentPayload = decodeToken(token)
  if (!currentPayload) return

  const currentUserId = currentPayload.sub

  flushing = true
  try {
    const db = await openDb()
    const all = await idbGetAll(db)
    db.close()

    const now = Date.now()
    const ready = all.filter(
      (e) =>
        e.status !== 'done' &&
        e.status !== 'uploading' &&
        e.status !== 'orphaned' &&
        (e.nextRetryAt === undefined || e.nextRetryAt <= now),
    )

    for (const entry of ready) {
      // Security: skip entries from other users — mark as orphaned
      if (entry.userId !== currentUserId) {
        try {
          await updateEntry(entry.localId, { status: 'orphaned' })
        } catch (err) {
          console.error('[photoQueue] Failed to mark entry as orphaned:', entry.localId, err)
        }
        continue
      }

      try {
        await uploadEntry(entry, uploadFn)
      } catch (err) {
        console.error('[photoQueue] uploadEntry failed for', entry.localId, err)
        // Don't continue looping on unexpected errors from uploadEntry itself
      }
    }
  } finally {
    flushing = false
  }
}

async function uploadEntry(
  entry: PhotoQueueEntry,
  uploadFn?: (entry: PhotoQueueEntry) => Promise<string>,
): Promise<void> {
  await updateEntry(entry.localId, { status: 'uploading' })

  try {
    let serverId: string
    if (uploadFn) {
      serverId = await uploadFn(entry)
    } else {
      serverId = await defaultUpload(entry)
    }
    // Delete after successful upload — blob served its purpose
    await deleteEntry(entry.localId)
    // Suppress unused variable warning; serverId is returned by the API but
    // we don't need it after deleting the entry.
    void serverId
  } catch (err: unknown) {
    // If the server rejected with 401, don't schedule a retry — leave as queued
    // but with a far-future nextRetryAt so it won't loop. The api interceptor
    // already called clearToken(), so the next flush will bail at the token check.
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 401) {
      console.warn('[photoQueue] 401 during upload — stopping retry for', entry.localId)
      // nextRetryAt = far future (effectively orphaned until re-login)
      await updateEntry(entry.localId, {
        status: 'queued',
        retries: entry.retries + 1,
        nextRetryAt: Date.now() + 24 * 60 * 60_000, // 24 h
      })
      return
    }

    const newRetries = entry.retries + 1
    try {
      await updateEntry(entry.localId, {
        status: 'queued',
        retries: newRetries,
        nextRetryAt: Date.now() + nextBackoffMs(newRetries),
      })
    } catch (updateErr) {
      console.error('[photoQueue] Failed to update retry state for', entry.localId, updateErr)
    }
  }
}

async function defaultUpload(entry: PhotoQueueEntry): Promise<string> {
  // Step 1: create the order record (or reuse existing serverId if step 1 succeeded
  // on a previous attempt but step 2 failed)
  let serverId = entry.serverId
  if (!serverId) {
    const createRes = await apiClient.post<{ id: string }>('/delivery-orders')
    serverId = createRes.data.id
    // Persist serverId so a retry skips step 1
    await updateEntry(entry.localId, { serverId })
  }

  // Step 2: upload the photo as multipart
  const formData = new FormData()
  formData.append('file', entry.blob, 'photo.jpg')
  await apiClient.post(`/delivery-orders/${serverId}/photo`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

  return serverId
}

// ---------------------------------------------------------------------------
// Size validation helper — called before enqueue
// Max 2 MB. Re-compresses at lower quality if needed.
// ---------------------------------------------------------------------------

const MAX_BLOB_BYTES = 2 * 1024 * 1024 // 2 MB

/**
 * Compress a canvas to a JPEG blob within the size limit.
 * Tries quality 0.8, 0.6, 0.4 in order.
 * Returns null if the blob is still too large after all attempts.
 */
export function compressCanvas(
  canvas: HTMLCanvasElement,
  onResult: (blob: Blob | null, tooLarge: boolean) => void,
): void {
  const qualities = [0.8, 0.6, 0.4]
  let attempt = 0

  function tryNext(): void {
    if (attempt >= qualities.length) {
      onResult(null, true)
      return
    }
    const q = qualities[attempt++]
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          onResult(null, false)
          return
        }
        if (blob.size > MAX_BLOB_BYTES) {
          tryNext()
        } else {
          onResult(blob, false)
        }
      },
      'image/jpeg',
      q,
    )
  }

  tryNext()
}

// ---------------------------------------------------------------------------
// Read helpers
// ---------------------------------------------------------------------------

function idbGetAll(db: IDBDatabase): Promise<PhotoQueueEntry[]> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly')
    const store = tx.objectStore(STORE)
    const req = store.getAll()
    req.onsuccess = () => resolve(req.result as PhotoQueueEntry[])
    req.onerror = () => reject(req.error)
  })
}

/**
 * Read all entries — used by the bandeja to show local-only photos.
 */
export async function getAllQueueEntries(): Promise<PhotoQueueEntry[]> {
  try {
    const db = await openDb()
    const all = await idbGetAll(db)
    db.close()
    return all
  } catch {
    return []
  }
}
