/**
 * AuthImg — renders an image that requires an Authorization header.
 *
 * <img> cannot send custom headers, so we fetch the binary with the
 * JWT and create a local blob URL. The blob URL is revoked on unmount
 * to avoid memory leaks.
 *
 * While loading, renders the placeholder. On error, keeps the placeholder.
 */
import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'

interface AuthImgProps {
  /** The /api/v1/... URL that requires auth */
  src: string
  alt: string
  className?: string
  'data-testid'?: string
}

const PLACEHOLDER =
  'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"%3E%3Crect width="64" height="64" fill="%23d1d5db"/%3E%3C/svg%3E'

export function AuthImg({ src, alt, className, 'data-testid': testId }: AuthImgProps) {
  const token = useAuth((s) => s.token)
  const [objectUrl, setObjectUrl] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    let blobUrl: string | null = null

    async function load() {
      try {
        const headers: HeadersInit = {}
        if (token) {
          headers['Authorization'] = `Bearer ${token}`
        }
        const res = await fetch(src, { headers, signal: controller.signal })
        if (!res.ok) return
        const blob = await res.blob()
        blobUrl = URL.createObjectURL(blob)
        setObjectUrl(blobUrl)
      } catch (err) {
        // AbortError is expected on unmount — ignore it. Other errors fall back
        // to the placeholder silently.
        if (err instanceof DOMException && err.name === 'AbortError') return
      }
    }

    void load()

    return () => {
      controller.abort()
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }
    // Re-fetch if the src or token changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, token])

  return (
    <img
      src={objectUrl ?? PLACEHOLDER}
      alt={alt}
      className={className}
      data-testid={testId}
    />
  )
}
