import { useState, useCallback } from 'react'

export type PeriodPreset = 'today' | '7d' | '30d' | 'custom'

/**
 * Returns the current date in Argentina (UTC-3) as YYYY-MM-DD.
 * Uses a fixed offset — Argentina does not observe DST.
 */
function todayArgentina(): string {
  const OFFSET_MS = 3 * 60 * 60 * 1000
  const local = new Date(Date.now() - OFFSET_MS)
  const y = local.getUTCFullYear()
  const m = String(local.getUTCMonth() + 1).padStart(2, '0')
  const d = String(local.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function addDays(base: string, delta: number): string {
  const OFFSET_MS = 3 * 60 * 60 * 1000
  // Parse the date as Argentina midnight
  const [y, m, d] = base.split('-').map(Number)
  const utcMidnight = Date.UTC(y, m - 1, d) + OFFSET_MS
  const shifted = new Date(utcMidnight + delta * 24 * 60 * 60 * 1000 - OFFSET_MS)
  const yr = shifted.getUTCFullYear()
  const mo = String(shifted.getUTCMonth() + 1).padStart(2, '0')
  const dy = String(shifted.getUTCDate()).padStart(2, '0')
  return `${yr}-${mo}-${dy}`
}

/**
 * Converts an ISO 8601 UTC timestamp to a YYYY-MM-DD date string in UTC-3.
 */
function isoToArgentinaDate(isoUtc: string): string {
  const OFFSET_MS = 3 * 60 * 60 * 1000
  const local = new Date(new Date(isoUtc).getTime() - OFFSET_MS)
  const y = local.getUTCFullYear()
  const m = String(local.getUTCMonth() + 1).padStart(2, '0')
  const d = String(local.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function rangeFor(
  preset: PeriodPreset,
  custom: { from: string; to: string },
  lastInventoryAt: string | null,
) {
  const today = todayArgentina()
  switch (preset) {
    case 'today':
      // Wireframe: "HOY = desde el último inventario hasta ahora."
      // If last_inventory_at is known, use its date as the from boundary.
      // Fallback: from=today when no inventory has been recorded yet.
      return {
        from: lastInventoryAt ? isoToArgentinaDate(lastInventoryAt) : today,
        to: today,
      }
    case '7d':
      return { from: addDays(today, -6), to: today }
    case '30d':
      return { from: addDays(today, -29), to: today }
    case 'custom':
      return { from: custom.from, to: custom.to }
  }
}

interface PeriodState {
  preset: PeriodPreset
  from: string
  to: string
  customFrom: string
  customTo: string
  setPreset: (p: PeriodPreset) => void
  setCustomFrom: (v: string) => void
  setCustomTo: (v: string) => void
}

export function usePeriod(
  defaultPreset: PeriodPreset = '7d',
  lastInventoryAt: string | null = null,
): PeriodState {
  const today = todayArgentina()
  const [preset, setPresetState] = useState<PeriodPreset>(defaultPreset)
  const [customFrom, setCustomFrom] = useState<string>(addDays(today, -6))
  const [customTo, setCustomTo] = useState<string>(today)

  const setPreset = useCallback((p: PeriodPreset) => {
    setPresetState(p)
  }, [])

  const range = rangeFor(preset, { from: customFrom, to: customTo }, lastInventoryAt)

  return {
    preset,
    from: range.from,
    to: range.to,
    customFrom,
    customTo,
    setPreset,
    setCustomFrom,
    setCustomTo,
  }
}
