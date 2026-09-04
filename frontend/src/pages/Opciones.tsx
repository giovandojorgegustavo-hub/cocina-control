import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { isAxiosError } from 'axios'
import {
  useCreateOptionGroup,
  useCreateOptionItem,
  useOptionGroups,
  useProductOptionGroups,
  useReplaceProductOptionGroups,
  useUpdateOptionGroup,
  useUpdateOptionItem,
} from '../lib/options'
import { useProducts } from '../lib/products'
import { useAuthWithGetters } from '../lib/auth'
import { ErrorBanner } from '../components/ErrorBanner'
import type { OptionGroup, OptionItem, Product, SelectionMode } from '../lib/types'

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

// Espejo del ge=0 del servidor: alcanza para no mandar un request que va a
// volver 422; la validacion real vive en el backend.
function priceValid(price: string): boolean {
  const value = parseFloat(price)
  return price.trim() !== '' && isFinite(value) && value >= 0
}

function intOrUndefined(value: string): number | undefined {
  if (value.trim() === '') return undefined
  const parsed = parseInt(value, 10)
  return isFinite(parsed) && parsed >= 0 ? parsed : undefined
}

const inputClass =
  'w-full px-3 py-2 border border-gray-300 bg-white text-base focus:outline-none focus:ring-2 focus:ring-gray-900 min-h-[44px]'

const saveButtonClass = (enabled: boolean) =>
  [
    'min-h-[44px] px-4 text-sm font-bold uppercase tracking-wide',
    enabled ? 'bg-gray-900 text-white active:opacity-70' : 'bg-gray-200 text-gray-400 cursor-not-allowed',
  ].join(' ')

const badgeClass = 'inline-block px-2 py-0.5 text-xs font-semibold uppercase tracking-wide rounded'

const thClass = 'px-3 py-2 font-semibold text-gray-600 uppercase text-xs'

function limitsLabel(group: OptionGroup): string {
  const max = group.max_choices === null ? 'sin tope' : String(group.max_choices)
  return `mín ${group.min_choices} / máx ${max}`
}

// ---------------------------------------------------------------------------
// Fila de opcion
// ---------------------------------------------------------------------------

interface ItemRowProps {
  item: OptionItem
  onError: (message: string) => void
}

function ItemRow({ item, onError }: ItemRowProps) {
  const [price, setPrice] = useState(item.price)
  const [active, setActive] = useState(item.is_active)
  const [saved, setSaved] = useState(false)
  const mutation = useUpdateOptionItem()

  // Cuando llega una version nueva de la lista (otro usuario guardo), la fila
  // se vuelve a alinear con el servidor salvo que se este editando.
  useEffect(() => {
    setPrice(item.price)
    setActive(item.is_active)
  }, [item.price, item.is_active])

  const dirty = price.trim() !== item.price || active !== item.is_active
  const canSave = dirty && priceValid(price) && !mutation.isPending

  function handleSave() {
    if (!canSave) return
    setSaved(false)
    mutation.mutate(
      { id: item.id, input: { price: price.trim(), is_active: active } },
      {
        onSuccess: () => {
          setSaved(true)
          setTimeout(() => setSaved(false), 3000)
        },
        onError: (err) => {
          onError(errorMessage(err, `No se pudo guardar la opción ${item.name}.`))
        },
      },
    )
  }

  const rowClass = ['border-b border-gray-100', item.is_active ? '' : 'opacity-50'].join(' ')

  return (
    <tr className={rowClass} data-inactive={item.is_active ? undefined : 'true'}>
      <td className="px-3 py-2 font-semibold text-gray-900">{item.name}</td>
      <td className="px-3 py-2 w-32">
        <input
          type="number"
          inputMode="decimal"
          step="0.50"
          min="0"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          aria-label={`Precio de ${item.name}`}
          className={`${inputClass} text-right`}
        />
      </td>
      <td className="px-3 py-2 text-center">
        <input
          type="checkbox"
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
          aria-label={`Activa — ${item.name}`}
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
// Fila de alta de opcion
// ---------------------------------------------------------------------------

interface NewItemRowProps {
  group: OptionGroup
  onError: (message: string) => void
}

function NewItemRow({ group, onError }: NewItemRowProps) {
  const [name, setName] = useState('')
  const [price, setPrice] = useState('0')
  const [conflict, setConflict] = useState(false)
  const mutation = useCreateOptionItem()

  const canAdd = name.trim() !== '' && priceValid(price) && !mutation.isPending

  function handleAdd() {
    if (!canAdd) return
    setConflict(false)
    mutation.mutate(
      { groupId: group.id, input: { name: name.trim(), price: price.trim() } },
      {
        onSuccess: () => {
          setName('')
          setPrice('0')
        },
        onError: (err) => {
          // El 409 es un error de esta fila, no de la pantalla: se muestra al
          // lado del campo para que el dueno corrija sin perder lo que escribio.
          if (isConflict(err)) {
            setConflict(true)
            return
          }
          onError(errorMessage(err, 'No se pudo agregar la opción.'))
        },
      },
    )
  }

  return (
    <tr className="bg-gray-50">
      <td className="px-3 py-2">
        <input
          type="text"
          value={name}
          maxLength={120}
          onChange={(e) => {
            setName(e.target.value)
            setConflict(false)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleAdd()
          }}
          placeholder="Agregar opción"
          aria-label={`Nueva opción en ${group.name}`}
          aria-invalid={conflict || undefined}
          className={inputClass}
        />
        {conflict && (
          <p role="alert" className="mt-1 text-xs font-semibold text-red-700">
            Esa opción ya existe en el grupo
          </p>
        )}
      </td>
      <td className="px-3 py-2 w-32 align-top">
        <input
          type="number"
          inputMode="decimal"
          step="0.50"
          min="0"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleAdd()
          }}
          aria-label={`Precio de la nueva opción en ${group.name}`}
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
// Tarjeta de grupo
// ---------------------------------------------------------------------------

interface GroupCardProps {
  group: OptionGroup
  onError: (message: string) => void
}

function GroupCard({ group, onError }: GroupCardProps) {
  const [open, setOpen] = useState(false)
  const mutation = useUpdateOptionGroup()

  // Apagar un grupo lo saca de la carta y del asistente en el acto; no hace
  // falta un boton Guardar para un solo interruptor.
  function toggleActive(next: boolean) {
    mutation.mutate(
      { id: group.id, input: { is_active: next } },
      {
        onError: (err) => {
          onError(errorMessage(err, `No se pudo cambiar el grupo ${group.name}.`))
        },
      },
    )
  }

  const cardClass = [
    'bg-white border border-gray-200 rounded-lg',
    group.is_active ? '' : 'opacity-60',
  ].join(' ')

  return (
    <article
      className={cardClass}
      aria-label={`Grupo ${group.name}`}
      data-inactive={group.is_active ? undefined : 'true'}
    >
      <div className="flex items-center gap-3 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex-1 min-h-[44px] flex flex-wrap items-center gap-2 text-left"
        >
          <span className="text-base font-bold text-gray-900">{group.name}</span>
          <span className={`${badgeClass} bg-gray-100 text-gray-700`}>
            {group.selection === 'single' ? 'Una opción' : 'Varias'}
          </span>
          {group.required && (
            <span className={`${badgeClass} bg-gray-900 text-white`}>Obligatorio</span>
          )}
          <span className="text-xs text-gray-500">{limitsLabel(group)}</span>
          <span className="text-xs text-gray-400">
            {group.items.length} {group.items.length === 1 ? 'opción' : 'opciones'}
          </span>
        </button>
        <label className="flex items-center gap-2 text-xs font-semibold uppercase text-gray-600">
          <input
            type="checkbox"
            checked={group.is_active}
            disabled={mutation.isPending}
            onChange={(e) => toggleActive(e.target.checked)}
            aria-label={`Activo — ${group.name}`}
            className="h-6 w-6 accent-gray-900"
          />
          Activa
        </label>
      </div>

      {open && (
        <div className="overflow-x-auto border-t border-gray-200">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className={`${thClass} text-left`}>Opción</th>
                <th className={`${thClass} text-right`}>Precio (S/)</th>
                <th className={`${thClass} text-center`}>Activa</th>
                <th className={thClass}>
                  <span className="sr-only">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {group.items.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-3 text-sm text-gray-400">
                    Este grupo todavía no tiene opciones.
                  </td>
                </tr>
              )}
              {group.items.map((item) => (
                <ItemRow key={item.id} item={item} onError={onError} />
              ))}
              <NewItemRow group={group} onError={onError} />
            </tbody>
          </table>
        </div>
      )}
    </article>
  )
}

// ---------------------------------------------------------------------------
// Alta de grupo
// ---------------------------------------------------------------------------

interface NewGroupFormProps {
  onError: (message: string) => void
}

function NewGroupForm({ onError }: NewGroupFormProps) {
  const [name, setName] = useState('')
  const [selection, setSelection] = useState<SelectionMode>('single')
  const [required, setRequired] = useState(false)
  const [min, setMin] = useState('')
  const [max, setMax] = useState('')
  const mutation = useCreateOptionGroup()

  const canCreate = name.trim() !== '' && !mutation.isPending

  function handleCreate() {
    if (!canCreate) return
    // Los campos vacios no viajan: el servidor aplica sus reglas (single =>
    // max 1, obligatorio => min 1) y devuelve el grupo ya coherente.
    const input = {
      name: name.trim(),
      selection,
      required,
      ...(intOrUndefined(min) !== undefined ? { min_choices: intOrUndefined(min) } : {}),
      ...(selection === 'multiple' && intOrUndefined(max) !== undefined
        ? { max_choices: intOrUndefined(max) }
        : {}),
    }
    mutation.mutate(input, {
      onSuccess: () => {
        setName('')
        setSelection('single')
        setRequired(false)
        setMin('')
        setMax('')
      },
      onError: (err) => {
        onError(errorMessage(err, 'No se pudo crear el grupo.'))
      },
    })
  }

  return (
    <form
      className="bg-gray-50 border border-gray-200 rounded-lg p-3 grid grid-cols-2 md:grid-cols-6 gap-3 items-end"
      aria-label="Nuevo grupo"
      onSubmit={(e) => {
        e.preventDefault()
        handleCreate()
      }}
    >
      <label className="col-span-2 text-xs font-semibold uppercase text-gray-600">
        Nuevo grupo
        <input
          type="text"
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
          placeholder="Ej. Proteína extra"
          aria-label="Nombre del nuevo grupo"
          className={`${inputClass} mt-1 normal-case font-normal`}
        />
      </label>
      <label className="text-xs font-semibold uppercase text-gray-600">
        Selección
        <select
          value={selection}
          onChange={(e) => setSelection(e.target.value as SelectionMode)}
          aria-label="Selección del nuevo grupo"
          className={`${inputClass} mt-1 normal-case font-normal`}
        >
          <option value="single">Una opción</option>
          <option value="multiple">Varias</option>
        </select>
      </label>
      <label className="flex items-center gap-2 min-h-[44px] text-xs font-semibold uppercase text-gray-600">
        <input
          type="checkbox"
          checked={required}
          onChange={(e) => setRequired(e.target.checked)}
          aria-label="Obligatorio"
          className="h-6 w-6 accent-gray-900"
        />
        Obligatorio
      </label>
      <label className="text-xs font-semibold uppercase text-gray-600">
        Mín
        <input
          type="number"
          inputMode="numeric"
          min="0"
          step="1"
          value={min}
          onChange={(e) => setMin(e.target.value)}
          aria-label="Mínimo del nuevo grupo"
          className={`${inputClass} mt-1 text-right font-normal`}
        />
      </label>
      <label className="text-xs font-semibold uppercase text-gray-600">
        Máx
        <input
          type="number"
          inputMode="numeric"
          min="1"
          step="1"
          value={selection === 'single' ? '1' : max}
          disabled={selection === 'single'}
          onChange={(e) => setMax(e.target.value)}
          aria-label="Máximo del nuevo grupo"
          className={`${inputClass} mt-1 text-right font-normal disabled:bg-gray-100 disabled:text-gray-400`}
        />
      </label>
      <div className="col-span-2 md:col-span-6 flex justify-end">
        <button type="submit" disabled={!canCreate} className={saveButtonClass(canCreate)}>
          {mutation.isPending ? 'creando...' : 'Crear grupo'}
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Asignacion por plato
// ---------------------------------------------------------------------------

interface ProductAssignmentProps {
  product: Product
  groups: OptionGroup[]
  onError: (message: string) => void
}

function ProductAssignment({ product, groups, onError }: ProductAssignmentProps) {
  const { data: links, isLoading } = useProductOptionGroups(product.id)
  const [selected, setSelected] = useState<string[] | null>(null)
  const [saved, setSaved] = useState(false)
  const mutation = useReplaceProductOptionGroups()

  // El orden guardado es el orden en que se le pregunta al cliente: se
  // conserva, y lo nuevo se agrega al final.
  const current = links ? links.map((l) => l.group_id) : []
  const value = selected ?? current

  useEffect(() => {
    setSelected(null)
  }, [links])

  function toggle(groupId: string, checked: boolean) {
    const base = selected ?? current
    setSelected(checked ? [...base, groupId] : base.filter((id) => id !== groupId))
  }

  const dirty = selected !== null && selected.join('|') !== current.join('|')
  const canSave = dirty && !mutation.isPending

  function handleSave() {
    if (!canSave || selected === null) return
    setSaved(false)
    mutation.mutate(
      { productId: product.id, groupIds: selected },
      {
        onSuccess: () => {
          setSelected(null)
          setSaved(true)
          setTimeout(() => setSaved(false), 3000)
        },
        onError: (err) => {
          onError(errorMessage(err, `No se pudo guardar las opciones de ${product.name}.`))
        },
      },
    )
  }

  return (
    <article
      className="bg-white border border-gray-200 rounded-lg px-3 py-2"
      aria-label={`Opciones de ${product.name}`}
    >
      <div className="flex items-center gap-2 mb-2">
        <h3 className="flex-1 text-base font-bold text-gray-900">{product.name}</h3>
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
      {isLoading && (
        <p role="status" className="text-sm text-gray-400">
          Cargando...
        </p>
      )}
      {links && (
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {groups.map((group) => (
            <label
              key={group.id}
              className="flex items-center gap-2 min-h-[44px] text-sm text-gray-800"
            >
              <input
                type="checkbox"
                checked={value.includes(group.id)}
                onChange={(e) => toggle(group.id, e.target.checked)}
                aria-label={`${group.name} — ${product.name}`}
                className="h-6 w-6 accent-gray-900"
              />
              {group.name}
            </label>
          ))}
        </div>
      )}
    </article>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Opciones() {
  const navigate = useNavigate()
  const { role } = useAuthWithGetters()
  const backTo = role === 'owner' ? '/tablero' : '/'

  // all=true: el panel es el unico lugar donde un grupo apagado se ve, porque
  // es el unico lugar desde donde se lo puede volver a encender.
  const {
    data: groups,
    isLoading: groupsLoading,
    isError: groupsError,
    refetch: refetchGroups,
  } = useOptionGroups(true)
  const {
    data: products,
    isLoading: productsLoading,
    isError: productsError,
    refetch: refetchProducts,
  } = useProducts('sale')
  const [error, setError] = useState<string | null>(null)

  const loadError = groupsError || productsError
  // Solo los grupos encendidos se ofrecen para asignar: uno apagado no sale
  // en la carta aunque este asignado.
  const activeGroups = (groups ?? []).filter((g) => g.is_active)

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
        <h1 className="text-lg font-bold uppercase tracking-wide">EXTRAS Y OPCIONES</h1>
      </header>

      <main className="flex-1 px-4 py-6 space-y-8 overflow-y-auto pb-24">
        <section aria-label="Grupos de opciones" className="space-y-3">
          <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500">
            Grupos de opciones
          </h2>
          <p className="text-sm text-gray-500">
            Las opciones con precio se suman al plato. El asistente de WhatsApp y la carta leen
            esta lista.
          </p>
          {groupsLoading && (
            <p role="status" className="text-sm text-gray-400">
              Cargando opciones...
            </p>
          )}
          {groups && groups.length === 0 && (
            <p className="text-sm text-gray-400">Todavía no hay grupos de opciones.</p>
          )}
          {groups &&
            groups.map((group) => <GroupCard key={group.id} group={group} onError={setError} />)}
          <NewGroupForm onError={setError} />
        </section>

        <section aria-label="Qué opciones tiene cada plato" className="space-y-3">
          <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500">
            Qué opciones tiene cada plato
          </h2>
          <p className="text-sm text-gray-500">
            Marca los grupos que se le preguntan al cliente al pedir cada plato.
          </p>
          {productsLoading && (
            <p role="status" className="text-sm text-gray-400">
              Cargando carta...
            </p>
          )}
          {products && products.length === 0 && (
            <p className="text-sm text-gray-400">No hay productos de venta en el catálogo.</p>
          )}
          {products &&
            groups &&
            products.map((product) => (
              <ProductAssignment
                key={product.id}
                product={product}
                groups={activeGroups}
                onError={setError}
              />
            ))}
        </section>
      </main>

      {loadError && (
        <ErrorBanner
          message="No se pudieron cargar las opciones."
          onRetry={() => {
            void refetchGroups()
            void refetchProducts()
          }}
        />
      )}
      {!loadError && error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
    </div>
  )
}
