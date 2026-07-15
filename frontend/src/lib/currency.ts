/** Format a Decimal-like string as Peruvian Soles. Ex: '108.5' -> 'S/. 108,50' */
export function formatSoles(amount: string | number): string {
  if (typeof amount === 'string' && amount.trim() === '') return 'S/. —'
  const n = typeof amount === 'string' ? Number(amount) : amount
  if (!isFinite(n)) return 'S/. —'
  return 'S/. ' + n.toLocaleString('es-PE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}
