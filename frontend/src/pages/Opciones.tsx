import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { isAxiosError } from 'axios'
import {
  useCreateOptionGroup,
  useCreateOptionItem,
  useOptionGroups,
  useProductsOptionGroups,
  useReplaceProductOptionGroups,
  useUpdateOptionGroup,
  useUpdateOptionItem,
} from '../lib/options'
import { useProducts } from '../lib/products'
import { finalPrice } from '../lib/pricing'
import { useAuthWithGetters } from '../lib/auth'
import { formatSoles } from '../lib/currency'
import { ErrorBanner } from '../components/ErrorBanner'
import type {
  OptionGroup,
  OptionItem,
  Product,
  ProductOptionGroupLink,
  SelectionMode,
} from '../lib/types'

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
// volver 422; la validacion real vive en el backend. Vacio vale 0 (incluido).
function priceValid(price: string): boolean {
  if (price.trim() === '') return true
  const value = parseFloat(price)
  return isFinite(value) && value >= 0
}

function priceOrZero(price: string): string {
  return price.trim() === '' ? '0' : price.trim()
}

function isIncluded(price: string): boolean {
  return price.trim() === '' || parseFloat(price) === 0
}

function intOrUndefined(value: string): number | undefined {
  if (value.trim() === '') return undefined
  const parsed = parseInt(value, 10)
  return isFinite(parsed) && parsed >= 0 ? parsed : undefined
}

type RuleInput = Pick<OptionGroup, 'selection' | 'required' | 'min_choices' | 'max_choices'>

/**
 * La regla del grupo en una frase, en vez de badges + "min 1 / max 2". Es lo
 * que el dueno lee al lado del nombre del grupo en cada plato.
 */
function describeRule(group: RuleInput): string {
  const min = group.min_choices
  const max = group.max_choices
  if (group.selection === 'single') {
    return group.required && min > 0 ? 'Elige 1' : 'Opcional, elige 1'
  }
  if (min <= 0) {
    return max === null ? 'Opcional, sin tope' : `Opcional, hasta ${max}`
  }
  if (max === null) return `Elige ${min} o más`
  if (max === min) return `Elige ${min}`
  return `Elige de ${min} a ${max}`
}

function usedInLabel(count: number): string {
  if (count === 0) return 'en ningún plato'
  if (count === 1) return 'en 1 plato'
  return `en ${count} platos`
}

function dishPrice(product: Product): string {
  if (product.sale_price === null) return formatSoles('')
  const computed = finalPrice(product.sale_price, product.discount_percent ?? '')
  return formatSoles(computed === null ? product.sale_price : computed)
}

const inputClass =
  'w-full px-3 py-2 border border-gray-300 bg-white text-base focus:outline-none focus:ring-2 focus:ring-gray-900 min-h-[44px]'

const saveButtonClass = (enabled: boolean) =>
  [
    'min-h-[44px] px-4 text-sm font-bold uppercase tracking-wide',
    enabled ? 'bg-gray-900 text-white active:opacity-70' : 'bg-gray-200 text-gray-400 cursor-not-allowed',
  ].join(' ')

const linkButtonClass =
  'min-h-[44px] px-2 text-sm text-gray-600 underline underline-offset-2 whitespace-nowrap disabled:text-gray-400 disabled:no-underline'

const thClass = 'px-3 py-2 font-semibold text-gray-600 uppercase text-xs'

// ---------------------------------------------------------------------------
// Fila de opcion
// ---------------------------------------------------------------------------

interface ItemRowProps {
  item: OptionItem
  onError: (message: string) => void
}

function ItemRow({ item, onError }: ItemRowProps) {
  // Precio 0 se muestra vacio con "incluido" de placeholder: es lo que
  // significa para la carta y evita una columna llena de 0.00.
  const [price, setPrice] = useState(isIncluded(item.price) ? '' : item.price)
  const [active, setActive] = useState(item.is_active)
  const [saved, setSaved] = useState(false)
  const mutation = useUpdateOptionItem()

  // Cuando llega una version nueva de la lista (otro usuario guardo), la fila
  // se vuelve a alinear con el servidor salvo que se este editando.
  useEffect(() => {
    setPrice(isIncluded(item.price) ? '' : item.price)
    setActive(item.is_active)
  }, [item.price, item.is_active])

  const priceDirty = priceValid(price)
    ? parseFloat(priceOrZero(price)) !== parseFloat(item.price)
    : true
  const dirty = priceDirty || active !== item.is_active
  const canSave = dirty && priceValid(price) && !mutation.isPending

  function handleSave() {
    if (!canSave) return
    setSaved(false)
    mutation.mutate(
      { id: item.id, input: { price: priceOrZero(price), is_active: active } },
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
          placeholder="incluido"
          onChange={(e) => setPrice(e.target.value)}
          aria-label={`Precio de ${item.name}`}
          className={`${inputClass} text-right placeholder:text-gray-400 placeholder:text-sm`}
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
  const [price, setPrice] = useState('')
  const [conflict, setConflict] = useState(false)
  const mutation = useCreateOptionItem()

  const canAdd = name.trim() !== '' && priceValid(price) && !mutation.isPending

  function handleAdd() {
    if (!canAdd) return
    setConflict(false)
    mutation.mutate(
      { groupId: group.id, input: { name: name.trim(), price: priceOrZero(price) } },
      {
        onSuccess: () => {
          setName('')
          setPrice('')
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
          placeholder="incluido"
          onChange={(e) => setPrice(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleAdd()
          }}
          aria-label={`Precio de la nueva opción en ${group.name}`}
          className={`${inputClass} text-right placeholder:text-gray-400 placeholder:text-sm`}
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
// Tabla de opciones de un grupo (la misma dentro del plato y en GRUPOS)
// ---------------------------------------------------------------------------

interface ItemsTableProps {
  group: OptionGroup
  onError: (message: string) => void
}

function ItemsTable({ group, onError }: ItemsTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <th className={`${thClass} text-left`}>Opción</th>
            <th className={`${thClass} text-right`}>Extra (S/)</th>
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
  )
}

// ---------------------------------------------------------------------------
// Bloque de grupo dentro de un plato
// ---------------------------------------------------------------------------

interface DishGroupBlockProps {
  product: Product
  link: ProductOptionGroupLink
  group: OptionGroup | undefined
  usedIn: number
  removing: boolean
  onRemove: () => void
  onError: (message: string) => void
}

function DishGroupBlock({
  product,
  link,
  group,
  usedIn,
  removing,
  onRemove,
  onError,
}: DishGroupBlockProps) {
  const name = group?.name ?? link.name
  return (
    <section
      aria-label={`${name} en ${product.name}`}
      className="bg-white border border-gray-200 rounded-lg overflow-hidden"
      data-inactive={group && !group.is_active ? 'true' : undefined}
    >
      <div className="flex items-start gap-2 px-3 py-2">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-base font-bold text-gray-900">{name}</span>
            {group && <span className="text-sm text-gray-600">{describeRule(group)}</span>}
            {group && !group.is_active && (
              <span className="text-xs font-semibold uppercase text-red-700">
                Grupo apagado: no se ofrece
              </span>
            )}
          </div>
          {usedIn > 1 && (
            <p className="text-xs text-gray-500 mt-0.5">
              Este grupo se usa en {usedIn} platos; el cambio aplica a todos.
            </p>
          )}
        </div>
        <button type="button" onClick={onRemove} disabled={removing} className={linkButtonClass}>
          {removing ? 'quitando...' : 'Quitar de este plato'}
        </button>
      </div>
      {group ? (
        <div className="border-t border-gray-200">
          <ItemsTable group={group} onError={onError} />
        </div>
      ) : (
        <p className="px-3 py-2 text-sm text-gray-400 border-t border-gray-200">
          No se encontró el grupo.
        </p>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Tarjeta de plato
// ---------------------------------------------------------------------------

interface DishCardProps {
  product: Product
  groups: OptionGroup[]
  links: ProductOptionGroupLink[] | undefined
  linksError: boolean
  usage: Map<string, number>
  onError: (message: string) => void
}

function DishCard({ product, groups, links, linksError, usage, onError }: DishCardProps) {
  const [open, setOpen] = useState(false)
  const [toAdd, setToAdd] = useState('')
  const [removingId, setRemovingId] = useState<string | null>(null)
  const mutation = useReplaceProductOptionGroups()

  const byId = useMemo(() => new Map(groups.map((g) => [g.id, g])), [groups])
  const assignedIds = links ? links.map((l) => l.group_id) : []
  // Solo grupos encendidos y todavia no asignados se ofrecen para agregar.
  const available = groups.filter((g) => g.is_active && !assignedIds.includes(g.id))

  let summary = '…'
  if (links) {
    summary =
      links.length === 0
        ? 'Sin opciones todavía'
        : links.map((l) => byId.get(l.group_id)?.name ?? l.name).join(' · ')
  } else if (linksError) {
    summary = 'No se pudieron cargar las opciones'
  }

  function save(groupIds: string[], fallback: string, done: () => void) {
    mutation.mutate(
      { productId: product.id, groupIds },
      {
        onSuccess: done,
        onError: (err) => {
          done()
          onError(errorMessage(err, fallback))
        },
      },
    )
  }

  function handleAdd() {
    if (!toAdd || mutation.isPending) return
    // El orden guardado es el orden en que se le pregunta al cliente: lo
    // nuevo va al final.
    save([...assignedIds, toAdd], `No se pudo agregar el grupo a ${product.name}.`, () =>
      setToAdd(''),
    )
  }

  function handleRemove(groupId: string) {
    if (mutation.isPending) return
    setRemovingId(groupId)
    save(
      assignedIds.filter((id) => id !== groupId),
      `No se pudo quitar el grupo de ${product.name}.`,
      () => setRemovingId(null),
    )
  }

  const canAdd = toAdd !== '' && !mutation.isPending
  const adding = mutation.isPending && removingId === null

  let placeholder = 'Elige un grupo…'
  if (available.length === 0) {
    placeholder = groups.length === 0 ? 'Primero crea un grupo abajo' : 'Todos los grupos ya están en este plato'
  }

  return (
    <article className="bg-white border border-gray-200 rounded-lg" aria-label={`Plato ${product.name}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full min-h-[56px] px-3 py-2 flex items-center gap-3 text-left"
      >
        <span aria-hidden="true" className="w-4 text-gray-400 text-sm select-none">
          {open ? '▾' : '▸'}
        </span>
        <span className="flex-1 min-w-0">
          <span className="block text-base font-bold text-gray-900">{product.name}</span>
          <span className="block text-sm text-gray-500 truncate">{summary}</span>
        </span>
        <span className="font-bold text-gray-900 whitespace-nowrap">{dishPrice(product)}</span>
      </button>

      {open && (
        <div className="border-t border-gray-200 px-3 py-3 space-y-3 bg-gray-50">
          {!links && !linksError && (
            <p role="status" className="text-sm text-gray-400">
              Cargando...
            </p>
          )}
          {links && links.length === 0 && (
            <p className="text-sm text-gray-500">
              Este plato no tiene opciones todavía: el cliente lo pide tal cual.
            </p>
          )}
          {links &&
            links.map((link) => (
              <DishGroupBlock
                key={link.group_id}
                product={product}
                link={link}
                group={byId.get(link.group_id)}
                usedIn={usage.get(link.group_id) ?? 0}
                removing={removingId === link.group_id && mutation.isPending}
                onRemove={() => handleRemove(link.group_id)}
                onError={onError}
              />
            ))}

          {links && (
            <div className="flex flex-col sm:flex-row sm:items-end gap-2 pt-1">
              <label className="flex-1 text-xs font-semibold uppercase text-gray-600">
                Agregar grupo a este plato
                <select
                  value={toAdd}
                  onChange={(e) => setToAdd(e.target.value)}
                  disabled={available.length === 0}
                  aria-label={`Agregar grupo a ${product.name}`}
                  className={`${inputClass} mt-1 normal-case font-normal disabled:bg-gray-100 disabled:text-gray-400`}
                >
                  <option value="">{placeholder}</option>
                  {available.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name} — {describeRule(g)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={handleAdd}
                disabled={!canAdd}
                className={saveButtonClass(canAdd)}
              >
                {adding ? 'agregando...' : 'Agregar grupo'}
              </button>
            </div>
          )}
        </div>
      )}
    </article>
  )
}

// ---------------------------------------------------------------------------
// Edicion de reglas de un grupo
// ---------------------------------------------------------------------------

interface GroupEditFormProps {
  group: OptionGroup
  onDone: () => void
  onError: (message: string) => void
}

function GroupEditForm({ group, onDone, onError }: GroupEditFormProps) {
  const [name, setName] = useState(group.name)
  const [selection, setSelection] = useState<SelectionMode>(group.selection)
  const [required, setRequired] = useState(group.required)
  const [min, setMin] = useState(String(group.min_choices))
  const [max, setMax] = useState(group.max_choices === null ? '' : String(group.max_choices))
  const mutation = useUpdateOptionGroup()

  const canSave = name.trim() !== '' && !mutation.isPending

  // Lo que va a leer el cliente con estos valores, antes de guardar.
  const preview = describeRule({
    selection,
    required,
    min_choices: intOrUndefined(min) ?? 0,
    max_choices: selection === 'single' ? 1 : (intOrUndefined(max) ?? null),
  })

  function handleSave() {
    if (!canSave) return
    // El minimo vacio no viaja: el servidor aplica sus reglas (single => max
    // 1, obligatorio => min 1) y devuelve el grupo ya coherente.
    const input = {
      name: name.trim(),
      selection,
      required,
      ...(intOrUndefined(min) !== undefined ? { min_choices: intOrUndefined(min) } : {}),
      ...(selection === 'multiple' ? { max_choices: intOrUndefined(max) ?? null } : {}),
    }
    mutation.mutate(
      { id: group.id, input },
      {
        onSuccess: onDone,
        onError: (err) => {
          onError(errorMessage(err, `No se pudo guardar el grupo ${group.name}.`))
        },
      },
    )
  }

  return (
    <form
      className="border-t border-gray-200 bg-gray-50 p-3 grid grid-cols-2 md:grid-cols-6 gap-3 items-end"
      aria-label={`Editar grupo ${group.name}`}
      onSubmit={(e) => {
        e.preventDefault()
        handleSave()
      }}
    >
      <label className="col-span-2 text-xs font-semibold uppercase text-gray-600">
        Nombre
        <input
          type="text"
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
          aria-label={`Nombre del grupo ${group.name}`}
          className={`${inputClass} mt-1 normal-case font-normal`}
        />
      </label>
      <label className="text-xs font-semibold uppercase text-gray-600">
        Selección
        <select
          value={selection}
          onChange={(e) => setSelection(e.target.value as SelectionMode)}
          aria-label={`Selección del grupo ${group.name}`}
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
          aria-label={`Obligatorio — ${group.name}`}
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
          aria-label={`Mínimo del grupo ${group.name}`}
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
          placeholder="sin tope"
          onChange={(e) => setMax(e.target.value)}
          aria-label={`Máximo del grupo ${group.name}`}
          className={`${inputClass} mt-1 text-right font-normal disabled:bg-gray-100 disabled:text-gray-400`}
        />
      </label>
      <div className="col-span-2 md:col-span-6 flex items-center gap-3">
        <span className="flex-1 text-sm text-gray-600">
          El cliente verá: <span className="font-semibold text-gray-900">{preview}</span>
        </span>
        <button type="button" onClick={onDone} className={linkButtonClass}>
          Cancelar
        </button>
        <button type="submit" disabled={!canSave} className={saveButtonClass(canSave)}>
          {mutation.isPending ? 'guardando...' : 'Guardar'}
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Tarjeta de grupo
// ---------------------------------------------------------------------------

interface GroupCardProps {
  group: OptionGroup
  usedIn: number
  onError: (message: string) => void
}

function GroupCard({ group, usedIn, onError }: GroupCardProps) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
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
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex-1 min-h-[44px] flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-left"
        >
          <span className="text-base font-bold text-gray-900">{group.name}</span>
          <span className="text-sm text-gray-600">{describeRule(group)}</span>
          <span className="text-xs text-gray-400">
            {group.items.length} {group.items.length === 1 ? 'opción' : 'opciones'} ·{' '}
            {usedInLabel(usedIn)}
          </span>
        </button>
        <button
          type="button"
          onClick={() => setEditing((v) => !v)}
          aria-expanded={editing}
          aria-label={`Editar grupo ${group.name}`}
          className={linkButtonClass}
        >
          Editar
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

      {editing && (
        <GroupEditForm group={group} onDone={() => setEditing(false)} onError={onError} />
      )}

      {open && (
        <div className="border-t border-gray-200">
          <ItemsTable group={group} onError={onError} />
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
          placeholder="sin tope"
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
  const [showGroups, setShowGroups] = useState(false)

  // Solo platos con precio: sin precio no salen en la carta ni en el
  // asistente, y no tiene sentido armarles opciones.
  const dishes = useMemo(
    () =>
      (products ?? [])
        .filter((p) => p.sale_price !== null)
        .sort((a, b) => a.name.localeCompare(b.name, 'es')),
    [products],
  )
  const dishIds = useMemo(() => dishes.map((d) => d.id), [dishes])
  const linkQueries = useProductsOptionGroups(dishIds)

  // En cuantos platos esta cada grupo: alimenta el aviso "el cambio aplica a
  // todos" y el resumen de cada grupo.
  const usage = new Map<string, number>()
  for (const query of linkQueries) {
    for (const link of query.data ?? []) {
      usage.set(link.group_id, (usage.get(link.group_id) ?? 0) + 1)
    }
  }

  const loadError = groupsError || productsError

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
        <p className="text-sm text-gray-500">
          Lo que el cliente puede elegir o agregar en cada plato, y cuánto cuesta cada extra.
        </p>

        {/* Por plato */}
        <section aria-label="Por plato" className="space-y-3">
          <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500">Por plato</h2>
          {(productsLoading || groupsLoading) && (
            <p role="status" className="text-sm text-gray-400">
              Cargando carta...
            </p>
          )}
          {products && groups && dishes.length === 0 && (
            <p className="text-sm text-gray-400">
              No hay platos con precio en la carta.{' '}
              <Link to="/precios" className="underline text-gray-600">
                Cárgalos en Precios y descuentos.
              </Link>
            </p>
          )}
          {products &&
            groups &&
            dishes.map((product, index) => (
              <DishCard
                key={product.id}
                product={product}
                groups={groups}
                links={linkQueries[index]?.data}
                linksError={linkQueries[index]?.isError ?? false}
                usage={usage}
                onError={setError}
              />
            ))}
        </section>

        {/* Grupos */}
        <section aria-label="Grupos" className="space-y-3">
          <div className="flex items-center gap-3">
            <h2 className="flex-1 text-xs font-bold uppercase tracking-widest text-gray-500">
              Grupos
            </h2>
            <button
              type="button"
              onClick={() => setShowGroups((v) => !v)}
              aria-expanded={showGroups}
              className={linkButtonClass}
            >
              {showGroups ? 'Ocultar grupos' : 'Ver grupos'}
            </button>
          </div>
          <p className="text-sm text-gray-500">
            Un grupo es una pregunta que se le hace al cliente (Base, Toppings, Salsa…). El mismo
            grupo se puede usar en varios platos.
          </p>
          {showGroups && groups && groups.length === 0 && (
            <p className="text-sm text-gray-400">Todavía no hay grupos de opciones.</p>
          )}
          {showGroups &&
            groups &&
            groups.map((group) => (
              <GroupCard
                key={group.id}
                group={group}
                usedIn={usage.get(group.id) ?? 0}
                onError={setError}
              />
            ))}
          {showGroups && <NewGroupForm onError={setError} />}
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
