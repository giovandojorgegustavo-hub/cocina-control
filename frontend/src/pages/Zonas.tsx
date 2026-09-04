import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { isAxiosError } from 'axios'
import { useCreateZone, useUpdateZone, useZones } from '../lib/zones'
import { useAuthWithGetters } from '../lib/auth'
import { ErrorBanner } from '../components/ErrorBanner'
import type { DeliveryZone } from '../lib/types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function errorMessage(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  return fallback
}

function isConflict(err: unknown): boolean {
  return isAxiosError(err) && err.response?.status === 409
}

// Espejo del ge=0 del servidor: alcanza para no mandar un PATCH que va a
// volver 422; la validacion real vive en el backend.
function feeValid(fee: string): boolean {
  const value = parseFloat(fee)
  return fee.trim() !== '' && isFinite(value) && value >= 0
}

const inputClass =
  'w-full px-3 py-2 border border-gray-300 bg-white text-base focus:outline-none focus:ring-2 focus:ring-gray-900 min-h-[44px]'

const saveButtonClass = (enabled: boolean) =>
  [
    'min-h-[44px] px-4 text-sm font-bold uppercase tracking-wide',
    enabled ? 'bg-gray-900 text-white active:opacity-70' : 'bg-gray-200 text-gray-400 cursor-not-allowed',
  ].join(' ')

// ---------------------------------------------------------------------------
// Fila de distrito
// ---------------------------------------------------------------------------

interface ZoneRowProps {
  zone: DeliveryZone
  onError: (message: string) => void
}

function ZoneRow({ zone, onError }: ZoneRowProps) {
  const [fee, setFee] = useState(zone.fee)
  const [active, setActive] = useState(zone.is_active)
  const [saved, setSaved] = useState(false)
  const mutation = useUpdateZone()

  // Cuando llega una version nueva de la lista (otro usuario guardo), la fila
  // se vuelve a alinear con el servidor salvo que se este editando.
  useEffect(() => {
    setFee(zone.fee)
    setActive(zone.is_active)
  }, [zone.fee, zone.is_active])

  const dirty = fee.trim() !== zone.fee || active !== zone.is_active
  const canSave = dirty && feeValid(fee) && !mutation.isPending

  function handleSave() {
    if (!canSave) return
    setSaved(false)
    mutation.mutate(
      { id: zone.id, input: { fee: fee.trim(), is_active: active } },
      {
        onSuccess: () => {
          setSaved(true)
          setTimeout(() => setSaved(false), 3000)
        },
        onError: (err) => {
          onError(errorMessage(err, `No se pudo guardar el distrito ${zone.district}.`))
        },
      },
    )
  }

  // Una zona apagada se ve atenuada: sigue en la tabla para poder volver a
  // encenderla, pero tiene que leerse distinto de las que cotizan.
  const rowClass = ['border-b border-gray-100', zone.is_active ? '' : 'opacity-50'].join(' ')

  return (
    <tr className={rowClass} data-inactive={zone.is_active ? undefined : 'true'}>
      <td className="px-3 py-2 font-semibold text-gray-900">{zone.district}</td>
      <td className="px-3 py-2 w-32">
        <input
          type="number"
          inputMode="decimal"
          step="0.50"
          min="0"
          value={fee}
          onChange={(e) => setFee(e.target.value)}
          aria-label={`Tarifa de ${zone.district}`}
          className={`${inputClass} text-right`}
        />
      </td>
      <td className="px-3 py-2 text-center">
        <input
          type="checkbox"
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
          aria-label={`Activa — ${zone.district}`}
          className="h-6 w-6 accent-gray-900"
        />
      </td>
      <td className="px-3 py-2 text-right whitespace-nowrap">
        <div className="flex items-center justify-end gap-2">
          {saved && (
            <span role="status" className="text-xs text-green-700 font-semibold">
              Guardado
            </span>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            className={saveButtonClass(canSave)}
          >
            {mutation.isPending ? 'guardando...' : 'Guardar'}
          </button>
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Fila de alta
// ---------------------------------------------------------------------------

interface NewZoneRowProps {
  onError: (message: string) => void
}

function NewZoneRow({ onError }: NewZoneRowProps) {
  const [district, setDistrict] = useState('')
  const [fee, setFee] = useState('')
  const [conflict, setConflict] = useState(false)
  const mutation = useCreateZone()

  const canAdd = district.trim() !== '' && feeValid(fee) && !mutation.isPending

  function handleAdd() {
    if (!canAdd) return
    setConflict(false)
    mutation.mutate(
      { district: district.trim(), fee: fee.trim() },
      {
        onSuccess: () => {
          setDistrict('')
          setFee('')
        },
        onError: (err) => {
          // El 409 es un error de esta fila, no de la pantalla: se muestra al
          // lado del campo para que el dueno corrija sin perder lo que escribio.
          if (isConflict(err)) {
            setConflict(true)
            return
          }
          onError(errorMessage(err, 'No se pudo agregar el distrito.'))
        },
      },
    )
  }

  return (
    <tr className="bg-gray-50">
      <td className="px-3 py-2">
        <input
          type="text"
          value={district}
          maxLength={80}
          onChange={(e) => {
            setDistrict(e.target.value)
            setConflict(false)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleAdd()
          }}
          placeholder="Agregar distrito"
          aria-label="Nuevo distrito"
          aria-invalid={conflict || undefined}
          className={inputClass}
        />
        {conflict && (
          <p role="alert" className="mt-1 text-xs font-semibold text-red-700">
            Ese distrito ya existe
          </p>
        )}
      </td>
      <td className="px-3 py-2 w-32 align-top">
        <input
          type="number"
          inputMode="decimal"
          step="0.50"
          min="0"
          value={fee}
          onChange={(e) => setFee(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleAdd()
          }}
          placeholder="0.00"
          aria-label="Tarifa del nuevo distrito"
          className={`${inputClass} text-right`}
        />
      </td>
      <td className="px-3 py-2" />
      <td className="px-3 py-2 text-right whitespace-nowrap align-top">
        <button
          type="button"
          onClick={handleAdd}
          disabled={!canAdd}
          className={saveButtonClass(canAdd)}
        >
          {mutation.isPending ? 'agregando...' : 'Agregar'}
        </button>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const thClass = 'px-3 py-2 font-semibold text-gray-600 uppercase text-xs'

export function Zonas() {
  const navigate = useNavigate()
  const { role } = useAuthWithGetters()
  const backTo = role === 'owner' ? '/tablero' : '/'

  // all=true: el panel es el unico lugar donde una zona apagada se ve, porque
  // es el unico lugar desde donde se la puede volver a encender.
  const { data: zones, isLoading, isError, refetch } = useZones(true)
  const [error, setError] = useState<string | null>(null)

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate(backTo)}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver"
        >
          &lt;
        </button>
        <h1 className="text-lg font-bold uppercase tracking-wide">DISTRITOS DE REPARTO</h1>
      </header>

      <main className="flex-1 px-4 py-6 space-y-8 overflow-y-auto pb-24">
        <section aria-label="Distritos de reparto">
          <p className="text-sm text-gray-500 mb-3">
            El asistente de WhatsApp solo cotiza y toma pedidos en los distritos activos.
          </p>
          {isLoading && (
            <p role="status" className="text-sm text-gray-400">
              Cargando distritos...
            </p>
          )}
          {zones && (
            <div className="overflow-x-auto bg-white border border-gray-200 rounded-lg">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className={`${thClass} text-left`}>Distrito</th>
                    <th className={`${thClass} text-right`}>Tarifa (S/)</th>
                    <th className={`${thClass} text-center`}>Activa</th>
                    <th className={thClass}>
                      <span className="sr-only">Acciones</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {zones.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-3 py-3 text-sm text-gray-400">
                        Todavía no hay distritos cargados: sin distritos activos, el asistente
                        no reparte a ningún lado.
                      </td>
                    </tr>
                  )}
                  {zones.map((zone) => (
                    <ZoneRow key={zone.id} zone={zone} onError={setError} />
                  ))}
                  <NewZoneRow onError={setError} />
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>

      {isError && (
        <ErrorBanner
          message="No se pudieron cargar los distritos."
          onRetry={() => {
            void refetch()
          }}
        />
      )}
      {!isError && error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
    </div>
  )
}
