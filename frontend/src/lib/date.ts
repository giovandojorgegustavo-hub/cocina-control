/**
 * Format an ISO 8601 UTC timestamp as a human-readable relative date
 * using UTC-3 (Argentina) as the local timezone.
 *
 * Rules:
 *  - Same calendar day (UTC-3)  → "hoy HH:mm"
 *  - Previous calendar day      → "ayer HH:mm"
 *  - 2–6 days ago               → "hace N días"
 *  - 7+ days ago                → "DD/MM HH:mm"
 */
export function formatRelativeDate(iso: string, now = new Date()): string {
  const date = new Date(iso)

  // Convert both dates to UTC-3 by subtracting 3 hours in ms
  const OFFSET_MS = 3 * 60 * 60 * 1000

  const localDate = new Date(date.getTime() - OFFSET_MS)
  const localNow = new Date(now.getTime() - OFFSET_MS)

  // Calendar day boundaries in UTC-3
  const dateDay = new Date(
    Date.UTC(localDate.getUTCFullYear(), localDate.getUTCMonth(), localDate.getUTCDate()),
  )
  const nowDay = new Date(
    Date.UTC(localNow.getUTCFullYear(), localNow.getUTCMonth(), localNow.getUTCDate()),
  )

  const diffDays = Math.round((nowDay.getTime() - dateDay.getTime()) / (24 * 60 * 60 * 1000))

  const hh = String(localDate.getUTCHours()).padStart(2, '0')
  const mm = String(localDate.getUTCMinutes()).padStart(2, '0')
  const timeStr = `${hh}:${mm}`

  if (diffDays === 0) return `hoy ${timeStr}`
  if (diffDays === 1) return `ayer ${timeStr}`
  if (diffDays <= 6) return `hace ${diffDays} días`

  const dd = String(localDate.getUTCDate()).padStart(2, '0')
  const mo = String(localDate.getUTCMonth() + 1).padStart(2, '0')
  return `${dd}/${mo} ${timeStr}`
}
