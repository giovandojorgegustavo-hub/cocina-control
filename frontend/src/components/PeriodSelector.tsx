import type { PeriodPreset } from '../lib/usePeriod'

interface PeriodSelectorProps {
  preset: PeriodPreset
  customFrom: string
  customTo: string
  onPreset: (p: PeriodPreset) => void
  onCustomFrom: (v: string) => void
  onCustomTo: (v: string) => void
  lastInventoryAt: string | null
}

const PRESETS: { id: PeriodPreset; label: string }[] = [
  { id: 'today', label: 'HOY' },
  { id: '7d', label: '7 dias' },
  { id: '30d', label: '30 dias' },
  { id: 'custom', label: 'personalizado' },
]

/**
 * Format last_inventory_at as human-readable relative label.
 * Uses UTC-3 offset; only displays date, not relative ("ayer 23:15" style).
 */
function formatLastInventory(iso: string): string {
  const OFFSET_MS = 3 * 60 * 60 * 1000
  const local = new Date(new Date(iso).getTime() - OFFSET_MS)
  const localNow = new Date(Date.now() - OFFSET_MS)

  const dateDay = Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate())
  const nowDay = Date.UTC(localNow.getUTCFullYear(), localNow.getUTCMonth(), localNow.getUTCDate())
  const diffDays = Math.round((nowDay - dateDay) / (24 * 60 * 60 * 1000))

  const hh = String(local.getUTCHours()).padStart(2, '0')
  const mm = String(local.getUTCMinutes()).padStart(2, '0')
  const time = `${hh}:${mm}`

  if (diffDays <= 0) return `hoy ${time}`
  if (diffDays === 1) return `ayer ${time}`
  return `hace ${diffDays} dias ${time}`
}

export function PeriodSelector({
  preset,
  customFrom,
  customTo,
  onPreset,
  onCustomFrom,
  onCustomTo,
  lastInventoryAt,
}: PeriodSelectorProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Selector de periodo">
        {PRESETS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => onPreset(id)}
            className={[
              'px-4 py-2 text-sm font-semibold border rounded min-h-[44px]',
              preset === id
                ? 'bg-gray-900 text-white border-gray-900'
                : 'bg-white text-gray-700 border-gray-300 hover:border-gray-500',
            ].join(' ')}
            aria-pressed={preset === id}
          >
            {label}
          </button>
        ))}
      </div>

      {preset === 'custom' && (
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="date"
              value={customFrom}
              onChange={(e) => {
                const newFrom = e.target.value
                // If the new "from" would be after "to", move "to" forward to match.
                if (newFrom > customTo) {
                  onCustomTo(newFrom)
                }
                onCustomFrom(newFrom)
              }}
              className="border border-gray-300 rounded px-2 py-1 text-sm min-h-[44px]"
              aria-label="Fecha desde"
            />
            <span className="text-gray-500 text-sm">al</span>
            <input
              type="date"
              value={customTo}
              min={customFrom}
              onChange={(e) => {
                const newTo = e.target.value
                // Reject: "to" cannot be before "from".
                if (newTo < customFrom) return
                onCustomTo(newTo)
              }}
              className="border border-gray-300 rounded px-2 py-1 text-sm min-h-[44px]"
              aria-label="Fecha hasta"
            />
          </div>
          {customFrom > customTo && (
            <p role="alert" className="text-xs text-red-600">
              El &apos;desde&apos; debe ser anterior al &apos;hasta&apos;.
            </p>
          )}
        </div>
      )}

      {lastInventoryAt && (
        <span className="text-xs text-gray-500 ml-2">
          ultimo inventario: {formatLastInventory(lastInventoryAt)}
        </span>
      )}
    </div>
  )
}
