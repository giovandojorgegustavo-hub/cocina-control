/**
 * Semaforo — visual traffic-light indicator for stock level relative to threshold.
 *
 * Three filled/empty circles: ●●● green, ●●○ yellow, ●○○ red.
 *
 * Rules (per UX spec):
 *   stock_now >= threshold          → green  (●●●)
 *   stock_now >= threshold * 0.5    → yellow (●●○)
 *   stock_now < threshold * 0.5     → red    (●○○)
 */

type SemaforoLevel = 'green' | 'yellow' | 'red'

export function stockLevel(stockNow: number, threshold: number): SemaforoLevel {
  if (stockNow >= threshold) return 'green'
  if (stockNow >= threshold * 0.5) return 'yellow'
  return 'red'
}

const LEVEL_COLORS: Record<SemaforoLevel, string> = {
  green: 'bg-green-500',
  yellow: 'bg-yellow-400',
  red: 'bg-red-500',
}

const LEVEL_LABELS: Record<SemaforoLevel, string> = {
  green: 'stock ok',
  yellow: 'stock bajo',
  red: 'stock critico',
}

// Each level defines which dots are "filled" (true) and which are "empty" (false)
const LEVEL_DOTS: Record<SemaforoLevel, [boolean, boolean, boolean]> = {
  green: [true, true, true],
  yellow: [true, true, false],
  red: [true, false, false],
}

interface SemaforoProps {
  level: SemaforoLevel
  /** Size in px of each dot. Default: 10 */
  size?: number
}

export function Semaforo({ level, size = 10 }: SemaforoProps) {
  const color = LEVEL_COLORS[level]
  const dots = LEVEL_DOTS[level]

  return (
    <span
      role="img"
      aria-label={LEVEL_LABELS[level]}
      className="inline-flex items-center gap-0.5"
    >
      {dots.map((filled, i) => (
        <span
          key={i}
          style={{ width: size, height: size }}
          className={[
            'rounded-full inline-block',
            filled ? color : 'bg-gray-300',
          ].join(' ')}
        />
      ))}
    </span>
  )
}
