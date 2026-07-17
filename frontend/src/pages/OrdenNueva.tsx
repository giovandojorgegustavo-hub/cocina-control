import { useState, useId, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { isAxiosError } from 'axios'
import { useProducts, useCreateProduct } from '../lib/products'
import { useSuppliers, useCreateSupplier, type Supplier } from '../lib/suppliers'
import { useCreatePurchaseOrder } from '../lib/purchaseOrders'
import { useAuthWithGetters } from '../lib/auth'
import { formatSoles } from '../lib/currency'
import type { Product } from '../lib/types'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

const UNIT_OPTIONS = ['kg', 'un', 'lt'] as const

interface OrderItem {
  localId: string
  product_id: string
  product_name: string
  unit: string
  qty: string
  cost: string
  // costo total de la linea, editable: a veces la factura solo trae el total
  costTotal: string
  // cual de los dos costos escribio el usuario por ultimo — ese manda al
  // recalcular cuando cambia la cantidad
  lastCostEdit: 'unit' | 'total' | null
  // true = producto que todavia no existe en el catalogo: se crea al guardar
  isNew: boolean
}

function emptyItem(localId: string): OrderItem {
  return {
    localId,
    product_id: '',
    product_name: '',
    unit: '',
    qty: '',
    cost: '',
    costTotal: '',
    lastCostEdit: null,
    isNew: false,
  }
}

// El backend normaliza nombres a MAYUSCULAS con whitespace colapsado.
// Usamos la misma normalizacion para detectar duplicados antes de ofrecer crear.
function normalizeName(name: string): string {
  return name.trim().replace(/\s+/g, ' ').toUpperCase()
}

function lineTotal(item: OrderItem): number {
  const q = parseFloat(item.qty)
  const c = parseFloat(item.cost)
  if (!isFinite(q) || !isFinite(c) || q <= 0 || c <= 0) return 0
  return q * c
}

function orderTotal(items: OrderItem[]): number {
  return items.reduce((acc, i) => acc + lineTotal(i), 0)
}

function isItemValid(item: OrderItem): boolean {
  const q = parseFloat(item.qty)
  const c = parseFloat(item.cost)
  const amountsValid = isFinite(q) && q > 0 && isFinite(c) && c > 0
  if (item.isNew) {
    // producto nuevo: nombre y unidad obligatorios (la unidad es del catalogo)
    return normalizeName(item.product_name) !== '' && item.unit !== '' && amountsValid
  }
  return item.product_id !== '' && amountsValid
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

interface ToastState {
  visible: boolean
  message: string
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

// Seleccion de proveedor: existente (id) o nuevo (isNew, se crea al guardar)
interface SupplierSelection {
  id: string
  name: string
  phone: string
  isNew: boolean
}

const emptySupplier: SupplierSelection = { id: '', name: '', phone: '', isNew: false }

export function OrdenNueva() {
  const navigate = useNavigate()
  const { role } = useAuthWithGetters()
  const nextId = useId()
  const nextIdRef = useRef(1)

  const { data: products, refetch: refetchProducts } = useProducts()
  const { data: suppliers, refetch: refetchSuppliers } = useSuppliers()
  const createMutation = useCreatePurchaseOrder()
  const createProductMutation = useCreateProduct()
  const createSupplierMutation = useCreateSupplier()

  const [supplier, setSupplier] = useState<SupplierSelection>(emptySupplier)
  const [items, setItems] = useState<OrderItem[]>([emptyItem(`item-${nextId}-0`)])
  const [toast, setToast] = useState<ToastState>({ visible: false, message: '' })
  const [creatingProducts, setCreatingProducts] = useState(false)

  // Crear productos/proveedores inline: solo owner y admin (el cocinero no
  // llega a esta pantalla por el guard de ruta, pero la regla se explicita).
  const canCreateProducts = role === 'owner' || role === 'admin'

  // Product IDs already chosen — to hide duplicates in other rows
  const chosenProductIds = new Set(items.map((i) => i.product_id).filter(Boolean))

  // Validate form: proveedor elegido del registro o marcado para crear
  const supplierValid =
    supplier.name.trim() !== '' && (supplier.id !== '' || supplier.isNew)
  const allItemsValid = items.length > 0 && items.every(isItemValid)
  // dos filas no pueden crear (o referenciar) el mismo nombre nuevo
  const newNames = items.filter((i) => i.isNew).map((i) => normalizeName(i.product_name))
  const noDuplicateNewNames = new Set(newNames).size === newNames.length
  const busy =
    createMutation.isPending || creatingProducts || createSupplierMutation.isPending
  const canSubmit = supplierValid && allItemsValid && noDuplicateNewNames && !busy

  // Handlers
  function addItem() {
    const localId = `item-${nextId}-${nextIdRef.current++}`
    setItems((prev) => [...prev, emptyItem(localId)])
  }

  function removeItem(localId: string) {
    setItems((prev) => prev.filter((i) => i.localId !== localId))
  }

  function updateItem(localId: string, patch: Partial<OrderItem>) {
    setItems((prev) =>
      prev.map((i) => (i.localId === localId ? { ...i, ...patch } : i)),
    )
  }

  function showToast(message: string) {
    setToast({ visible: true, message })
    setTimeout(() => setToast({ visible: false, message: '' }), 5000)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return

    // Paso 0: crear el proveedor nuevo en el registro (si corresponde).
    // Igual que con productos: exito persistido en el estado para que un
    // reintento no lo re-cree; 409 recupera el existente por nombre.
    let supplierNameResolved = supplier.name.trim()
    if (supplier.isNew && supplier.id === '') {
      let created: Supplier | null = null
      try {
        created = await createSupplierMutation.mutateAsync({
          name: supplier.name.trim(),
          phone: supplier.phone.trim() || undefined,
        })
      } catch (err) {
        if (isAxiosError(err) && err.response?.status === 409) {
          const fresh = await refetchSuppliers()
          created =
            fresh.data?.find(
              (s) => normalizeName(s.name) === normalizeName(supplier.name),
            ) ?? null
        }
      }
      if (!created) {
        showToast(
          'No se pudo registrar el proveedor. Los datos no se perdieron — toca de nuevo para reintentar.',
        )
        return
      }
      setSupplier((prev) => ({ ...prev, id: created.id, name: created.name, isNew: false }))
      supplierNameResolved = created.name
    }

    // Paso 1: crear los productos nuevos en el catalogo (con su unidad).
    // Cada creacion exitosa se persiste en el estado de la fila, asi un
    // reintento tras un fallo posterior no vuelve a crear el mismo producto.
    let resolvedItems = items
    const pendingNew = items.filter((i) => i.isNew && i.product_id === '')
    if (pendingNew.length > 0) {
      setCreatingProducts(true)
      for (const it of pendingNew) {
        let created: Product | null = null
        try {
          created = await createProductMutation.mutateAsync({
            name: it.product_name.trim(),
            unit: it.unit,
          })
        } catch (err) {
          // 409: otro usuario creo el mismo producto entre medio. Se recupera
          // el existente por nombre y se usa SU unidad — la define quien creo
          // el producto primero (la unidad es del catalogo).
          if (isAxiosError(err) && err.response?.status === 409) {
            const fresh = await refetchProducts()
            created =
              fresh.data?.find(
                (p) => normalizeName(p.name) === normalizeName(it.product_name),
              ) ?? null
          }
        }
        if (!created) {
          showToast(
            'No se pudo crear un producto nuevo. Los datos no se perdieron — toca de nuevo para reintentar.',
          )
          setCreatingProducts(false)
          return
        }
        const patch = {
          product_id: created.id,
          product_name: created.name,
          unit: created.unit,
          isNew: false,
        }
        updateItem(it.localId, patch)
        resolvedItems = resolvedItems.map((r) =>
          r.localId === it.localId ? { ...r, ...patch } : r,
        )
      }
      setCreatingProducts(false)
    }

    // Paso 2: crear la orden con todos los product_id resueltos.
    createMutation.mutate(
      {
        supplier_name: supplierNameResolved,
        items: resolvedItems.map((i) => ({
          product_id: i.product_id,
          expected_qty: parseFloat(i.qty),
          unit_cost: parseFloat(i.cost),
        })),
      },
      {
        onSuccess: () => {
          navigate('/ordenes')
        },
        onError: () => {
          showToast(
            'No se pudo guardar la orden. Los datos no se perdieron — toca de nuevo para reintentar.',
          )
        },
      },
    )
  }

  const total = orderTotal(items)

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate('/ordenes')}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver a ordenes"
        >
          &lt;
        </button>
        <h1 className="text-lg font-bold uppercase tracking-wide">NUEVA ORDEN DE COMPRA</h1>
      </header>

      <form onSubmit={handleSubmit} className="flex-1 flex flex-col">
        <main className="flex-1 px-4 py-6 space-y-6 overflow-y-auto pb-40">
          {/* Supplier — registro con combobox (issue #129) */}
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-1">Proveedor</p>
            {supplier.isNew ? (
              <div className="border-2 border-gray-900 bg-gray-50 px-3 py-3 space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-base font-semibold text-gray-900">
                    {supplier.name}
                  </span>
                  <span className="bg-gray-900 text-white text-[10px] font-bold px-2 py-0.5 uppercase">
                    nuevo
                  </span>
                  <button
                    type="button"
                    onClick={() => setSupplier(emptySupplier)}
                    className="text-xs text-gray-500 underline active:opacity-70"
                    aria-label="Cambiar proveedor"
                  >
                    cambiar
                  </button>
                </div>
                <input
                  type="tel"
                  value={supplier.phone}
                  onChange={(e) =>
                    setSupplier((prev) => ({ ...prev, phone: e.target.value }))
                  }
                  placeholder="telefono (opcional)"
                  className="w-full px-3 py-2 border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
                  aria-label="Telefono del proveedor"
                  autoComplete="off"
                />
                <p className="text-[11px] text-gray-500">
                  se registra al guardar la orden
                </p>
              </div>
            ) : (
              <SupplierCombobox
                value={supplier}
                suppliers={suppliers ?? []}
                canCreate={canCreateProducts}
                onSelect={setSupplier}
              />
            )}
          </div>

          {/* Items table */}
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-2">Productos en esta orden</p>

            {/* Table header — desktop only */}
            <div className="hidden md:grid md:grid-cols-[1fr_80px_80px_110px_90px_40px] gap-2 text-xs text-gray-500 uppercase tracking-wide mb-1 px-1">
              <span>Producto</span>
              <span>Cant.</span>
              <span>Unidad</span>
              <span>Costo unit.</span>
              <span className="text-right">Total</span>
              <span />
            </div>

            <div className="flex flex-col gap-2">
              {items.map((item) => (
                <ItemRow
                  key={item.localId}
                  item={item}
                  products={products ?? []}
                  chosenProductIds={chosenProductIds}
                  canCreateProducts={canCreateProducts}
                  onChange={(patch) => updateItem(item.localId, patch)}
                  onRemove={() => removeItem(item.localId)}
                  canRemove={items.length > 1}
                />
              ))}
            </div>

            <button
              type="button"
              onClick={addItem}
              className="mt-3 min-h-[48px] w-full border-2 border-dashed border-gray-300 text-gray-600 text-sm font-medium hover:border-gray-400 active:opacity-70"
            >
              + agregar producto
            </button>
          </div>

          {/* Total */}
          <div className="border-t border-gray-300 pt-4 flex justify-between items-center">
            <span className="text-sm font-semibold text-gray-700">Total de la orden</span>
            <span className="text-base font-bold text-gray-900">{formatSoles(total)}</span>
          </div>
        </main>

        {/* Sticky footer */}
        <footer className="fixed bottom-0 left-0 right-0 border-t border-gray-200 bg-white px-4 py-3 flex gap-3">
          <button
            type="button"
            onClick={() => navigate('/ordenes')}
            className="flex-1 min-h-[56px] border border-gray-300 text-gray-700 font-semibold text-sm active:opacity-70"
          >
            cancelar
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className={[
              'flex-1 min-h-[56px] font-bold text-sm uppercase tracking-wide',
              canSubmit
                ? 'bg-gray-900 text-white active:opacity-70'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed',
            ].join(' ')}
          >
            {busy ? 'guardando...' : 'guardar orden — abierta'}
          </button>
        </footer>
      </form>

      {/* Toast */}
      {toast.visible && (
        <div
          role="alert"
          aria-live="assertive"
          className="fixed top-4 left-4 right-4 z-50 bg-red-600 text-white px-4 py-3 text-sm font-medium"
        >
          {toast.message}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Supplier combobox: mismo patron que el de productos — tipear busca en el
// registro; sin match exacto, la ultima opcion es registrar el proveedor.
// ---------------------------------------------------------------------------

interface SupplierComboboxProps {
  value: SupplierSelection
  suppliers: Supplier[]
  canCreate: boolean
  onSelect: (sel: SupplierSelection) => void
}

function SupplierCombobox({ value, suppliers, canCreate, onSelect }: SupplierComboboxProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)

  const displayText = open ? query : value.name
  const normalizedQuery = normalizeName(query)

  const matches =
    normalizedQuery === ''
      ? suppliers
      : suppliers.filter((s) => normalizeName(s.name).includes(normalizedQuery))

  const exactMatchExists = suppliers.some((s) => normalizeName(s.name) === normalizedQuery)
  const showCreateOption = canCreate && normalizedQuery !== '' && !exactMatchExists

  const optionCount = matches.length + (showCreateOption ? 1 : 0)
  const active = optionCount > 0 ? Math.min(highlight, optionCount - 1) : -1

  function selectSupplier(s: Supplier) {
    onSelect({ id: s.id, name: s.name, phone: s.phone ?? '', isNew: false })
    setQuery('')
    setOpen(false)
  }

  function selectCreate() {
    onSelect({ id: '', name: query.trim(), phone: '', isNew: true })
    setQuery('')
    setOpen(false)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlight((h) => Math.min(h + 1, optionCount - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight((h) => Math.max(h - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (active < 0) return
      if (active < matches.length) {
        selectSupplier(matches[active])
      } else if (showCreateOption) {
        selectCreate()
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="relative">
      <input
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-label="Proveedor"
        placeholder="buscar o registrar proveedor..."
        value={displayText}
        onFocus={() => {
          setQuery('')
          setHighlight(0)
          setOpen(true)
        }}
        onBlur={() => setOpen(false)}
        onChange={(e) => {
          setQuery(e.target.value)
          setHighlight(0)
          if (value.id !== '') {
            onSelect(emptySupplier)
          }
        }}
        onKeyDown={handleKeyDown}
        className="w-full px-4 py-3 border border-gray-300 bg-white focus:outline-none focus:ring-2 focus:ring-gray-900 text-base"
        autoComplete="off"
      />

      {open && (
        <ul
          role="listbox"
          className="absolute z-20 left-0 right-0 top-full mt-1 max-h-56 overflow-y-auto bg-white border-2 border-gray-900 shadow-lg"
        >
          {matches.map((s, i) => (
            <li key={s.id} role="option" aria-selected={i === active}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault()
                  selectSupplier(s)
                }}
                className={[
                  'w-full min-h-[44px] px-3 py-2 flex justify-between items-center text-left text-sm active:bg-gray-200',
                  i === active ? 'bg-gray-100' : 'hover:bg-gray-100',
                ].join(' ')}
              >
                <span className="text-gray-900">{s.name}</span>
                {s.phone && <span className="text-xs text-gray-500">{s.phone}</span>}
              </button>
            </li>
          ))}

          {matches.length === 0 && !showCreateOption && (
            <li className="px-3 py-2 text-sm text-gray-500">sin resultados</li>
          )}

          {showCreateOption && (
            <li role="option" aria-selected={active === matches.length}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault()
                  selectCreate()
                }}
                className={[
                  'w-full min-h-[44px] px-3 py-2 text-left text-sm font-bold bg-gray-900 text-white',
                  active === matches.length ? 'opacity-80 underline' : 'active:opacity-80',
                ].join(' ')}
              >
                + registrar "{query.trim()}" como proveedor nuevo
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Item row sub-component
// ---------------------------------------------------------------------------

interface ItemRowProps {
  item: OrderItem
  products: Product[]
  chosenProductIds: Set<string>
  canCreateProducts: boolean
  onChange: (patch: Partial<OrderItem>) => void
  onRemove: () => void
  canRemove: boolean
}

function ItemRow({
  item,
  products,
  chosenProductIds,
  canCreateProducts,
  onChange,
  onRemove,
  canRemove,
}: ItemRowProps) {
  // Costos bidireccionales: el usuario puede escribir el unitario O el total.
  // El que escribio por ultimo manda; el otro se deriva. El backend siempre
  // recibe unit_cost, asi que el unitario derivado se normaliza a 2 decimales
  // y el total mostrado se ajusta a unitario x cantidad (fuente de verdad).
  function deriveTotal(qtyStr: string, unitStr: string): string {
    const q = parseFloat(qtyStr)
    const c = parseFloat(unitStr)
    return isFinite(q) && q > 0 && isFinite(c) && c > 0 ? (q * c).toFixed(2) : ''
  }

  function deriveUnit(qtyStr: string, totalStr: string): string {
    const q = parseFloat(qtyStr)
    const t = parseFloat(totalStr)
    return isFinite(q) && q > 0 && isFinite(t) && t > 0 ? (t / q).toFixed(2) : ''
  }

  function handleUnitCostChange(v: string) {
    onChange({ cost: v, costTotal: deriveTotal(item.qty, v), lastCostEdit: 'unit' })
  }

  function handleTotalChange(v: string) {
    onChange({ costTotal: v, cost: deriveUnit(item.qty, v), lastCostEdit: 'total' })
  }

  function handleQtyChange(v: string) {
    if (item.lastCostEdit === 'total') {
      onChange({ qty: v, cost: deriveUnit(v, item.costTotal) })
    } else {
      onChange({ qty: v, costTotal: deriveTotal(v, item.cost) })
    }
  }

  return (
    <div className="bg-white border border-gray-200 px-2 py-2">
      <div className="grid grid-cols-[1fr_80px_80px_110px_90px_40px] gap-2 items-center">
        {/* Product: combobox (existente) o nombre fijo + badge (nuevo) */}
        {item.isNew ? (
          <div className="flex items-center gap-2 min-h-[44px] px-2">
            <span className="text-sm font-semibold text-gray-900 truncate">
              {item.product_name}
            </span>
            <span className="flex-shrink-0 bg-gray-900 text-white text-[10px] font-bold px-2 py-0.5 uppercase">
              nuevo
            </span>
            <button
              type="button"
              onClick={() =>
                onChange({ isNew: false, product_id: '', product_name: '', unit: '' })
              }
              className="flex-shrink-0 text-xs text-gray-500 underline active:opacity-70"
              aria-label="Cambiar producto"
            >
              cambiar
            </button>
          </div>
        ) : (
          <ProductCombobox
            value={item}
            products={products}
            chosenProductIds={chosenProductIds}
            canCreateProducts={canCreateProducts}
            onChange={onChange}
          />
        )}

        {/* Qty */}
        <input
          type="number"
          inputMode="decimal"
          min="0.001"
          step="any"
          value={item.qty}
          onChange={(e) => handleQtyChange(e.target.value)}
          placeholder="0"
          className="min-h-[44px] px-2 border border-gray-300 text-sm text-center focus:outline-none focus:ring-2 focus:ring-gray-900 w-full"
          aria-label="Cantidad"
          required
        />

        {/* Unit — readonly para existentes (viene del catalogo); select para nuevos */}
        {item.isNew ? (
          <select
            value={item.unit}
            onChange={(e) => onChange({ unit: e.target.value })}
            // el select se monta justo cuando la fila pasa a producto nuevo:
            // el foco salta al siguiente dato obligatorio (carga sin mouse)
            autoFocus
            className="min-h-[44px] px-1 border-2 border-gray-900 bg-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-gray-900 w-full"
            aria-label="Unidad del producto"
            required
          >
            <option value="">unidad...</option>
            {UNIT_OPTIONS.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            readOnly
            value={item.unit}
            className="min-h-[44px] px-2 border border-gray-200 bg-gray-100 text-sm text-center text-gray-500 w-full"
            aria-label="Unidad"
            tabIndex={-1}
          />
        )}

        {/* Cost per unit */}
        <input
          type="number"
          inputMode="decimal"
          min="0.01"
          step="0.01"
          value={item.cost}
          onChange={(e) => handleUnitCostChange(e.target.value)}
          placeholder="0.00"
          className="min-h-[44px] px-2 border border-gray-300 text-sm text-right focus:outline-none focus:ring-2 focus:ring-gray-900 w-full"
          aria-label="Costo unitario"
          required
        />

        {/* Line total — editable: si la factura solo trae el total, se escribe
            aca y el unitario se deriva (total / cantidad) */}
        <input
          type="number"
          inputMode="decimal"
          min="0.01"
          step="0.01"
          value={item.costTotal}
          onChange={(e) => handleTotalChange(e.target.value)}
          placeholder="0.00"
          className="min-h-[44px] px-2 border border-gray-300 text-sm text-right tabular-nums focus:outline-none focus:ring-2 focus:ring-gray-900 w-full"
          aria-label="Costo total"
        />

        {/* Remove */}
        <button
          type="button"
          onClick={onRemove}
          disabled={!canRemove}
          className={[
            'min-h-[44px] min-w-[40px] flex items-center justify-center text-lg font-bold',
            canRemove ? 'text-gray-500 active:text-red-600' : 'text-gray-300 cursor-not-allowed',
          ].join(' ')}
          aria-label="Eliminar fila"
        >
          —
        </button>
      </div>

      {item.isNew && (
        <p className="text-[11px] text-gray-500 mt-1 px-2">
          se crea en el catalogo al guardar la orden — la unidad es del producto, no de esta
          compra
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Product combobox: tipear busca en el catalogo; si no hay match exacto, la
// ultima opcion es crear el producto (solo owner/admin). Los parecidos se
// muestran ANTES de ofrecer crear (anti-duplicados).
// ---------------------------------------------------------------------------

interface ProductComboboxProps {
  value: OrderItem
  products: Product[]
  chosenProductIds: Set<string>
  canCreateProducts: boolean
  onChange: (patch: Partial<OrderItem>) => void
}

function ProductCombobox({
  value,
  products,
  chosenProductIds,
  canCreateProducts,
  onChange,
}: ProductComboboxProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)

  const displayText = open ? query : value.product_name
  const normalizedQuery = normalizeName(query)

  const available = products.filter(
    (p) => !chosenProductIds.has(p.id) || p.id === value.product_id,
  )
  const matches =
    normalizedQuery === ''
      ? available
      : available.filter((p) => normalizeName(p.name).includes(normalizedQuery))

  const exactMatchExists = products.some((p) => normalizeName(p.name) === normalizedQuery)
  const showCreateOption = canCreateProducts && normalizedQuery !== '' && !exactMatchExists

  // Opciones navegables con teclado: los matches y, al final, la de crear.
  const optionCount = matches.length + (showCreateOption ? 1 : 0)
  const active = optionCount > 0 ? Math.min(highlight, optionCount - 1) : -1

  function selectProduct(p: Product) {
    onChange({ product_id: p.id, product_name: p.name, unit: p.unit, isNew: false })
    setQuery('')
    setOpen(false)
  }

  function selectCreate() {
    onChange({ product_id: '', product_name: query.trim(), unit: '', isNew: true })
    setQuery('')
    setOpen(false)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlight((h) => Math.min(h + 1, optionCount - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight((h) => Math.max(h - 1, 0))
    } else if (e.key === 'Enter') {
      // Enter selecciona la opcion activa (o crea) — y NUNCA envia el form
      // mientras el dropdown esta abierto: carga rapida sin mouse.
      e.preventDefault()
      if (active < 0) return
      if (active < matches.length) {
        selectProduct(matches[active])
      } else if (showCreateOption) {
        selectCreate()
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="relative">
      <input
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-label="Elegir producto"
        placeholder="elegir producto..."
        value={displayText}
        onFocus={() => {
          setQuery('')
          setHighlight(0)
          setOpen(true)
        }}
        onBlur={() => setOpen(false)}
        onChange={(e) => {
          setQuery(e.target.value)
          setHighlight(0)
          if (value.product_id !== '') {
            onChange({ product_id: '', product_name: '', unit: '' })
          }
        }}
        onKeyDown={handleKeyDown}
        className="min-h-[44px] px-2 border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-gray-900 w-full"
        autoComplete="off"
      />

      {open && (
        <ul
          role="listbox"
          className="absolute z-20 left-0 right-0 top-full mt-1 max-h-56 overflow-y-auto bg-white border-2 border-gray-900 shadow-lg"
        >
          {matches.map((p, i) => (
            <li key={p.id} role="option" aria-selected={i === active}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault()
                  selectProduct(p)
                }}
                className={[
                  'w-full min-h-[44px] px-3 py-2 flex justify-between items-center text-left text-sm active:bg-gray-200',
                  i === active ? 'bg-gray-100' : 'hover:bg-gray-100',
                ].join(' ')}
              >
                <span className="text-gray-900">{p.name}</span>
                <span className="text-xs text-gray-500">{p.unit}</span>
              </button>
            </li>
          ))}

          {matches.length === 0 && !showCreateOption && (
            <li className="px-3 py-2 text-sm text-gray-500">sin resultados</li>
          )}

          {showCreateOption && (
            <li role="option" aria-selected={active === matches.length}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault()
                  selectCreate()
                }}
                className={[
                  'w-full min-h-[44px] px-3 py-2 text-left text-sm font-bold bg-gray-900 text-white',
                  active === matches.length ? 'opacity-80 underline' : 'active:opacity-80',
                ].join(' ')}
              >
                + crear "{query.trim()}" como producto nuevo
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
